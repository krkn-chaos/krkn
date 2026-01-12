import queue
import time
from typing import Tuple

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_random_string

from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosScenarioType,
    BaseNetworkChaosConfig,
    NetworkChaosConfig,
)
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.modules.utils import (
    log_info,
    setup_network_chaos_ng_scenario,
    log_error,
)
from krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos import (
    common_set_limit_rules,
    common_delete_limit_rules,
)


class PodNetworkChaosModule(AbstractNetworkChaosModule):

    def __init__(self, config: NetworkChaosConfig, kubecli: KrknTelemetryOpenshift):
        super().__init__(config, kubecli)
        self.config = config

    def run(self, target: str, error_queue: queue.Queue = None):
        parallel = False
        if error_queue:
            parallel = True
        try:
            network_chaos_pod_name = f"pod-network-chaos-{get_random_string(5)}"
            container_name = f"fedora-container-{get_random_string(5)}"
            pod_info = self.kubecli.get_lib_kubernetes().get_pod_info(
                target, self.config.namespace
            )

            log_info(
                f"creating workload to inject network chaos in pod {target} network"
                f"latency:{str(self.config.latency) if self.config.latency else '0'}, "
                f"packet drop:{str(self.config.loss) if self.config.loss else '0'} "
                f"bandwidth restriction:{str(self.config.bandwidth) if self.config.bandwidth else '0'} ",
                parallel,
                network_chaos_pod_name,
            )

            if not pod_info:
                raise Exception(
                    f"impossible to retrieve infos for pod {target} namespace {self.config.namespace}"
                )

            container_ids, interfaces = setup_network_chaos_ng_scenario(
                self.config,
                pod_info.nodeName,
                network_chaos_pod_name,
                container_name,
                self.kubecli.get_lib_kubernetes(),
                target,
                parallel,
                False,
            )

            if len(self.config.interfaces) == 0:
                if len(interfaces) == 0:
                    log_error(
                        "no network interface found in pod, impossible to execute the network chaos scenario",
                        parallel,
                        network_chaos_pod_name,
                    )
                    return
                log_info(
                    f"detected network interfaces: {','.join(interfaces)}",
                    parallel,
                    network_chaos_pod_name,
                )
            else:
                interfaces = self.config.interfaces

            if len(container_ids) == 0:
                raise Exception(
                    f"impossible to resolve container id for pod {target} namespace {self.config.namespace}"
                )

            log_info(
                f"targeting container {container_ids[0]}",
                parallel,
                network_chaos_pod_name,
            )

            pids = self.kubecli.get_lib_kubernetes().get_pod_pids(
                base_pod_name=network_chaos_pod_name,
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
                network_chaos_pod_name,
            )

            common_set_limit_rules(
                self.config.egress,
                self.config.ingress,
                interfaces,
                self.config.bandwidth,
                self.config.latency,
                self.config.loss,
                parallel,
                network_chaos_pod_name,
                self.kubecli.get_lib_kubernetes(),
                network_chaos_pod_name,
                self.config.namespace,
                pids,
            )

            time.sleep(self.config.test_duration)

            log_info("removing tc rules", parallel, network_chaos_pod_name)

            common_delete_limit_rules(
                self.config.egress,
                self.config.ingress,
                interfaces,
                network_chaos_pod_name,
                self.config.namespace,
                self.kubecli.get_lib_kubernetes(),
                pids,
                parallel,
                network_chaos_pod_name,
            )

            self.kubecli.get_lib_kubernetes().delete_pod(
                network_chaos_pod_name, self.config.namespace
            )

        except Exception as e:
            if error_queue is None:
                raise e
            else:
                error_queue.put(str(e))

    def get_config(self) -> Tuple[NetworkChaosScenarioType, BaseNetworkChaosConfig]:
        return NetworkChaosScenarioType.Pod, self.config

    def get_targets(self) -> list[str]:
        return self.get_pod_targets(self.config)
