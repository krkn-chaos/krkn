# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import os
from typing import Tuple

import yaml
from jinja2 import FileSystemLoader, Environment
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import Pod

from krkn.scenario_plugins.network_chaos_ng.models import (
    BaseNetworkChaosConfig,
)


def log_info(message: str, parallel: bool = False, node_name: str = ""):
    """
    log helper method for INFO severity to be used in the scenarios
    """
    if parallel:
        logging.info(f"[{node_name}]: {message}")
    else:
        logging.info(message)


def log_error(message: str, parallel: bool = False, node_name: str = ""):
    """
    log helper method for ERROR severity to be used in the scenarios
    """
    if parallel:
        logging.error(f"[{node_name}]: {message}")
    else:
        logging.error(message)


def log_warning(message: str, parallel: bool = False, node_name: str = ""):
    """
    log helper method for WARNING severity to be used in the scenarios
    """
    if parallel:
        logging.warning(f"[{node_name}]: {message}")
    else:
        logging.warning(message)


def deploy_network_chaos_ng_pod(
    config: BaseNetworkChaosConfig,
    target_node: str,
    pod_name: str,
    kubecli: KrknKubernetes,
    container_name: str = "fedora",
    host_network: bool = True,
):
    file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
    env = Environment(loader=file_loader, autoescape=True)
    pod_template = env.get_template("templates/network-chaos.j2")
    tolerations = []

    for taint in config.taints:
        key_value_part, effect = taint.split(":", 1)
        if "=" in key_value_part:
            key, value = key_value_part.split("=", 1)
            operator = "Equal"
        else:
            key = key_value_part
            value = None
            operator = "Exists"
        toleration = {
            "key": key,
            "operator": operator,
            "effect": effect,
        }
        if value is not None:
            toleration["value"] = value
        tolerations.append(toleration)

    pod_body = yaml.safe_load(
        pod_template.render(
            pod_name=pod_name,
            namespace=config.namespace,
            host_network=host_network,
            target=target_node,
            container_name=container_name,
            workload_image=config.image,
            taints=tolerations,
            service_account=config.service_account,
        )
    )

    kubecli.create_pod(pod_body, config.namespace, 300)


def get_pod_default_interface(
    pod_name: str, namespace: str, kubecli: KrknKubernetes
) -> str:
    cmd = "ip r | grep default | awk '/default/ {print $5}'"
    output = kubecli.exec_cmd_in_pod([cmd], pod_name, namespace)
    return output.replace("\n", "")


def find_virt_launcher_netns_pid(
    chaos_pod_name: str,
    namespace: str,
    pids: list[str],
    kubecli: KrknKubernetes,
) -> str:
    """Return the first PID from `pids` whose netns contains a tap device.

    Not all PIDs returned by get_pod_pids are inside the virt-launcher network
    namespace — some helper processes run in the host netns.  Entering one of
    those would target the node's physical NIC instead of the bridge slave
    inside the virt-launcher netns.
    """
    for pid in pids:
        try:
            result = kubecli.exec_cmd_in_pod(
                [f"nsenter --target {pid} --net -- ip link show type tun"],
                chaos_pod_name,
                namespace,
            )
            if result and "tap" in result:
                return pid
        except Exception:
            continue
    return None


def get_vmi_tap_interface(
    chaos_pod_name: str,
    namespace: str,
    netns_pid: str,
    kubecli: KrknKubernetes,
) -> str:
    """Return the name of the tap device inside the virt-launcher netns."""
    try:
        result = kubecli.exec_cmd_in_pod(
            [f"nsenter --target {netns_pid} --net -- ip -o link show type tun"],
            chaos_pod_name,
            namespace,
        )
        if not result:
            return None
        for line in result.splitlines():
            parts = line.split(":")
            if len(parts) >= 2:
                iface = parts[1].strip().split("@")[0].strip()
                if iface.startswith("tap"):
                    return iface
    except Exception:
        pass
    return None


def setup_network_chaos_ng_scenario(
    config: BaseNetworkChaosConfig,
    node_name: str,
    pod_name: str,
    container_name: str,
    kubecli: KrknKubernetes,
    target: str,
    parallel: bool,
    host_network: bool,
) -> Tuple[list[str], list[str]]:

    deploy_network_chaos_ng_pod(
        config,
        node_name,
        pod_name,
        kubecli,
        container_name,
        host_network=host_network,
    )

    if len(config.interfaces) == 0:
        interfaces = [
            get_pod_default_interface(
                pod_name,
                config.namespace,
                kubecli,
            )
        ]

        log_info(f"detected default interface {interfaces[0]}", parallel, target)

    else:
        interfaces = config.interfaces
    # if not host_network means that the target is a pod so container_ids need to be resolved
    # otherwise it's not needed
    if not host_network:
        container_ids = kubecli.get_container_ids(target, config.namespace)
    else:
        container_ids = []

    return container_ids, interfaces
