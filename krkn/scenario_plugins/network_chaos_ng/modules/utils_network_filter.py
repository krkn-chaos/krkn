import os

import yaml
from jinja2 import FileSystemLoader, Environment
from krkn_lib.k8s import KrknKubernetes

from krkn.scenario_plugins.network_chaos_ng.models import NetworkFilterConfig
from krkn.scenario_plugins.network_chaos_ng.modules.utils import log_info


def generate_rules(
    interfaces: list[str], config: NetworkFilterConfig
) -> (list[str], list[str]):
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


def generate_namespaced_rules(
    interfaces: list[str], config: NetworkFilterConfig, pids: list[str]
) -> (list[str], list[str]):
    namespaced_input_rules: list[str] = []
    namespaced_output_rules: list[str] = []
    input_rules, output_rules = generate_rules(interfaces, config)
    for pid in pids:
        ns_input_rules = [
            f"nsenter --target {pid} --net -- {rule}" for rule in input_rules
        ]
        ns_output_rules = [
            f"nsenter --target {pid} --net -- {rule}" for rule in output_rules
        ]
        namespaced_input_rules.extend(ns_input_rules)
        namespaced_output_rules.extend(ns_output_rules)

    return namespaced_input_rules, namespaced_output_rules


def deploy_network_filter_pod(
    config: NetworkFilterConfig,
    target_node: str,
    pod_name: str,
    kubecli: KrknKubernetes,
    container_name: str = "fedora",
):
    file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
    env = Environment(loader=file_loader, autoescape=True)
    pod_template = env.get_template("templates/network-chaos.j2")
    pod_body = yaml.safe_load(
        pod_template.render(
            pod_name=pod_name,
            namespace=config.namespace,
            host_network=True,
            target=target_node,
            container_name=container_name,
            workload_image=config.image,
        )
    )

    kubecli.create_pod(pod_body, config.namespace, 300)


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


def get_default_interface(
    pod_name: str, namespace: str, kubecli: KrknKubernetes
) -> str:
    cmd = "ip r | grep default | awk '/default/ {print $5}'"
    output = kubecli.exec_cmd_in_pod([cmd], pod_name, namespace)
    return output.replace("\n", "")
