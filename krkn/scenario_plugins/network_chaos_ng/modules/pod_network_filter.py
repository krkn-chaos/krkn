import logging
import queue
import time

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_random_string

from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosScenarioType,
    BaseNetworkChaosConfig,
    NetworkFilterConfig,
)
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.modules.utils import log_info, log_error
from krkn.scenario_plugins.network_chaos_ng.modules.utils_network_filter import (
    deploy_network_filter_pod,
    generate_namespaced_rules,
    apply_network_rules,
    clean_network_rules_namespaced,
)


class PodNetworkFilterModule(AbstractNetworkChaosModule):
    config: NetworkFilterConfig

    def run(self, target: str, error_queue: queue.Queue = None):
        parallel = False
        if error_queue:
            parallel = True
        try:
            pod_name = f"pod-filter-{get_random_string(5)}"
            container_name = f"fedora-container-{get_random_string(5)}"
            pod_info = self.kubecli.get_lib_kubernetes().get_pod_info(
                target, self.config.namespace
            )

            log_info(
                f"creating workload to filter pod {self.config.target} network"
                f"ports {','.join([str(port) for port in self.config.ports])}, "
                f"ingress:{str(self.config.ingress)}, "
                f"egress:{str(self.config.egress)}",
                parallel,
                pod_name,
            )

            if not pod_info:
                raise Exception(
                    f"impossible to retrieve infos for pod {self.config.target} namespace {self.config.namespace}"
                )

            deploy_network_filter_pod(
                self.config,
                pod_info.nodeName,
                pod_name,
                self.kubecli.get_lib_kubernetes(),
                container_name,
                host_network=False,
            )

            if len(self.config.interfaces) == 0:
                interfaces = (
                    self.kubecli.get_lib_kubernetes().list_pod_network_interfaces(
                        target, self.config.namespace
                    )
                )

                if len(interfaces) == 0:
                    log_error(
                        "no network interface found in pod, impossible to execute the network filter scenario",
                        parallel,
                        pod_name,
                    )
                    return
                log_info(
                    f"detected network interfaces: {','.join(interfaces)}",
                    parallel,
                    pod_name,
                )
            else:
                interfaces = self.config.interfaces

            container_ids = self.kubecli.get_lib_kubernetes().get_container_ids(
                target, self.config.namespace
            )

            if len(container_ids) == 0:
                raise Exception(
                    f"impossible to resolve container id for pod {target} namespace {self.config.namespace}"
                )

            log_info(f"targeting container {container_ids[0]}", parallel, pod_name)

            pids = self.kubecli.get_lib_kubernetes().get_pod_pids(
                base_pod_name=pod_name,
                base_pod_namespace=self.config.namespace,
                base_pod_container_name=container_name,
                pod_name=target,
                pod_namespace=self.config.namespace,
                pod_container_id=container_ids[0],
            )

            if not pids:
                raise Exception(f"impossible to resolve pid for pod {target}")

            log_info(
                f"resolved pids {pids} in node {pod_info.nodeName} for pod {target}",
                parallel,
                pod_name,
            )

            input_rules, output_rules = generate_namespaced_rules(
                interfaces, self.config, pids
            )

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
                pod_name,
            )

            time.sleep(self.config.test_duration)

            log_info("removing iptables rules", parallel, pod_name)

            clean_network_rules_namespaced(
                self.kubecli.get_lib_kubernetes(),
                input_rules,
                output_rules,
                pod_name,
                self.config.namespace,
                pids,
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

    def get_config(self) -> (NetworkChaosScenarioType, BaseNetworkChaosConfig):
        return NetworkChaosScenarioType.Pod, self.config

    def get_targets(self) -> list[str]:
        if not self.config.namespace:
            raise Exception("namespace not specified, aborting")
        if self.base_network_config.label_selector:
            return self.kubecli.get_lib_kubernetes().list_pods(
                self.config.namespace, self.config.label_selector
            )
        else:
            if not self.config.target:
                raise Exception(
                    "neither node selector nor node_name (target) specified, aborting."
                )
            if not self.kubecli.get_lib_kubernetes().check_if_pod_exists(
                self.config.target, self.config.namespace
            ):
                raise Exception(
                    f"pod {self.config.target} not found in namespace {self.config.namespace}"
                )

            return [self.config.target]
