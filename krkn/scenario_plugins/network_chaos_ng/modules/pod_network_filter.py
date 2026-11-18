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
    NetworkChaosScenarioType,
    BaseNetworkChaosConfig,
    NetworkFilterConfig,
)
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.modules.utils import (
    log_info,
    log_error,
    deploy_network_chaos_ng_pod,
    get_pod_default_interface,
    setup_network_chaos_ng_scenario,
)
from krkn.scenario_plugins.network_chaos_ng.modules.utils_network_filter import (
    apply_network_rules,
    clean_network_rules_namespaced,
    generate_namespaced_rules,
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

            container_ids, interfaces = setup_network_chaos_ng_scenario(
                self.config,
                pod_info.nodeName,
                pod_name,
                container_name,
                self.kubecli.get_lib_kubernetes(),
                target,
                parallel,
                False,
            )

            if len(self.config.interfaces) == 0:
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

            pids = self._resolve_target_pids(
                target, container_ids[0], pod_name, container_name, parallel
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

            # re-resolve the target PIDs at cleanup time: the target
            # container may have restarted during the chaos window,
            # leaving the apply-time PIDs dead while the network
            # namespace (and the applied rules) survives
            cleanup_pids = self._resolve_target_pids(
                target, container_ids[0], pod_name, container_name, parallel
            )
            if not cleanup_pids:
                # target pod or container is gone: its network namespace
                # was destroyed with it, so the rules are gone too
                log_info(
                    f"target pod {target} no longer has live containers, "
                    f"its network namespace (and the applied rules) is gone",
                    parallel,
                    pod_name,
                )
            else:
                if cleanup_pids != pids:
                    log_info(
                        f"target container restarted during the chaos window, "
                        f"resolved fresh pids {cleanup_pids} for cleanup "
                        f"(apply-time pids {pids} are stale)",
                        parallel,
                        pod_name,
                    )
                clean_network_rules_namespaced(
                    self.kubecli.get_lib_kubernetes(),
                    input_rules,
                    output_rules,
                    pod_name,
                    self.config.namespace,
                    cleanup_pids,
                )

            # verify the rules are actually gone before reporting success
            self._verify_rules_removed(
                target, cleanup_pids, pod_name, container_name, parallel
            )

            self.kubecli.get_lib_kubernetes().delete_pod(
                pod_name, self.config.namespace
            )

        except Exception as e:
            if error_queue is None:
                raise e
            else:
                error_queue.put(str(e))

    def _resolve_target_pids(
        self,
        target: str,
        container_id: str,
        pod_name: str,
        container_name: str,
        parallel: bool,
    ) -> list[str]:
        """
        Resolves the PIDs of the target pod's container running in a
        network namespace other than the node host namespace, so that
        nsenter-based rule application can never touch the host network
        namespace (supervisor processes like conmon match the container-id
        cgroup grep but live in the host netns).

        :return: the filtered PID list, None when the pod or the
            container does not exist anymore.
        """
        kubecli = self.kubecli.get_lib_kubernetes()
        if not kubecli.check_if_pod_exists(target, self.config.namespace):
            return None

        pids = kubecli.get_pod_pids(
            base_pod_name=pod_name,
            base_pod_namespace=self.config.namespace,
            base_pod_container_name=container_name,
            pod_name=target,
            pod_namespace=self.config.namespace,
            pod_container_id=container_id,
        )
        if not pids:
            return None

        # defensive: filter out host-netns PIDs in case the installed
        # krkn-lib version does not do it yet (krkn-lib fix pending)
        filter_cmd = (
            'for p in {}; do '
            '[ "$(readlink /proc/$p/ns/net 2>/dev/null)" '
            '!= "$(readlink /proc/1/ns/net 2>/dev/null)" ] && echo $p; done'
        ).format(" ".join(pids))
        filtered = kubecli.exec_cmd_in_pod(
            [filter_cmd], pod_name, self.config.namespace, container_name
        )
        if filtered:
            filtered = list(filter(None, filtered.split("\n")))
            if filtered:
                return filtered
        return pids

    def _verify_rules_removed(
        self,
        target: str,
        cleanup_pids: list[str],
        pod_name: str,
        container_name: str,
        parallel: bool,
    ):
        """
        Verifies that no DROP rule is left behind in the target network
        namespace after cleanup, and fails loudly with the surviving
        rules dumped for manual removal.
        """
        if not cleanup_pids:
            return
        kubecli = self.kubecli.get_lib_kubernetes()
        verify_cmd = (
            f"nsenter --target {cleanup_pids[0]} --net -- "
            f"iptables-save 2>/dev/null | grep -E '^-A (INPUT|OUTPUT).*DROP'"
        )
        surviving = kubecli.exec_cmd_in_pod(
            [verify_cmd], pod_name, self.config.namespace, container_name
        )
        if surviving and surviving.strip():
            raise Exception(
                f"iptables DROP rules survived cleanup in the network "
                f"namespace of pod {target} namespace {self.config.namespace}. "
                f"Surviving rules:\n{surviving}\n"
                f"Manual removal may be required (e.g. nsenter --target "
                f"{cleanup_pids[0]} --net -- iptables -D ...)."
            )
        log_info(
            f"verified no DROP rules left in the network namespace of pod {target}",
            parallel,
            pod_name,
        )


    def __init__(self, config: NetworkFilterConfig, kubecli: KrknTelemetryOpenshift):
        super().__init__(config, kubecli)
        self.config = config

    def get_config(self) -> Tuple[NetworkChaosScenarioType, BaseNetworkChaosConfig]:
        return NetworkChaosScenarioType.Pod, self.config

    def get_targets(self) -> list[str]:
        return self.get_pod_targets(self.config)
