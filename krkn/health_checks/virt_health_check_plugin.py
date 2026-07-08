# Copyright 2026 The Krkn Authors
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
"""
Virtualization Health Check Plugin

This plugin provides health checking for KubeVirt virtual machines and VMIs
during chaos engineering experiments.

Example configuration in config.yaml:
kubevirt_checks:
    type: virt_health_check
    namespace: "default"
    name: ".*"                    # optional VMI name regex pattern; matches all if omitted
    label_selector: ""            # optional label selector (e.g. "app=myvm"); if set, name is not required
    interval: 2                   # Check interval in seconds
    disconnected: false           # Use disconnected SSH access
    only_failures: false          # Only report failures
    ssh_node: ""                  # Common SSH node for fallback
    node_names: ""                # Comma-separated node names to filter
    exit_on_failure: false        # Exit if failures persist at end
"""

import logging
import math
import queue
import threading
import time
from datetime import datetime
from typing import Any

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry.models import VirtCheck
from krkn_lib.utils.functions import get_yaml_item_value
from krkn.health_checks.abstract_health_check_plugin import AbstractHealthCheckPlugin
from krkn.invoke.command import invoke_no_exit
from krkn.scenario_plugins.kubevirt_vm_outage.kubevirt_vm_outage_scenario_plugin import (
    KubevirtVmOutageScenarioPlugin,
)


