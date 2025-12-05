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


def setup_network_chaos_ng_scenario(
    config: BaseNetworkChaosConfig,
    pod_info: Pod,
    pod_name: str,
    container_name: str,
    kubecli: KrknKubernetes,
    target: str,
    parallel: bool,
) -> Tuple[list[str], list[str]]:

    deploy_network_chaos_ng_pod(
        config,
        pod_info.nodeName,
        pod_name,
        kubecli,
        container_name,
        host_network=False,
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

    container_ids = kubecli.get_container_ids(target, config.namespace)

    return container_ids, interfaces
