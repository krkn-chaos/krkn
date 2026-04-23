import queue
import time
from typing import Tuple

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_random_string

from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosScenarioType,
    BaseNetworkChaosConfig,
    InterfaceDownConfig,
)
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.modules.utils import (
    log_info,
    log_error,
    deploy_network_chaos_ng_pod,
    get_pod_default_interface,
)


class NodeInterfaceDownModule(AbstractNetworkChaosModule):
    config: InterfaceDownConfig
    kubecli: KrknTelemetryOpenshift

    def __init__(self, config: InterfaceDownConfig, kubecli: KrknTelemetryOpenshift):
        super().__init__(config, kubecli)
        self.config = config

    def run(self, target: str, error_queue: queue.Queue = None):
        parallel = False
        if error_queue:
            parallel = True
        try:
            pod_name = f"node-iface-down-{get_random_string(5)}"

            log_info(
                f"creating workload pod on node {target} to bring interface(s) down",
                parallel,
                target,
            )

            deploy_network_chaos_ng_pod(
                self.config,
                target,
                pod_name,
                self.kubecli.get_lib_kubernetes(),
            )

            if len(self.config.interfaces) == 0:
                interfaces = [
                    get_pod_default_interface(
                        pod_name,
                        self.config.namespace,
                        self.kubecli.get_lib_kubernetes(),
                    )
                ]
                if not interfaces[0]:
                    log_error(
                        "could not detect default network interface, aborting",
                        parallel,
                        target,
                    )
                    self.kubecli.get_lib_kubernetes().delete_pod(
                        pod_name, self.config.namespace
                    )
                    return
                log_info(
                    f"detected default interface: {interfaces[0]}", parallel, target
                )
            else:
                interfaces = self.config.interfaces

            log_info(
                f"scheduling recovery and bringing down interface(s): {', '.join(interfaces)} on node {target}",
                parallel,
                target,
            )

            # Pre-schedule recovery as a background process on the node before bringing
            # the interface down. Once the interface is down the node loses connectivity
            # to the control plane, so exec_cmd_in_pod can no longer reach the pod.
            # The background process runs entirely on the node and fires regardless of
            # control-plane connectivity.
            recovery_cmds = " && ".join(
                [f"ip link set {iface} up" for iface in interfaces]
            )
            down_cmds = " && ".join(
                [f"ip link set {iface} down" for iface in interfaces]
            )
            cmd = f"(sleep {self.config.test_duration} && {recovery_cmds}) & {down_cmds}"
            self.kubecli.get_lib_kubernetes().exec_cmd_in_pod(
                [cmd], pod_name, self.config.namespace
            )
            log_info(
                f"interface(s) {', '.join(interfaces)} are down on node {target}, "
                f"recovery scheduled in {self.config.test_duration}s",
                parallel,
                target,
            )

            log_info(
                f"waiting {self.config.test_duration} seconds for interface(s) to recover",
                parallel,
                target,
            )
            time.sleep(self.config.test_duration)

            log_info(
                f"waiting for node {target} to become Ready after interface recovery",
                parallel,
                target,
            )
            node_ready = False
            for _ in range(60):
                time.sleep(5)
                ready_nodes = self.kubecli.get_lib_kubernetes().list_ready_nodes()
                if target in ready_nodes:
                    node_ready = True
                    break

            if not node_ready:
                log_error(
                    f"node {target} did not become Ready within 5 minutes after interface recovery",
                    parallel,
                    target,
                )
            else:
                log_info(f"node {target} is Ready", parallel, target)

            if self.config.recovery_time > 0:
                log_info(
                    f"waiting {self.config.recovery_time} seconds for node to stabilize",
                    parallel,
                    target,
                )
                time.sleep(self.config.recovery_time)

            self.kubecli.get_lib_kubernetes().delete_pod(
                pod_name, self.config.namespace
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
