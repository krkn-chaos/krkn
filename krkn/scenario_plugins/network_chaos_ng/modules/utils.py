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
    chaos_pod_name: str, namespace: str, pids: list[str], kubecli: KrknKubernetes
) -> str:
    """Return the first PID that is in the virt-launcher's network namespace.

    get_pod_pids returns all PIDs from the compute container's cgroup.  Some of
    those processes (helpers, privileged threads) run in the HOST network
    namespace rather than the pod's netns.  nsenter-ing one of those would
    target the node's physical interfaces (e.g. ens4) instead of the
    virt-launcher's bridge slave.

    tap0 is a KubeVirt-specific tap device that only exists inside the
    virt-launcher's netns, so its presence is a reliable probe.
    """
    for pid in pids:
        cmd = f"nsenter --target {pid} --net -- ip link show tap0 2>/dev/null"
        try:
            out = kubecli.exec_cmd_in_pod([cmd], chaos_pod_name, namespace)
            if "tap0" in out:
                return pid
        except Exception:
            continue
    return ""


def get_vmi_tap_interface(
    chaos_pod_name: str, namespace: str, pid: str, kubecli: KrknKubernetes
) -> str:
    """Find the VMI's primary tap interface inside the virt-launcher network namespace.

    The tap device is the VM-facing member of the KubeVirt bridge:
        ovn-udn1-nic -> k6t-ovn-udn1 (bridge) -> tap0 -> QEMU (VM guest)

    We locate it by finding the tap member of the k6t-* bridge rather than
    grepping for any tap-prefixed device, so the detection works regardless
    of how many interfaces the VM has.

    Blocking the tap interface isolates only this VMI.  Blocking the bridge
    slave (ovn-udn1-nic) would also sever OVN's BFD heartbeats and trigger
    a node-wide network reconvergence.
    """
    # Find the k6t-* bridge name first, then find its tap member.
    bridge_cmd = (
        f"nsenter --target {pid} --net -- "
        f"ip link show | grep ': k6t-' | head -1 | cut -d: -f2 | tr -d ' '"
    )
    bridge = kubecli.exec_cmd_in_pod([bridge_cmd], chaos_pod_name, namespace).strip()
    if not bridge:
        return ""

    tap_cmd = (
        f"nsenter --target {pid} --net -- "
        f"ip link show master {bridge} | grep ': tap' | head -1 | cut -d: -f2 | tr -d ' '"
    )
    output = kubecli.exec_cmd_in_pod([tap_cmd], chaos_pod_name, namespace)
    return output.strip()


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
