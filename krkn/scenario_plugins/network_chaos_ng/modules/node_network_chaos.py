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
    log_warning,
)
from krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos import (
    common_set_limit_rules,
    common_delete_limit_rules,
    node_qdisc_is_simple,
)


class NodeNetworkChaosModule(AbstractNetworkChaosModule):

    def __init__(self, config: NetworkChaosConfig, kubecli: KrknTelemetryOpenshift):
        super().__init__(config, kubecli)
        self.config = config

    def run(self, target: str, error_queue: queue.Queue = None):
        parallel = False
        if error_queue:
            parallel = True
        try:
            network_chaos_pod_name = f"node-network-chaos-{get_random_string(5)}"
            container_name = f"fedora-container-{get_random_string(5)}"

            log_info(
                f"creating workload to inject network chaos in node {target} network"
                f"latency:{str(self.config.latency) if self.config.latency else '0'}, "
                f"packet drop:{str(self.config.loss) if self.config.loss else '0'} "
                f"bandwidth restriction:{str(self.config.bandwidth) if self.config.bandwidth else '0'} ",
                parallel,
                network_chaos_pod_name,
            )

            _, interfaces = setup_network_chaos_ng_scenario(
                self.config,
                target,
                network_chaos_pod_name,
                container_name,
                self.kubecli.get_lib_kubernetes(),
                target,
                parallel,
                True,
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

            log_info(
                f"targeting node {target}",
                parallel,
                network_chaos_pod_name,
            )

            complex_config_interfaces = []
            for interface in interfaces:
                is_simple = node_qdisc_is_simple(
                    self.kubecli.get_lib_kubernetes(),
                    network_chaos_pod_name,
                    self.config.namespace,
                    interface,
                )
                if not is_simple:
                    complex_config_interfaces.append(interface)

            if len(complex_config_interfaces) > 0 and not self.config.force:
                log_warning(
                    f"node already has tc rules set for {','.join(complex_config_interfaces)}, this action might damage the cluster,"
                    "if you want to continue set `force` to True in the node network "
                    "chaos scenario config file and try again"
                )
            else:
                if len(complex_config_interfaces) > 0 and self.config.force:
                    log_warning(
                        f"you are forcing node network configuration override for {','.join(complex_config_interfaces)},"
                        "this action might lead to unpredictable node behaviour, "
                        "you're doing it in your own responsibility"
                        "waiting 10 seconds before continuing"
                    )
                    time.sleep(10)
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
                    None,
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
                    None,
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
        return NetworkChaosScenarioType.Node, self.config

    def get_targets(self) -> list[str]:
        return self.get_node_targets(self.config)
