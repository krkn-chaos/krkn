import logging

from krkn_lib.k8s import KrknKubernetes

from krkn.scenario_plugins.network_chaos_ng.models import BaseNetworkChaosConfig


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


def taints_to_tolerations(taints: list[str]) -> list[dict[str, str]]:
    tolerations = []
    for taint in taints:
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
    return tolerations