class VirtHealthCheckPlugin(AbstractHealthCheckPlugin):
    """
    KubeVirt VM health check plugin that monitors virtual machine accessibility
    during chaos experiments.

    This plugin supports both virtctl-based and disconnected SSH-based access checks,
    tracks VM status changes, and collects telemetry about VM health over time.
    """

    def __init__(
        self,
        health_check_type: str = "virt_health_check",
        iterations: int = 1,
        krkn_lib: KrknKubernetes = None,
        **kwargs
    ):
        """
        Initializes the virt health check plugin.

        :param health_check_type: the health check type identifier
        :param iterations: the number of chaos iterations to monitor
        :param krkn_lib: KrknKubernetes client instance
        :param kwargs: additional keyword arguments
        """
        super().__init__(health_check_type)
        self.iterations = iterations
        self.current_iterations = 0
        self.krkn_lib = krkn_lib
        self.iteration_lock = threading.Lock()
        self.threads = []
        self.vm_list = []
        self.batch_size = 0
        self.threads_limit = kwargs.get("threads_limit", 20)

        # Configuration attributes (will be set in run_health_check)
        self.namespace = ""
        self.disconnected = False
        self.only_failures = False
        self.interval = 2
        self.ssh_node = ""
        self.node_names = ""
        self.exit_on_failure = False
        self.kube_vm_plugin = None
        self.vmis_list = []

    def get_health_check_types(self) -> list[str]:
        """
        Returns the health check types this plugin handles.

        :return: list of health check type identifiers
        """
        return ["virt_health_check", "kubevirt_health_check", "vm_health_check"]

    def get_config_key(self) -> str:
        """
        Returns the top-level config.yaml key this plugin reads from.

        :return: config key string
        """
        return "kubevirt_checks"

    def manages_own_threads(self) -> bool:
        """
        Virt plugin spawns its own worker threads internally via run_health_check().
        The factory calls run_health_check() directly and uses thread_join() to wait.

        :return: True
        """
        return True

    def increment_iterations(self) -> None:
        """
        Thread-safe method to increment current_iterations.

        :return: None
        """
        with self.iteration_lock:
            self.current_iterations += 1

    def _initialize_from_config(self, config: dict[str, Any]) -> bool:
        """
        Initialize plugin from configuration dictionary.

        :param config: configuration dictionary
        :return: True if initialization successful, False otherwise
        """
        self.namespace = get_yaml_item_value(config, "namespace", "")
        self.disconnected = get_yaml_item_value(config, "disconnected", False)
        self.only_failures = get_yaml_item_value(config, "only_failures", False)
        self.interval = get_yaml_item_value(config, "interval", 2)
        self.ssh_node = get_yaml_item_value(config, "ssh_node", "")
        self.node_names = get_yaml_item_value(config, "node_names", "")
        self.exit_on_failure = get_yaml_item_value(config, "exit_on_failure", False)
        vmi_name_match = get_yaml_item_value(config, "name", None) or ".*"
        label_selector = get_yaml_item_value(config, "label_selector", None) or None

        if self.namespace == "":
            logging.info("kubevirt checks config namespace is not defined, skipping them")
            return False

        try:
            self.kube_vm_plugin = KubevirtVmOutageScenarioPlugin()
            self.kube_vm_plugin.init_clients(k8s_client=self.krkn_lib)
            self.vmis_list = self.kube_vm_plugin.k8s_client.get_vmis(
                vmi_name_match, self.namespace, label_selector=label_selector
            )
        except Exception as e:
            logging.error(f"Virt Check init exception: {str(e)}")
            return False

        # Build VM list from VMIs
        node_name_list = [
            node_name for node_name in self.node_names.split(",") if node_name
        ]
        for vmi in self.vmis_list:
            node_name = vmi.get("status", {}).get("nodeName")
            vmi_name = vmi.get("metadata", {}).get("name")
            interfaces = vmi.get("status", {}).get("interfaces", [])

            if not interfaces:
                logging.debug(f"VMI {vmi_name} has no network interfaces, skipping")
                continue

            ip_address = interfaces[0].get("ipAddress")
            namespace = vmi.get("metadata", {}).get("namespace")

            if not node_name_list or node_name in node_name_list:
                self.vm_list.append(
                    VirtCheck(
                        {
                            "vm_name": vmi_name,
                            "ip_address": ip_address,
                            "namespace": namespace,
                            "node_name": node_name,
                            "new_ip_address": "",
                        }
                    )
                )

        self.batch_size = math.ceil(len(self.vm_list) / self.threads_limit)
        return True

    def check_disconnected_access(
        self, ip_address: str, worker_name: str = "", vmi_name: str = ""
    ) -> tuple[bool, str | None, str | None]:
        """
        Check VM accessibility via disconnected SSH access through worker nodes.

        :param ip_address: VM IP address
        :param worker_name: worker node name
        :param vmi_name: VMI name
        :return: tuple of (success, new_ip_address, new_node_name)
        """
        virtctl_vm_cmd = f"ssh core@{worker_name} -o ConnectTimeout=5 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@{ip_address}'"

        all_out = invoke_no_exit(virtctl_vm_cmd)
        logging.debug(
            f"Checking disconnected access for {ip_address} on {worker_name} output: {all_out}"
        )

        virtctl_vm_cmd = f"ssh core@{worker_name} -o ConnectTimeout=5 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@{ip_address} 2>&1 | grep Permission' && echo 'True' || echo 'False'"
        output = invoke_no_exit(virtctl_vm_cmd)

        if "True" in output:
            logging.debug(
                f"Disconnected access for {ip_address} on {worker_name} is successful: {output}"
            )
            return True, None, None
        else:
            logging.debug(
                f"Disconnected access for {ip_address} on {worker_name} failed: {output}"
            )
            vmi = self.kube_vm_plugin.get_vmi(vmi_name, self.namespace)
            interfaces = vmi.get("status", {}).get("interfaces", [])
            new_ip_address = interfaces[0].get("ipAddress") if interfaces else None
            new_node_name = vmi.get("status", {}).get("nodeName")

            # Check if VM restarted with new IP
            if new_ip_address != ip_address:
                virtctl_vm_cmd = f"ssh core@{worker_name} -o ConnectTimeout=5 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@{new_ip_address} 2>&1 | grep Permission' && echo 'True' || echo 'False'"
                new_output = invoke_no_exit(virtctl_vm_cmd)
                logging.debug(
                    f"Disconnected access for {ip_address} on {worker_name}: {new_output}"
                )
                if "True" in new_output:
                    return True, new_ip_address, None

            # Check if VM migrated to new node
            if new_node_name != worker_name:
                virtctl_vm_cmd = f"ssh core@{new_node_name} -o ConnectTimeout=5 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@{new_ip_address} 2>&1 | grep Permission' && echo 'True' || echo 'False'"
                new_output = invoke_no_exit(virtctl_vm_cmd)
                logging.debug(
                    f"Disconnected access for {ip_address} on {new_node_name}: {new_output}"
                )
                if "True" in new_output:
                    return True, new_ip_address, new_node_name

            # Try common SSH node as fallback
            if self.ssh_node:
                virtctl_vm_cmd = f"ssh core@{self.ssh_node} -o ConnectTimeout=5 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@{new_ip_address} 2>&1 | grep Permission' && echo 'True' || echo 'False'"
                new_output = invoke_no_exit(virtctl_vm_cmd)
                logging.debug(
                    f"Disconnected access for {new_ip_address} on {self.ssh_node}: {new_output}"
                )
                if "True" in new_output:
                    return True, new_ip_address, None

        return False, None, None

    def _get_ssh_status(self, vm) -> bool:
        """
        Check SSH accessibility for a VM, updating vm.new_ip_address and vm.node_name
        in-place if the VM has migrated.

        :param vm: VirtCheck object representing the VM
        :return: True if SSH access succeeded, False otherwise
        """
        if not self.disconnected:
            return self.get_vm_access(vm.vm_name, vm.namespace)

        ip = vm.new_ip_address or vm.ip_address
        vm_status, new_ip_address, new_node_name = self.check_disconnected_access(
            ip, vm.node_name, vm.vm_name
        )
        # Only update tracked addresses on first migration discovery
        if not vm.new_ip_address:
            if new_ip_address and vm.ip_address != new_ip_address:
                vm.new_ip_address = new_ip_address
            if new_node_name and vm.node_name != new_node_name:
                vm.node_name = new_node_name
        return vm_status

    def check_vmi_ready(self, vmi_name: str, namespace: str) -> bool:
        """
        Check if a VMI is in Running phase with a Ready=True condition.

        :param vmi_name: VMI name
        :param namespace: namespace
        :return: True if VMI is ready, False otherwise
        """
        try:
            vmi = self.krkn_lib.get_vmi(vmi_name, namespace)
            if vmi is None:
                return False
            phase = vmi.get("status", {}).get("phase", "")
            if phase != "Running":
                logging.debug(f"VMI {vmi_name} phase is '{phase}', not Running")
                return False
            for cond in vmi.get("status", {}).get("conditions", []):
                if cond.get("type") == "Ready" and cond.get("status") == "True":
                    return True
            logging.debug(f"VMI {vmi_name} has no Ready=True condition")
            return False
        except Exception:
            logging.exception(f"Exception checking VMI ready state for {vmi_name}")
            return False

    def get_vm_access(self, vm_name: str = "", namespace: str = "") -> bool:
        """
        Check VM accessibility using virtctl protocol.

        :param vm_name: VM name
        :param namespace: namespace
        :return: True if accessible, False otherwise
        """
        virtctl_vm_cmd = f"virtctl ssh --local-ssh-opts='-o BatchMode=yes' --local-ssh-opts='-o PasswordAuthentication=no' --local-ssh-opts='-o ConnectTimeout=5' root@vmi/{vm_name} -n {namespace} 2>&1 |egrep 'denied|verification failed'  && echo 'True' || echo 'False'"
        check_virtctl_vm_cmd = f"virtctl ssh --local-ssh-opts='-o BatchMode=yes' --local-ssh-opts='-o PasswordAuthentication=no' --local-ssh-opts='-o ConnectTimeout=5' root@{vm_name} -n {namespace} 2>&1 |egrep 'denied|verification failed'  && echo 'True' || echo 'False'"

        if "True" in invoke_no_exit(check_virtctl_vm_cmd):
            return True
        else:
            second_invoke = invoke_no_exit(virtctl_vm_cmd)
            if "True" in second_invoke:
                return True
            return False

    @staticmethod
    def _compute_check_type(ssh_status: bool, vmi_ready: bool) -> str:
        """
        Derive the check_type discriminator from individual check results.

        :param ssh_status: result of the SSH access check
        :param vmi_ready: result of the VMI readiness check
        :return: 'both', 'ssh_access', 'vmi_ready', or 'healthy'
        """
        if not ssh_status and not vmi_ready:
            return "both"
        if not ssh_status:
            return "ssh_access"
        if not vmi_ready:
            return "vmi_ready"
        return "healthy"

    def _make_tracker_entry(self, vm, ssh_status: bool, vmi_ready: bool) -> dict:
        """
        Build a fresh tracker entry dict for a VM with the current check results.

        :param vm: VirtCheck object representing the VM
        :param ssh_status: result of the SSH access check
        :param vmi_ready: result of the VMI readiness check
        :return: tracker entry dict
        """
        return {
            "vm_name": vm.vm_name,
            "ip_address": vm.ip_address,
            "namespace": vm.namespace,
            "node_name": vm.node_name,
            "ssh_status": ssh_status,
            "vmi_ready": vmi_ready,
            "status": ssh_status and vmi_ready,
            "check_type": self._compute_check_type(ssh_status, vmi_ready),
            "start_timestamp": datetime.now(),
            "new_ip_address": vm.new_ip_address,
        }

    def thread_join(self):
        """Join all worker threads."""
        for thread in self.threads:
            thread.join()

    def batch_list(self, telemetry_queue: queue.SimpleQueue = None):
        """
        Start worker threads to check VM batches.

        :param telemetry_queue: queue for telemetry data
        """
        if self.batch_size > 0:
            for i in range(0, len(self.vm_list), self.batch_size):
                sub_list = self.vm_list[i : i + self.batch_size]
                t = threading.Thread(
                    target=self._run_virt_check_batch,
                    name=str(i),
                    args=(sub_list, telemetry_queue),
                )
                self.threads.append(t)
                t.start()

    def _run_virt_check_batch(
        self, vm_list_batch, virt_check_telemetry_queue: queue.SimpleQueue
    ):
        """
        Run health checks for a batch of VMs (executed in worker thread).

        Each VM gets a single combined tracker entry that carries both ssh_status
        and vmi_ready. An entry is closed and a new one started whenever either
        check changes state.

        :param vm_list_batch: list of VMs to check
        :param virt_check_telemetry_queue: queue for telemetry
        """
        virt_check_telemetry = []
        vm_tracker = {}

        while True:
            with self.iteration_lock:
                current = self.current_iterations
            if current >= self.iterations or self._stop_event.is_set():
                break

            for vm in vm_list_batch:
                try:
                    ssh_status = self._get_ssh_status(vm)
                except Exception:
                    logging.exception("Exception in get vm status")
                    ssh_status = False

                vmi_ready = self.check_vmi_ready(vm.vm_name, vm.namespace)

                if vm.vm_name not in vm_tracker:
                    vm_tracker[vm.vm_name] = self._make_tracker_entry(
                        vm, ssh_status, vmi_ready
                    )
                elif (
                    ssh_status != vm_tracker[vm.vm_name]["ssh_status"]
                    or vmi_ready != vm_tracker[vm.vm_name]["vmi_ready"]
                ):
                    if not vmi_ready and vm_tracker[vm.vm_name]["vmi_ready"]:
                        logging.warning(
                            f"VMI {vm.vm_name} in namespace {vm.namespace} transitioned to not-ready"
                        )
                    if vm.new_ip_address:
                        vm_tracker[vm.vm_name]["new_ip_address"] = vm.new_ip_address
                    self._close_tracker_entry(
                        vm_tracker, vm.vm_name, virt_check_telemetry
                    )
                    vm_tracker[vm.vm_name] = self._make_tracker_entry(
                        vm, ssh_status, vmi_ready
                    )

            time.sleep(self.interval)

        # Record final status for all open tracker entries
        end_timestamp = datetime.now()
        for vm_name in vm_tracker:
            self._close_tracker_entry(
                vm_tracker, vm_name, virt_check_telemetry, end_timestamp, delete=False
            )

        try:
            virt_check_telemetry_queue.put(virt_check_telemetry)
        except Exception as e:
            logging.error(f"Put queue error: {str(e)}")

    def _close_tracker_entry(
        self,
        tracker: dict,
        vm_name: str,
        telemetry: list,
        end_timestamp: datetime = None,
        delete: bool = True,
    ) -> None:
        """
        Finalize a tracker entry: stamp timestamps/duration, conditionally append
        to telemetry, and optionally remove from the tracker.

        :param tracker: the vm_tracker dict
        :param vm_name: key into tracker
        :param telemetry: list to append VirtCheck to
        :param end_timestamp: override end time; defaults to now
        :param delete: whether to remove the entry from tracker after closing
        """
        if end_timestamp is None:
            end_timestamp = datetime.now()
        start = tracker[vm_name]["start_timestamp"]
        tracker[vm_name]["end_timestamp"] = end_timestamp.isoformat()
        tracker[vm_name]["duration"] = (end_timestamp - start).total_seconds()
        tracker[vm_name]["start_timestamp"] = start.isoformat()
        if not self.only_failures or not tracker[vm_name]["status"]:
            telemetry.append(VirtCheck(tracker[vm_name]))
        if delete:
            del tracker[vm_name]

    def gather_post_virt_checks(self, kubevirt_check_telem):
        """
        Gather final post-run VM health check status.

        :param kubevirt_check_telem: existing telemetry data
        :return: post-check telemetry data
        """
        post_kubevirt_check_queue = queue.SimpleQueue()
        post_threads = []

        if self.batch_size > 0:
            for i in range(0, len(self.vm_list), self.batch_size):
                sub_list = self.vm_list[i : i + self.batch_size]
                t = threading.Thread(
                    target=self._run_post_virt_check,
                    name=str(i),
                    args=(sub_list, kubevirt_check_telem, post_kubevirt_check_queue),
                )
                post_threads.append(t)
                t.start()

            kubevirt_check_telem = []
            for thread in post_threads:
                thread.join()
                if not post_kubevirt_check_queue.empty():
                    kubevirt_check_telem.extend(post_kubevirt_check_queue.get_nowait())

        if self.exit_on_failure and len(kubevirt_check_telem) > 0:
            self.ret_value = 3

        return kubevirt_check_telem

    def _run_post_virt_check(
        self,
        vm_list_batch,
        virt_check_telemetry,
        post_virt_check_queue: queue.SimpleQueue,
    ):
        """
        Run post-chaos VM health check for a batch. Emits one combined VirtCheck
        entry per VM containing both ssh_status and vmi_ready.

        :param vm_list_batch: list of VMs to check
        :param virt_check_telemetry: telemetry data
        :param post_virt_check_queue: queue for results
        """
        virt_check_telemetry = []
        start_timestamp = datetime.now()

        for vm in vm_list_batch:
            try:
                ssh_status = self._get_ssh_status(vm)
            except Exception:
                ssh_status = False

            vmi_ready = self.check_vmi_ready(vm.vm_name, vm.namespace)
            combined_status = ssh_status and vmi_ready

            if not combined_status:
                if not vmi_ready:
                    logging.warning(
                        f"Post-check: VMI {vm.vm_name} in namespace {vm.namespace} is not ready"
                    )
                virt_check_telemetry.append(
                    VirtCheck(
                        {
                            "vm_name": vm.vm_name,
                            "ip_address": vm.ip_address,
                            "namespace": vm.namespace,
                            "node_name": vm.node_name,
                            "ssh_status": ssh_status,
                            "vmi_ready": vmi_ready,
                            "status": combined_status,
                            "check_type": self._compute_check_type(ssh_status, vmi_ready),
                            "start_timestamp": start_timestamp.isoformat(),
                            "new_ip_address": vm.new_ip_address,
                            "duration": 0,
                            "end_timestamp": start_timestamp.isoformat(),
                        }
                    )
                )

        post_virt_check_queue.put(virt_check_telemetry)

    def run_health_check(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue,
    ) -> None:
        """
        Main entry point for running virt health checks.

        This method initializes the plugin from config and starts batch checking.
        It's called from the main thread and spawns worker threads.

        :param config: health check configuration
        :param telemetry_queue: queue for telemetry data
        :return: None
        """
        if not config:
            logging.info("Virt health check config not provided, skipping")
            return

        # Initialize from config
        if not self._initialize_from_config(config):
            return

        # Start batch checking in worker threads
        self.batch_list(telemetry_queue)
