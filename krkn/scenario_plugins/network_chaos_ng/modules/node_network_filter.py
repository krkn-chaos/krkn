import queue
import time
from typing import Tuple

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
from krkn.scenario_plugins.network_chaos_ng.modules.utils import log_info

from krkn.scenario_plugins.network_chaos_ng.modules.utils_network_filter import (
    deploy_network_filter_pod,
    apply_network_rules,
    clean_network_rules,
    generate_rules,
    get_default_interface,
)


class NodeNetworkFilterModule(AbstractNetworkChaosModule):
    config: NetworkFilterConfig
    kubecli: KrknTelemetryOpenshift

    def run(self, target: str, error_queue: queue.Queue = None):
        parallel = False
        if error_queue:
            parallel = True
        try:
            log_info(
                f"creating workload to filter node {target} network"
                f"ports {','.join([str(port) for port in self.config.ports])}, "
                f"ingress:{str(self.config.ingress)}, "
                f"egress:{str(self.config.egress)}",
                parallel,
                target,
            )

            pod_name = f"node-filter-{get_random_string(5)}"
            deploy_network_filter_pod(
                self.config,
                target,
                pod_name,
                self.kubecli.get_lib_kubernetes(),
            )

            if len(self.config.interfaces) == 0:
                interfaces = [
                    get_default_interface(
                        pod_name,
                        self.config.namespace,
                        self.kubecli.get_lib_kubernetes(),
                    )
                ]

                log_info(
                    f"detected default interface {interfaces[0]}", parallel, target
                )

            else:
                interfaces = self.config.interfaces

            input_rules, output_rules = generate_rules(interfaces, self.config)

            apply_network_rules(
                self.kubecli.get_lib_kubernetes(),
                input_rules,
                output_rules,
                pod_name,
                self.config.namespace,
                parallel,
                target,
            )

            log_info(
                f"waiting {self.config.test_duration} seconds before removing the iptables rules",
                parallel,
                target,
            )

            time.sleep(self.config.test_duration)

            log_info("removing iptables rules", parallel, target)

            clean_network_rules(
                self.kubecli.get_lib_kubernetes(),
                input_rules,
                output_rules,
                pod_name,
                self.config.namespace,
            )

            self.kubecli.get_lib_kubernetes().delete_pod(
                pod_name, self.config.namespace
            )

        except Exception as e:
            if error_queue is None:
                raise e
            else:
                error_queue.put(str(e))

    def __init__(self, config: NetworkFilterConfig, kubecli: KrknTelemetryOpenshift):
        super().__init__(config, kubecli)
        self.config = config

    def get_config(self) -> Tuple[NetworkChaosScenarioType, BaseNetworkChaosConfig]:
        return NetworkChaosScenarioType.Node, self.config

    def get_targets(self) -> list[str]:
        if self.base_network_config.label_selector:
            return self.kubecli.get_lib_kubernetes().list_nodes(
                self.base_network_config.label_selector
            )
        else:
            if not self.config.target:
                raise Exception(
                    "neither node selector nor node_name (target) specified, aborting."
                )
            node_info = self.kubecli.get_lib_kubernetes().list_nodes()
            if self.config.target not in node_info:
                raise Exception(f"node {self.config.target} not found, aborting")

            return [self.config.target]
