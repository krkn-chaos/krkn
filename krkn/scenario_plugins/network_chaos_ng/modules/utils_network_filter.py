from typing import Tuple

from krkn_lib.k8s import KrknKubernetes

from krkn.scenario_plugins.network_chaos_ng.models import NetworkFilterConfig
from krkn.scenario_plugins.network_chaos_ng.modules.utils import log_info


def generate_rules(
    interfaces: list[str], config: NetworkFilterConfig
) -> Tuple[list[str], list[str]]:
    input_rules = []
    output_rules = []
    for interface in interfaces:
        for port in config.ports:
            if config.egress:
                for protocol in set(config.protocols):
                    output_rules.append(
                        f"iptables -I OUTPUT 1 -p {protocol} --dport {port} -m state --state NEW,RELATED,ESTABLISHED -j DROP"
                    )

            if config.ingress:
                for protocol in set(config.protocols):
                    input_rules.append(
                        f"iptables -I INPUT 1 -i {interface} -p {protocol} --dport {port} -m state --state NEW,RELATED,ESTABLISHED -j DROP"
                    )
    return input_rules, output_rules


def apply_network_rules(
    kubecli: KrknKubernetes,
    input_rules: list[str],
    output_rules: list[str],
    pod_name: str,
    namespace: str,
    parallel: bool,
    node_name: str,
):
    for rule in input_rules:
        log_info(f"applying iptables INPUT rule: {rule}", parallel, node_name)
        kubecli.exec_cmd_in_pod([rule], pod_name, namespace)
    for rule in output_rules:
        log_info(f"applying iptables OUTPUT rule: {rule}", parallel, node_name)
        kubecli.exec_cmd_in_pod([rule], pod_name, namespace)


def clean_network_rules(
    kubecli: KrknKubernetes,
    input_rules: list[str],
    output_rules: list[str],
    pod_name: str,
    namespace: str,
):
    for _ in input_rules:
        # always deleting the first rule since has been inserted from the top
        kubecli.exec_cmd_in_pod([f"iptables -D INPUT 1"], pod_name, namespace)
    for _ in output_rules:
        # always deleting the first rule since has been inserted from the top
        kubecli.exec_cmd_in_pod([f"iptables -D OUTPUT 1"], pod_name, namespace)


def clean_network_rules_namespaced(
    kubecli: KrknKubernetes,
    input_rules: list[str],
    output_rules: list[str],
    pod_name: str,
    namespace: str,
    pids: list[str],
):
    for _ in input_rules:
        for pid in pids:
            # always deleting the first rule since has been inserted from the top
            kubecli.exec_cmd_in_pod(
                [f"nsenter --target {pid} --net -- iptables -D INPUT 1"],
                pod_name,
                namespace,
            )
    for _ in output_rules:
        for pid in pids:
            # always deleting the first rule since has been inserted from the top
            kubecli.exec_cmd_in_pod(
                [f"nsenter --target {pid} --net -- iptables -D OUTPUT 1"],
                pod_name,
                namespace,
            )
