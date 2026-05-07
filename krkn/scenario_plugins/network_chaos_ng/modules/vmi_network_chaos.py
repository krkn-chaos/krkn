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
import dataclasses
import queue
import re
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
    log_error,
    deploy_network_chaos_ng_pod,
    find_virt_launcher_netns_pid,
    get_vmi_tap_interface,
)
from krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos import (
    common_set_limit_rules,
    common_delete_limit_rules,
)


class VmiNetworkChaosModule(AbstractNetworkChaosModule):

    def __init__(self, config: NetworkChaosConfig, kubecli: KrknTelemetryOpenshift):
        super().__init__(config, kubecli)
        self.config = config

    def _rollback(
        self,
        namespace: str,
        network_chaos_pod_name: str,
        netns_pid: str = None,
        iface: str = None,
        parallel: bool = False,
        vmi_name: str = "",
    ):
        if netns_pid and iface:
            common_delete_limit_rules(
                self.config.egress,
                self.config.ingress,
                [iface],
                network_chaos_pod_name,
                namespace,
                self.kubecli.get_lib_kubernetes(),
                [netns_pid],
                parallel,
                vmi_name,
            )
        self.kubecli.get_lib_kubernetes().delete_pod(
            network_chaos_pod_name, namespace
        )

    def run(self, target: str, error_queue: queue.Queue = None):
        # target is "namespace/vmi-name" as produced by get_targets()
        parallel = False
        if error_queue:
            parallel = True

        network_chaos_pod_name = None
        netns_pid = None
        iface = None

        try:
            namespace, vmi_name = target.split("/", 1)
            # Create a scoped config with the resolved namespace so that all
            # Kubernetes calls use the actual namespace, not the regex pattern.
            scoped_config = dataclasses.replace(self.config, namespace=namespace)
            network_chaos_pod_name = f"vmi-network-chaos-{get_random_string(5)}"
            container_name = f"fedora-container-{get_random_string(5)}"

            log_info(
                f"creating workload to inject network chaos in VMI {vmi_name} "
                f"latency:{str(self.config.latency) if self.config.latency else '0'}, "
                f"loss:{str(self.config.loss) if self.config.loss else '0'}, "
                f"bandwidth:{str(self.config.bandwidth) if self.config.bandwidth else '0'}",
                parallel,
                network_chaos_pod_name,
            )

            vmi = self.kubecli.get_lib_kubernetes().get_vmi(vmi_name, namespace)
            if not vmi:
                raise Exception(
                    f"VMI {vmi_name} not found in namespace {namespace}"
                )

            node_name = vmi.get("status", {}).get("nodeName")
            if not node_name:
                raise Exception(
                    f"unable to determine node for VMI {vmi_name} in namespace {namespace}; "
                    "VMI may not be in Running phase"
                )

            log_info(
                f"VMI {vmi_name} is running on node {node_name}",
                parallel,
                network_chaos_pod_name,
            )

            # The virt-launcher pod carries the VMI's network namespace.
            virt_launcher_pods = self.kubecli.get_lib_kubernetes().list_pods(
                namespace, label_selector=f"vm.kubevirt.io/name={vmi_name}"
            )
            if not virt_launcher_pods:
                raise Exception(
                    f"no virt-launcher pod found for VMI {vmi_name} in namespace {namespace}"
                )
            virt_launcher_pod_name = virt_launcher_pods[0]

            log_info(
                f"resolved virt-launcher pod {virt_launcher_pod_name} for VMI {vmi_name}",
                parallel,
                network_chaos_pod_name,
            )

            # Deploy the privileged chaos pod onto the VMI's node.
            # hostPID=True (via template) allows nsenter into the virt-launcher's
            # network namespace using any of the compute container's host PIDs.
            deploy_network_chaos_ng_pod(
                scoped_config,
                node_name,
                network_chaos_pod_name,
                self.kubecli.get_lib_kubernetes(),
                container_name,
                host_network=False,
            )

            # Prefer the 'compute' container (the QEMU process in KubeVirt).
            # 'virt-launcher' is a sidecar monitor that may not be running.
            pod_info = self.kubecli.get_lib_kubernetes().get_pod_info(
                virt_launcher_pod_name, namespace
            )
            if not pod_info:
                raise Exception(
                    f"impossible to retrieve info for virt-launcher pod "
                    f"{virt_launcher_pod_name} in namespace {namespace}"
                )

            target_container_id = None
            for container in pod_info.containers:
                if container.name == "compute" and container.ready and container.containerId:
                    target_container_id = re.sub(r".*://", "", container.containerId)
                    break
            if not target_container_id:
                raise Exception(
                    f"compute container in virt-launcher pod {virt_launcher_pod_name} "
                    f"in namespace {namespace} is not ready"
                )

            log_info(
                f"targeting compute container {target_container_id}",
                parallel,
                network_chaos_pod_name,
            )

            pids = self.kubecli.get_lib_kubernetes().get_pod_pids(
                base_pod_name=network_chaos_pod_name,
                base_pod_namespace=namespace,
                base_pod_container_name=container_name,
                pod_name=virt_launcher_pod_name,
                pod_namespace=namespace,
                pod_container_id=target_container_id,
            )
            if not pids:
                raise Exception(
                    f"impossible to resolve PIDs for virt-launcher pod {virt_launcher_pod_name}"
                )

            log_info(
                f"resolved PIDs {pids} on node {node_name} for VMI {vmi_name}",
                parallel,
                network_chaos_pod_name,
            )

            # Not all PIDs are in the virt-launcher's netns — find the right one.
            netns_pid = find_virt_launcher_netns_pid(
                network_chaos_pod_name,
                namespace,
                pids,
                self.kubecli.get_lib_kubernetes(),
            )
            if not netns_pid:
                raise Exception(
                    f"could not find a PID in the virt-launcher netns for VMI {vmi_name}; "
                    "none of the compute container PIDs contain tap"
                )

            log_info(
                f"using PID {netns_pid} for netns entry (virt-launcher netns confirmed via tap)",
                parallel,
                network_chaos_pod_name,
            )

            # Target the tap interface rather than the bridge slave (ovn-udn1-nic).
            # Shaping the bridge slave also affects OVN's BFD heartbeats and can
            # cause node-wide reconvergence; the tap device only connects to QEMU.
            if len(scoped_config.interfaces) == 0:
                iface = get_vmi_tap_interface(
                    network_chaos_pod_name,
                    namespace,
                    netns_pid,
                    self.kubecli.get_lib_kubernetes(),
                )
                if not iface:
                    log_error(
                        "could not detect tap interface in virt-launcher netns; "
                        "impossible to execute the VMI network chaos scenario",
                        parallel,
                        network_chaos_pod_name,
                    )
                    self._rollback(namespace, network_chaos_pod_name)
                    return
            else:
                iface = scoped_config.interfaces[0]

            log_info(
                f"targeting tap interface: {iface}",
                parallel,
                network_chaos_pod_name,
            )

            # Apply tc-based shaping (HTB + netem) inside the virt-launcher netns.
            # Passing pids=[netns_pid] wraps each tc command with nsenter so it
            # targets the VMI's network namespace, not the host or chaos pod netns.
            common_set_limit_rules(
                self.config.egress,
                self.config.ingress,
                [iface],
                self.config.bandwidth,
                self.config.latency,
                self.config.loss,
                parallel,
                vmi_name,
                self.kubecli.get_lib_kubernetes(),
                network_chaos_pod_name,
                namespace,
                pids=[netns_pid],
            )

            log_info(
                f"waiting {self.config.test_duration} seconds before removing tc rules",
                parallel,
                network_chaos_pod_name,
            )

            time.sleep(self.config.test_duration)

            log_info("removing tc rules", parallel, network_chaos_pod_name)

            self._rollback(namespace, network_chaos_pod_name, netns_pid, iface, parallel, vmi_name)

        except Exception as e:
            if network_chaos_pod_name:
                self._rollback(
                    namespace, network_chaos_pod_name, netns_pid, iface, parallel, vmi_name
                )
            if error_queue is None:
                raise e
            else:
                error_queue.put(str(e))

    def get_config(self) -> Tuple[NetworkChaosScenarioType, BaseNetworkChaosConfig]:
        return NetworkChaosScenarioType.VMI, self.config

    def get_targets(self) -> list[str]:
        if not self.config.namespace:
            raise Exception("namespace not specified for VMI scenario, aborting")
        name_regex = self.config.target if self.config.target else ".*"
        label_selector = self.config.label_selector or None

        vmis = self.kubecli.get_lib_kubernetes().get_vmis(
            name_regex, self.config.namespace, label_selector=label_selector
        )
        return [
            f"{vmi['metadata']['namespace']}/{vmi['metadata']['name']}"
            for vmi in vmis
            if re.match(name_regex, vmi.get("metadata", {}).get("name", ""))
            and re.match(
                self.config.namespace,
                vmi.get("metadata", {}).get("namespace", ""),
            )
        ]
