import os
import queue
import time

import yaml
from jinja2 import Environment, FileSystemLoader


from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_random_string
from krkn.scenario_plugins.network_chaos_ng.models import (
    BaseNetworkChaosConfig,
    NetworkFilterConfig,
    NetworkChaosScenarioType,
)
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)


class NodeNetworkFilterModule(AbstractNetworkChaosModule):
    config: NetworkFilterConfig

    def run(
        self,
        target: str,
        kubecli: KrknTelemetryOpenshift,
        error_queue: queue.Queue = None,
    ):
        parallel = False
        if error_queue:
            parallel = True
        try:
            file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
            env = Environment(loader=file_loader, autoescape=True)
            pod_name = f"node-filter-{get_random_string(5)}"
            pod_template = env.get_template("templates/network-chaos.j2")
            pod_body = yaml.safe_load(
                pod_template.render(
                    pod_name=pod_name,
                    namespace=self.config.namespace,
                    host_network=True,
                    target=target,
                )
            )
            self.log_info(
                f"creating pod to filter "
                f"ports {','.join([str(port) for port in self.config.ports])}, "
                f"ingress:{str(self.config.ingress)}, "
                f"egress:{str(self.config.egress)}",
                parallel,
                target,
            )
            kubecli.get_lib_kubernetes().create_pod(
                pod_body, self.config.namespace, 300
            )

            if len(self.config.interfaces) == 0:
                interfaces = [
                    self.get_default_interface(pod_name, self.config.namespace, kubecli)
                ]
                self.log_info(f"detected default interface {interfaces[0]}")
            else:
                interfaces = self.config.interfaces

            input_rules, output_rules = self.generate_rules(interfaces)

            for rule in input_rules:
                self.log_info(f"applying iptables INPUT rule: {rule}", parallel, target)
                kubecli.get_lib_kubernetes().exec_cmd_in_pod(
                    [rule], pod_name, self.config.namespace
                )
            for rule in output_rules:
                self.log_info(
                    f"applying iptables OUTPUT rule: {rule}", parallel, target
                )
                kubecli.get_lib_kubernetes().exec_cmd_in_pod(
                    [rule], pod_name, self.config.namespace
                )
            self.log_info(
                f"waiting {self.config.test_duration} seconds before removing the iptables rules"
            )
            time.sleep(self.config.test_duration)
            self.log_info("removing iptables rules")
            for _ in input_rules:
                # always deleting the first rule since has been inserted from the top
                kubecli.get_lib_kubernetes().exec_cmd_in_pod(
                    [f"iptables -D INPUT 1"], pod_name, self.config.namespace
                )
            for _ in output_rules:
                # always deleting the first rule since has been inserted from the top
                kubecli.get_lib_kubernetes().exec_cmd_in_pod(
                    [f"iptables -D OUTPUT 1"], pod_name, self.config.namespace
                )
            self.log_info(
                f"deleting network chaos pod {pod_name} from {self.config.namespace}"
            )

            kubecli.get_lib_kubernetes().delete_pod(pod_name, self.config.namespace)

        except Exception as e:
            if error_queue is None:
                raise e
            else:
                error_queue.put(str(e))

    def __init__(self, config: NetworkFilterConfig):
        self.config = config

    def get_config(self) -> (NetworkChaosScenarioType, BaseNetworkChaosConfig):
        return NetworkChaosScenarioType.Node, self.config

    def get_default_interface(
        self, pod_name: str, namespace: str, kubecli: KrknTelemetryOpenshift
    ) -> str:
        cmd = "ip r | grep default | awk '/default/ {print $5}'"
        output = kubecli.get_lib_kubernetes().exec_cmd_in_pod(
            [cmd], pod_name, namespace
        )
        return output.replace("\n", "")

    def generate_rules(self, interfaces: list[str]) -> (list[str], list[str]):
        input_rules = []
        output_rules = []
        for interface in interfaces:
            for port in self.config.ports:
                if self.config.egress:
                    output_rules.append(
                        f"iptables -I OUTPUT 1 -p tcp --dport {port} -m state --state NEW,RELATED,ESTABLISHED -j DROP"
                    )

                if self.config.ingress:
                    input_rules.append(
                        f"iptables -I INPUT 1 -i {interface} -p tcp --dport {port} -m state --state NEW,RELATED,ESTABLISHED -j DROP"
                    )
        return input_rules, output_rules
