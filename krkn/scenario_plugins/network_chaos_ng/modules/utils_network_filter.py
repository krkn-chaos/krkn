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
        if config.ports:
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
        else:
            # empty ports means block all traffic on all ports
            if config.egress:
                for protocol in set(config.protocols):
                    output_rules.append(
                        f"iptables -I OUTPUT 1 -p {protocol} -m state --state NEW,RELATED,ESTABLISHED -j DROP"
                    )
            if config.ingress:
                for protocol in set(config.protocols):
                    input_rules.append(
                        f"iptables -I INPUT 1 -i {interface} -p {protocol} -m state --state NEW,RELATED,ESTABLISHED -j DROP"
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


def generate_namespaced_rules(
    interfaces: list[str], config: NetworkFilterConfig, pids: list[str]
) -> Tuple[list[str], list[str]]:
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


def apply_tc_vmi_chaos(
    kubecli: KrknKubernetes,
    chaos_pod_name: str,
    namespace: str,
    pid: str,
    iface: str,
    config: NetworkFilterConfig,
    parallel: bool,
    vmi_name: str,
) -> Tuple[list[str], list[str]]:
    """Apply iptables rules inside the virt-launcher netns via nsenter.

    Targets the tap interface (tap0) rather than the bridge slave (ovn-udn1-nic)
    so that OVN's BFD heartbeats on the bridge are unaffected.  Rules are applied
    inside the virt-launcher's network namespace using nsenter, matching the same
    iptables approach used by pod_network_filter and node_network_filter.

    Returns (input_rules, output_rules) needed for cleanup.
    """
    log_info(
        f"applying iptables rules on {iface} "
        f"(ports:{config.ports}, protocols:{config.protocols})",
        parallel,
        vmi_name,
    )
    input_rules, output_rules = generate_namespaced_rules([iface], config, [pid])
    apply_network_rules(kubecli, input_rules, output_rules, chaos_pod_name, namespace, parallel, vmi_name)
    return input_rules, output_rules


def clean_tc_vmi_chaos(
    kubecli: KrknKubernetes,
    chaos_pod_name: str,
    namespace: str,
    pid: str,
    iface: str,
    input_rules: list[str],
    output_rules: list[str],
):
    """Remove iptables rules applied by apply_tc_vmi_chaos."""
    clean_network_rules_namespaced(
        kubecli, input_rules, output_rules, chaos_pod_name, namespace, [pid]
    )


