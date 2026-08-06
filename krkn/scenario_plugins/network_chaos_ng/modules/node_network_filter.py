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
from krkn.scenario_plugins.network_chaos_ng.modules.utils import (
    log_info,
    deploy_network_chaos_ng_pod,
    get_pod_default_interface,
)

from krkn.scenario_plugins.network_chaos_ng.modules.utils_network_filter import (
    apply_network_rules,
    clean_network_rules,
    generate_rules,
)


class NodeNetworkFilterModule(AbstractNetworkChaosModule):
    config: NetworkFilterConfig
    kubecli: KrknTelemetryOpenshift

    def _rollback(
        self,
        pod_name: str,
        input_rules: list = None,
        output_rules: list = None,
        rules_applied: bool = False,
    ):
        if rules_applied:
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

    def run(self, target: str, error_queue: queue.Queue = None):
        parallel = False
        if error_queue:
            parallel = True
        pod_name = None
        input_rules = None
        output_rules = None
        rules_applied = False
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
            rules_applied = True

            log_info(
                f"waiting {self.config.test_duration} seconds before removing the iptables rules",
                parallel,
                target,
            )

            time.sleep(self.config.test_duration)

            log_info("removing iptables rules", parallel, target)

            # iptables cleanup is destructive and not idempotent: disarm the
            # rollback guard *before* cleaning so that if cleanup or pod deletion
            # fails, the exception handler cannot run a second, destructive
            # cleanup pass. Cleanup stays inside `try`, so its failures flow
            # through the existing error_queue / raise handling.
            rules_applied = False
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
            if pod_name:
                try:
                    self._rollback(
                        pod_name, input_rules, output_rules, rules_applied
                    )
                except Exception:
                    # best-effort cleanup: never mask or drop the original
                    # scenario error (preserves the error_queue / raise contract)
                    pass
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
        return self.get_node_targets(self.config)
