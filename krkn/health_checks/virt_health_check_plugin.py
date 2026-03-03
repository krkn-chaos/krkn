"""
Virtualization Health Check Plugin

This plugin provides health checking for KubeVirt virtual machines and VMIs
during chaos engineering experiments.

Example configuration in config.yaml:
    kubevirt_checks:
      type: virt_health_check
      namespace: "default"
      name: ".*"                    # VMI name regex pattern
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
        vmi_name_match = get_yaml_item_value(config, "name", ".*")

        if self.namespace == "":
            logging.info("kubevirt checks config namespace is not defined, skipping them")
            return False

        try:
            self.kube_vm_plugin = KubevirtVmOutageScenarioPlugin()
            self.kube_vm_plugin.init_clients(k8s_client=self.krkn_lib)
            self.vmis_list = self.kube_vm_plugin.k8s_client.get_vmis(
                vmi_name_match, self.namespace
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
                logging.warning(f"VMI {vmi_name} has no network interfaces, skipping")
                continue

            ip_address = interfaces[0].get("ipAddress")
            namespace = vmi.get("metadata", {}).get("namespace")

            # Filter by node names if specified
            if len(node_name_list) > 0 and node_name in node_name_list:
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
            elif len(node_name_list) == 0:
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
                if i + self.batch_size > len(self.vm_list):
                    sub_list = self.vm_list[i:]
                else:
                    sub_list = self.vm_list[i : i + self.batch_size]
                index = i
                t = threading.Thread(
                    target=self._run_virt_check_batch,
                    name=str(index),
                    args=(sub_list, telemetry_queue),
                )
                self.threads.append(t)
                t.start()

    def _run_virt_check_batch(
        self, vm_list_batch, virt_check_telemetry_queue: queue.SimpleQueue
    ):
        """
        Run health checks for a batch of VMs (executed in worker thread).

        :param vm_list_batch: list of VMs to check
        :param virt_check_telemetry_queue: queue for telemetry
        """
        virt_check_telemetry = []
        virt_check_tracker = {}

        while True:
            # Thread-safe read of current_iterations
            with self.iteration_lock:
                current = self.current_iterations
            if current >= self.iterations:
                break

            for vm in vm_list_batch:
                start_time = datetime.now()
                try:
                    if not self.disconnected:
                        vm_status = self.get_vm_access(vm.vm_name, vm.namespace)
                    else:
                        # Use new IP if available
                        if vm.new_ip_address:
                            vm_status, new_ip_address, new_node_name = (
                                self.check_disconnected_access(
                                    vm.new_ip_address, vm.node_name, vm.vm_name
                                )
                            )
                        else:
                            vm_status, new_ip_address, new_node_name = (
                                self.check_disconnected_access(
                                    vm.ip_address, vm.node_name, vm.vm_name
                                )
                            )
                            if new_ip_address and vm.ip_address != new_ip_address:
                                vm.new_ip_address = new_ip_address
                            if new_node_name and vm.node_name != new_node_name:
                                vm.node_name = new_node_name
                except Exception:
                    logging.info("Exception in get vm status")
                    vm_status = False

                if vm.vm_name not in virt_check_tracker:
                    start_timestamp = datetime.now()
                    virt_check_tracker[vm.vm_name] = {
                        "vm_name": vm.vm_name,
                        "ip_address": vm.ip_address,
                        "namespace": vm.namespace,
                        "node_name": vm.node_name,
                        "status": vm_status,
                        "start_timestamp": start_timestamp,
                        "new_ip_address": vm.new_ip_address,
                    }
                else:
                    if vm_status != virt_check_tracker[vm.vm_name]["status"]:
                        end_timestamp = datetime.now()
                        start_timestamp = virt_check_tracker[vm.vm_name][
                            "start_timestamp"
                        ]
                        duration = (end_timestamp - start_timestamp).total_seconds()
                        virt_check_tracker[vm.vm_name][
                            "end_timestamp"
                        ] = end_timestamp.isoformat()
                        virt_check_tracker[vm.vm_name]["duration"] = duration
                        virt_check_tracker[vm.vm_name][
                            "start_timestamp"
                        ] = start_timestamp.isoformat()
                        if vm.new_ip_address:
                            virt_check_tracker[vm.vm_name][
                                "new_ip_address"
                            ] = vm.new_ip_address

                        if self.only_failures:
                            if not virt_check_tracker[vm.vm_name]["status"]:
                                virt_check_telemetry.append(
                                    VirtCheck(virt_check_tracker[vm.vm_name])
                                )
                        else:
                            virt_check_telemetry.append(
                                VirtCheck(virt_check_tracker[vm.vm_name])
                            )
                        del virt_check_tracker[vm.vm_name]

            time.sleep(self.interval)

        # Record final status
        virt_check_end_time_stamp = datetime.now()
        for vm in virt_check_tracker.keys():
            final_start_timestamp = virt_check_tracker[vm]["start_timestamp"]
            final_duration = (
                virt_check_end_time_stamp - final_start_timestamp
            ).total_seconds()
            virt_check_tracker[vm]["end_timestamp"] = virt_check_end_time_stamp.isoformat()
            virt_check_tracker[vm]["duration"] = final_duration
            virt_check_tracker[vm]["start_timestamp"] = final_start_timestamp.isoformat()

            if self.only_failures:
                if not virt_check_tracker[vm]["status"]:
                    virt_check_telemetry.append(VirtCheck(virt_check_tracker[vm]))
            else:
                virt_check_telemetry.append(VirtCheck(virt_check_tracker[vm]))

        try:
            virt_check_telemetry_queue.put(virt_check_telemetry)
        except Exception as e:
            logging.error(f"Put queue error: {str(e)}")

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
                index = i
                t = threading.Thread(
                    target=self._run_post_virt_check,
                    name=str(index),
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
            self.ret_value = 2

        return kubevirt_check_telem

    def _run_post_virt_check(
        self,
        vm_list_batch,
        virt_check_telemetry,
        post_virt_check_queue: queue.SimpleQueue,
    ):
        """
        Run post-chaos VM health check for a batch.

        :param vm_list_batch: list of VMs to check
        :param virt_check_telemetry: telemetry data
        :param post_virt_check_queue: queue for results
        """
        virt_check_telemetry = []
        virt_check_tracker = {}
        start_timestamp = datetime.now()

        for vm in vm_list_batch:
            try:
                if not self.disconnected:
                    vm_status = self.get_vm_access(vm.vm_name, vm.namespace)
                else:
                    vm_status, new_ip_address, new_node_name = (
                        self.check_disconnected_access(
                            vm.ip_address, vm.node_name, vm.vm_name
                        )
                    )
                    if new_ip_address and vm.ip_address != new_ip_address:
                        vm.new_ip_address = new_ip_address
                    if new_node_name and vm.node_name != new_node_name:
                        vm.node_name = new_node_name
            except Exception:
                vm_status = False

            if not vm_status:
                virt_check_tracker = {
                    "vm_name": vm.vm_name,
                    "ip_address": vm.ip_address,
                    "namespace": vm.namespace,
                    "node_name": vm.node_name,
                    "status": vm_status,
                    "start_timestamp": start_timestamp.isoformat(),
                    "new_ip_address": vm.new_ip_address,
                    "duration": 0,
                    "end_timestamp": start_timestamp.isoformat(),
                }
                virt_check_telemetry.append(VirtCheck(virt_check_tracker))

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
