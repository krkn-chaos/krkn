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
    parallel: bool,
    vmi_name: str,
):
    """Block all traffic on the VMI's tap interface using tc.

    Targets tap0 (the VM-facing end of the KubeVirt bridge) rather than the
    bridge slave (ovn-udn1-nic).  Blocking the bridge slave also cuts OVN's
    BFD heartbeats and causes a node-wide network reconvergence; tap0 only
    connects to QEMU so blocking it isolates only this VMI.

    tc operates at the device layer below iptables and works without br_netfilter:
      - root netem loss 100%  -> drops traffic sent toward the VM
      - ingress + matchall    -> drops traffic sent by the VM
    Only one pid is needed because all processes in the container share a netns.
    """
    ns = f"nsenter --target {pid} --net --"
    log_info(f"applying tc block on {iface} (egress netem + ingress drop)", parallel, vmi_name)
    kubecli.exec_cmd_in_pod(
        [f"{ns} tc qdisc add dev {iface} root netem loss 100%"],
        chaos_pod_name,
        namespace,
    )
    kubecli.exec_cmd_in_pod(
        [f"{ns} tc qdisc add dev {iface} ingress"],
        chaos_pod_name,
        namespace,
    )
    kubecli.exec_cmd_in_pod(
        [f"{ns} tc filter add dev {iface} parent ffff: protocol all matchall action drop"],
        chaos_pod_name,
        namespace,
    )


def clean_tc_vmi_chaos(
    kubecli: KrknKubernetes,
    chaos_pod_name: str,
    namespace: str,
    pid: str,
    iface: str,
):
    """Remove tc qdiscs applied by apply_tc_vmi_chaos."""
    ns = f"nsenter --target {pid} --net --"
    for cmd in [
        f"{ns} tc qdisc del dev {iface} root",
        f"{ns} tc qdisc del dev {iface} ingress",
    ]:
        try:
            kubecli.exec_cmd_in_pod([cmd], chaos_pod_name, namespace)
        except Exception:
            pass


