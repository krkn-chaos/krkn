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

import logging
import time
import uuid
from typing import Dict, Any, Optional
import random
import yaml
from kubernetes.client.rest import ApiException
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import log_exception
from krkn_lib.models.k8s import AffectedVMI, VmisStatus

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin

# Helper image for guest reachability probes (ping/nc included).
DEFAULT_GUEST_PING_IMAGE = (
    "quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
)


def _as_bool(value: Any, default: bool = False) -> bool:
    """Parse bools from YAML or envsubst strings (``False`` must not become True)."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _optional_str(value: Any) -> Optional[str]:
    """Strip optional config/envsubst values; blank → None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_number(value: Any, default: float, cast=float):
    """
    Parse numeric YAML/envsubst values; blank or invalid → default.

    Hub templates often leave ``$VAR`` empty when unset; ``int("")`` must
    not abort a scenario that does not even enable guest ping.
    """
    if value is None:
        return cast(default)
    if isinstance(value, bool):
        return cast(default)
    if isinstance(value, (int, float)):
        return cast(value)
    text = str(value).strip()
    if not text:
        return cast(default)
    try:
        return cast(text)
    except (TypeError, ValueError):
        logging.warning(
            f"Invalid numeric value {value!r}; using default {default}"
        )
        return cast(default)


class VmiOutageScenarioPlugin(AbstractScenarioPlugin):
    """
    A scenario plugin that injects chaos by deleting a KubeVirt Virtual Machine Instance (VMI).
    This plugin simulates a VM crash or outage scenario and supports automated or manual recovery.
    """

    def __init__(self, scenario_type: str = None):
        scenario_type = self.get_scenario_types()[0]
        super().__init__(scenario_type)
        self.k8s_client = None
        self.original_vmi = None
        self.vmis_list = []

    # Scenario type is handled directly in execute_scenario
    def get_scenario_types(self) -> list[str]:
        # Support both new name and legacy name for backwards compatibility
        return ["vmi_outage", "kubevirt_vm_outage"]

    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        """
        Main entry point for the plugin.
        Parses the scenario configuration and executes the chaos scenario.
        """
        try:
            with open(scenario, "r") as f:
                scenario_config = yaml.safe_load(f)
            
            self.init_clients(lib_telemetry.get_lib_kubernetes())
            vmis_status = VmisStatus()
            for config in scenario_config["scenarios"]:
                # Support both new name and legacy name for backwards compatibility
                scenario_type = config.get("scenario")
                if scenario_type in ["vmi_outage", "kubevirt_vm_outage"]:
                    single_vmis_status = self.execute_scenario(config, scenario_telemetry)
                    vmis_status.merge(single_vmis_status)
                    if single_vmis_status.error:
                        vmis_status.error = single_vmis_status.error
            
            scenario_telemetry.affected_vmis = vmis_status
            if (
                scenario_telemetry.affected_vmis.error
                or len(scenario_telemetry.affected_vmis.unrecovered) > 0
            ):
                return 1
            return 0
        except Exception as e:
            logging.error(f"VMI Outage scenario failed: {e}")
            log_exception(str(e))
            return 1

    def init_clients(self, k8s_client: KrknKubernetes):
        """
        Initialize Kubernetes client for KubeVirt operations.
        """
        self.k8s_client = k8s_client
        self.custom_object_client = k8s_client.custom_object_client
        logging.info("Successfully initialized Kubernetes client for KubeVirt operations")

    
    def execute_scenario(self, config: Dict[str, Any], scenario_telemetry: ScenarioTelemetry) -> VmisStatus:
        """
        Execute a VMI outage scenario based on the provided configuration.

        :param config: The scenario configuration
        :param scenario_telemetry: The telemetry object for recording metrics
        :return: VmisStatus object containing recovered and unrecovered pods
        """
        self.vmis_status = VmisStatus()
        try:
            params = config.get("parameters", {})
            vm_name = params.get("vm_name") or None
            label_selector = params.get("label_selector") or None
            namespace = params.get("namespace", "default")
            timeout = params.get("timeout", 60)
            kill_count = params.get("kill_count", 1)
            disable_auto_restart = params.get("disable_auto_restart", False)
            wait_for_guest_ping = _as_bool(
                params.get("wait_for_guest_ping", False), False
            )
            # Guest-ping knobs are only needed when enabled (avoids empty
            # envsubst values aborting a default-off outage run).
            guest_ping_timeout = 300
            guest_ping_interval = 2.0
            guest_ping_method = "icmp"
            guest_ping_port = 22
            guest_ping_namespace = None
            guest_ping_pod = None
            guest_ping_settle_seconds = 5.0
            if wait_for_guest_ping:
                guest_ping_timeout = int(
                    _as_number(params.get("guest_ping_timeout"), 300, int)
                )
                guest_ping_interval = float(
                    _as_number(params.get("guest_ping_interval"), 2, float)
                )
                guest_ping_method = (
                    _optional_str(params.get("guest_ping_method")) or "icmp"
                ).lower()
                guest_ping_port = int(
                    _as_number(params.get("guest_ping_port"), 22, int)
                )
                guest_ping_namespace = _optional_str(
                    params.get("guest_ping_namespace")
                )
                # Optional pre-created helper (guest-ping-diagnosis-pod.yaml).
                guest_ping_pod = _optional_str(params.get("guest_ping_pod"))
                guest_ping_settle_seconds = float(
                    _as_number(
                        params.get("guest_ping_settle_seconds"), 5, float
                    )
                )

            if not vm_name and not label_selector:
                logging.error("Either vm_name or label_selector parameter is required")
                return self.vmis_status
            self.vmis_status = VmisStatus()
            name_regex = vm_name or ".*"
            self.vmis_list = self.k8s_client.get_vmis(name_regex, namespace, label_selector=label_selector)
            if not self.vmis_list:
                target = f"label_selector={label_selector}" if label_selector else f"vm_name={vm_name}"
                message = f"No VMIs found matching {target} in namespace {namespace}"
                logging.error(message)
                self.vmis_status.error = message
                return self.vmis_status

            # Spin helper pod before chaos so create/pull is off the MTTR path.
            owned_probe_pod = False
            active_probe_pod = guest_ping_pod
            probe_ns = guest_ping_namespace or namespace
            if wait_for_guest_ping:
                try:
                    active_probe_pod, owned_probe_pod = (
                        self._ensure_guest_probe_pod(
                            probe_ns,
                            probe_pod=guest_ping_pod,
                            method=guest_ping_method,
                        )
                    )
                    if guest_ping_settle_seconds > 0:
                        logging.info(
                            f"Probe pod {active_probe_pod} ready; settling "
                            f"{guest_ping_settle_seconds}s before scenario"
                        )
                        time.sleep(guest_ping_settle_seconds)
                except Exception as exc:
                    message = (
                        f"Failed to prepare guest probe pod in {probe_ns}: {exc}"
                    )
                    logging.error(message)
                    log_exception(str(exc))
                    self.vmis_status.error = message
                    return self.vmis_status

            try:
                for _ in range(kill_count):

                    rand_int = random.randint(0, len(self.vmis_list) - 1)
                    vmi = self.vmis_list[rand_int]

                    target = f"label_selector={label_selector}" if label_selector else f"vm_name={vm_name}"
                    logging.info(f"Starting VMI outage scenario for {target} in namespace: {namespace}")
                    vmi_name = vmi.get("metadata").get("name")
                    vmi_namespace = vmi.get("metadata").get("namespace")

                    # Create affected_vmi early so we can track failures
                    self.affected_vmi = AffectedVMI(
                        vmi_name=vmi_name,
                        namespace=vmi_namespace,
                    )

                    if not self.validate_environment(vmi_name, vmi_namespace):
                        self.vmis_status.unrecovered.append(self.affected_vmi)
                        continue

                    vmi = self.k8s_client.get_vmi(vmi_name, vmi_namespace)
                    if not vmi:
                        logging.error(f"VMI {vmi_name} not found in namespace {vmi_namespace}")
                        self.vmis_status.unrecovered.append(self.affected_vmi)
                        continue

                    self.original_vmi = vmi
                    logging.info(f"Captured initial state of VMI: {vmi_name}")
                    result = self.delete_vmi(vmi_name, vmi_namespace, disable_auto_restart)
                    if result != 0:
                        self.vmis_status.unrecovered.append(self.affected_vmi)
                        continue

                    result = self.wait_for_running(vmi_name, vmi_namespace, timeout)
                    if result != 0:
                        self.vmis_status.unrecovered.append(self.affected_vmi)
                        continue

                    if wait_for_guest_ping:
                        result = self.wait_for_guest_reachable(
                            vmi_name,
                            vmi_namespace,
                            timeout=guest_ping_timeout,
                            interval=guest_ping_interval,
                            method=guest_ping_method,
                            port=guest_ping_port,
                            probe_namespace=probe_ns,
                            probe_pod=active_probe_pod,
                        )
                        if result != 0:
                            self.vmis_status.unrecovered.append(self.affected_vmi)
                            continue

                    total = (
                        (self.affected_vmi.vmi_readiness_time or 0)
                        + (self.affected_vmi.vmi_rescheduling_time or 0)
                    )
                    guest_time = getattr(
                        self.affected_vmi, "guest_reachable_time", None
                    )
                    if guest_time is not None:
                        total += guest_time
                    self.affected_vmi.total_recovery_time = total

                    self.vmis_status.recovered.append(self.affected_vmi)
                    logging.info(
                        f"Successfully completed VMI outage scenario for VM: {vmi_name}"
                        f" (total_recovery_time={total:.2f}s"
                        f", guest_reachable_time={guest_time})"
                    )

                return self.vmis_status
            finally:
                if owned_probe_pod and active_probe_pod:
                    self._delete_guest_probe_pod(active_probe_pod, probe_ns)

        except Exception as e:
            message = f"Error executing VMI outage scenario: {e}"
            logging.error(message)
            log_exception(str(e))
            if self.vmis_status is None:
                self.vmis_status = VmisStatus()
            self.vmis_status.error = message
            return self.vmis_status

    def validate_environment(self, vm_name: str, namespace: str) -> bool:
        """
        Validate that KubeVirt is installed and the specified VM exists.
        
        :param vm_name: Name of the VM to validate
        :param namespace: Namespace of the VM
        :return: True if environment is valid, False otherwise
        """
        try:
            # Check if KubeVirt CRDs exist
            kubevirt_crds = self.k8s_client.get_vms(vm_name, namespace)
            if not kubevirt_crds:
                logging.error("KubeVirt CRDs not found. Ensure KubeVirt/CNV is installed in the cluster")
                return False
                
            # Check if VMI exists
            vmi = self.k8s_client.get_vmi(vm_name, namespace)
            if not vmi:
                logging.error(f"VMI {vm_name} not found in namespace {namespace}")
                return False
                
            logging.info(f"Validated environment: KubeVirt is installed and VMI {vm_name} exists")
            return True
            
        except Exception as e:
            logging.error(f"Error validating environment: {e}")
            return False

    def patch_vm_spec(self, vm_name: str, namespace: str, running: bool) -> bool:
        """
        Patch the VM spec to enable/disable auto-restart.
        
        :param vm_name: Name of the VM to patch
        :param namespace: Namespace of the VM
        :param running: Whether the VM should be set to running state
        :return: True if patch was successful, False otherwise
        """
        try:
            # Get the VM object first to get its current spec
            vm = self.k8s_client.get_vm(vm_name, namespace)
            
            # Update the running state
            if 'spec' not in vm:
                vm['spec'] = {}
            vm['spec']['running'] = running
            
            # Apply the patch
            self.k8s_client.patch_vm(vm_name,namespace,vm)
            return True
            
        except ApiException as e:
            logging.error(f"Failed to patch VM {vm_name}: {e}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error patching VM {vm_name}: {e}")
            return False
            
    def delete_vmi(self, vm_name: str, namespace: str, disable_auto_restart: bool = False, timeout: int = 120) -> int:
        """
        Delete a Virtual Machine Instance to simulate a VM outage.
        
        :param vm_name: Name of the VMI to delete
        :param namespace: Namespace of the VMI
        :return: 0 for success, 1 for failure
        """
        try:
            logging.info(f"Injecting chaos: Deleting VMI {vm_name} in namespace {namespace}")
            
            # If auto-restart should be disabled, patch the VM spec first
            if disable_auto_restart:
                logging.info(f"Disabling auto-restart for VM {vm_name} by setting spec.running=False")
                if not self.patch_vm_spec(vm_name, namespace, running=False):
                    logging.error("Failed to disable auto-restart for VM"
                               " - proceeding with deletion but VM may auto-restart")
            start_creation_time =  self.original_vmi.get('metadata', {}).get('creationTimestamp')
            start_time = time.time()
            self.k8s_client.delete_vmi(vm_name, namespace)
            
            # Wait for the VMI to be deleted
            
            while time.time() - start_time < timeout:
                deleted_vmi = self.k8s_client.get_vmi(vm_name, namespace)
                if deleted_vmi:
                    if start_creation_time != deleted_vmi.get('metadata', {}).get('creationTimestamp'):
                        logging.info(f"VMI {vm_name} successfully recreated")
                        self.affected_vmi.vmi_rescheduling_time = time.time() - start_time
                        return 0
                else: 
                    logging.info(f"VMI {vm_name} successfully deleted")
                time.sleep(1)
                
            logging.error(f"Timed out waiting for VMI {vm_name} to be deleted")
            return 1
            
        except Exception as e:
            logging.error(f"Error deleting VMI {vm_name}: {e}")
            log_exception(str(e))
            return 1

    def wait_for_running(self, vm_name: str, namespace: str, timeout: int = 120) -> int: 
        start_time = time.time()
        while time.time() - start_time < timeout: 

            # Check current state once since we've already waited for the duration
            vmi = self.k8s_client.get_vmi(vm_name, namespace)
            
            if vmi:
                if vmi.get('status', {}).get('phase') == "Running":
                    end_time = time.time()
                    self.affected_vmi.vmi_readiness_time = end_time - start_time

                    logging.info(f"VMI {vm_name} is already running")
                    return 0
                logging.info(f"VMI {vm_name} exists but is not in Running state. Current state: {vmi.get('status', {}).get('phase')}")
            else:
                logging.info(f"VMI {vm_name} not yet recreated")
            time.sleep(1)
        return 1

    @staticmethod
    def get_vmi_ips(vmi: Dict[str, Any]) -> list[str]:
        """
        Return all guest IPs from VMI status.interfaces (deduped).

        Skips IPv6 link-local (``fe80:``) addresses, which are not useful for
        cross-pod reachability probes. Order follows interface status order.
        """
        ips: list[str] = []
        seen = set()
        interfaces = (vmi or {}).get("status", {}).get("interfaces") or []
        for iface in interfaces:
            if not isinstance(iface, dict):
                continue
            candidates = []
            primary = iface.get("ipAddress")
            if primary:
                candidates.append(primary)
            for addr in iface.get("ipAddresses") or []:
                if addr:
                    candidates.append(addr)
            for ip in candidates:
                if ip in seen:
                    continue
                if str(ip).lower().startswith("fe80:"):
                    continue
                seen.add(ip)
                ips.append(ip)
        return ips

    @staticmethod
    def get_vmi_ip(vmi: Dict[str, Any]) -> Optional[str]:
        """Return the first guest IP from VMI status.interfaces, if any."""
        ips = VmiOutageScenarioPlugin.get_vmi_ips(vmi)
        return ips[0] if ips else None

    def _guest_probe_pod_body(
        self, pod_name: str, method: str = "icmp"
    ) -> Dict[str, Any]:
        """
        Build a short-lived helper pod (tools image already has ping/nc).

        NET_RAW is added only for ICMP. TCP probes stay compatible with
        OpenShift restricted-v2 / PodSecurity restricted (no extra caps).
        """
        capabilities: Dict[str, Any] = {"drop": ["ALL"]}
        if (method or "icmp").lower() == "icmp":
            # ICMP echo requires NET_RAW; may need a less-restricted SCC/ns.
            capabilities["add"] = ["NET_RAW"]

        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "labels": {
                    "app": "krkn-guest-ping",
                    "krkn-chaos.io/scenario": "vmi_outage",
                },
            },
            "spec": {
                "restartPolicy": "Never",
                "containers": [
                    {
                        "name": "probe",
                        "image": DEFAULT_GUEST_PING_IMAGE,
                        # Keep helper alive for long scenarios / high kill_count;
                        # owned pods are deleted when the scenario finishes.
                        "command": ["sleep", "infinity"],
                        "securityContext": {
                            "allowPrivilegeEscalation": False,
                            "capabilities": capabilities,
                        },
                    }
                ],
            },
        }

    def _create_guest_probe_pod(
        self, namespace: str, method: str = "icmp"
    ) -> str:
        """
        Create helper probe pod and wait until Running. Returns pod name.

        On create/startup failure the pod name is already known, so clean up
        here even if ``create_pod`` raises after the object exists.
        """
        pod_name = f"krkn-guest-ping-{uuid.uuid4().hex[:8]}"
        body = self._guest_probe_pod_body(pod_name, method=method)
        logging.info(
            f"Creating guest probe pod {pod_name} in {namespace} "
            f"(image={DEFAULT_GUEST_PING_IMAGE}, method={method})"
        )
        try:
            self.k8s_client.create_pod(body, namespace, timeout=180)
        except Exception:
            logging.error(
                f"Guest probe pod {pod_name} failed to start in {namespace}; "
                "cleaning up"
            )
            self._delete_guest_probe_pod(pod_name, namespace)
            raise
        return pod_name

    def _wait_for_probe_pod_ready(
        self, pod_name: str, namespace: str, timeout: int = 180
    ) -> None:
        """Block until an existing probe pod is Running/Ready or raise."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.k8s_client.is_pod_running(pod_name, namespace):
                logging.info(
                    f"Guest probe pod {pod_name} is ready in {namespace}"
                )
                return
            time.sleep(2)
        raise TimeoutError(
            f"Guest probe pod {pod_name} not ready in {namespace} "
            f"within {timeout}s"
        )

    def _ensure_guest_probe_pod(
        self,
        namespace: str,
        probe_pod: Optional[str] = None,
        method: str = "icmp",
    ) -> tuple[str, bool]:
        """
        Ensure a probe pod is Running before chaos starts.

        :return: (pod_name, owned) — owned True means caller should delete it
        """
        existing = _optional_str(probe_pod)
        if existing:
            logging.info(
                f"Using existing guest probe pod {existing} in {namespace}"
            )
            self._wait_for_probe_pod_ready(existing, namespace)
            return existing, False

        # create_pod already waits until Running; tools image needs no install.
        return self._create_guest_probe_pod(namespace, method=method), True

    def _delete_guest_probe_pod(self, pod_name: str, namespace: str) -> None:
        if not pod_name:
            return
        try:
            self.k8s_client.delete_pod(
                pod_name, namespace, grace_period_seconds=0
            )
            logging.info(f"Deleted guest probe pod {pod_name}")
        except Exception as exc:
            logging.warning(
                f"Failed to delete guest probe pod {pod_name}: {exc}"
            )

    def probe_guest_via_pod(
        self,
        host: str,
        pod_name: str,
        namespace: str,
        method: str = "icmp",
        port: int = 22,
    ) -> bool:
        """
        Probe guest from an in-cluster helper pod (same SDN as the VMI IP).
        """
        method = (method or "icmp").lower()
        if method == "tcp":
            cmd = f"nc -z -w 2 {host} {port} >/dev/null 2>&1 && echo OK || echo FAIL"
        else:
            if method != "icmp":
                logging.warning(
                    f"Unknown guest_ping_method={method!r}; falling back to icmp"
                )
            cmd = (
                f"ping -c 1 -W 1 {host} >/dev/null 2>&1 && echo OK || echo FAIL"
            )
        try:
            output = self.k8s_client.exec_cmd_in_pod(
                [cmd], pod_name, namespace
            )
            return "OK" in (output or "")
        except Exception as exc:
            status = getattr(exc, "status", None)
            msg = str(exc)
            # Surface RBAC/auth failures; guest-down is expected noise at debug.
            if status in (401, 403) or "forbidden" in msg.lower():
                logging.warning(
                    f"In-cluster probe of {host} via {pod_name} denied: {exc}. "
                    "Krkn SA needs pods/exec create "
                    "(see rbac/non-privileged-role.yaml / "
                    "rbac/privileged-clusterrole.yaml)."
                )
            else:
                logging.debug(
                    f"In-cluster probe of {host} via {pod_name} failed: {exc}"
                )
            return False

    def wait_for_guest_reachable(
        self,
        vm_name: str,
        namespace: str,
        timeout: int = 300,
        interval: float = 2,
        method: str = "icmp",
        port: int = 22,
        probe_namespace: Optional[str] = None,
        probe_pod: Optional[str] = None,
    ) -> int:
        """
        Poll until the guest is reachable after VMI phase=Running.

        Requires a ready in-cluster helper pod (prepared before chaos via
        ``_ensure_guest_probe_pod``). Sets
        ``affected_vmi.guest_reachable_time`` on success (needs
        ``krkn-lib>=7.0.4`` so the field serializes for reports/elastic).

        :return: 0 on success, 1 on timeout / missing IP / missing probe
        """
        probe_ns = probe_namespace or namespace
        active_probe_pod = _optional_str(probe_pod)
        if not active_probe_pod:
            logging.error(
                "wait_for_guest_reachable requires a ready probe_pod"
            )
            return 1

        logging.info(
            f"Waiting for guest reachability on VMI {vm_name} "
            f"(method={method}, probe={active_probe_pod}, timeout={timeout}s)"
        )

        start_time = time.time()
        while time.time() - start_time < timeout:
            vmi = self.k8s_client.get_vmi(vm_name, namespace)
            ips = self.get_vmi_ips(vmi) if vmi else []
            if not ips:
                logging.info(
                    f"VMI {vm_name} has no guest IP yet; "
                    f"retrying in {interval}s"
                )
                time.sleep(interval)
                continue

            # Multi-NIC guests: try every reported address each cycle.
            reachable_ip = None
            for ip in ips:
                if self.probe_guest_via_pod(
                    ip,
                    active_probe_pod,
                    probe_ns,
                    method=method,
                    port=port,
                ):
                    reachable_ip = ip
                    break

            if reachable_ip:
                elapsed = time.time() - start_time
                self.affected_vmi.guest_reachable_time = elapsed
                logging.info(
                    f"Guest {vm_name} reachable at {reachable_ip} after "
                    f"{elapsed:.2f}s (method={method})"
                )
                return 0

            logging.info(
                f"Guest {vm_name} at {ips} not reachable yet "
                f"(method={method})"
            )
            time.sleep(interval)

        logging.error(
            f"Timed out waiting for guest {vm_name} to become reachable "
            f"after {timeout}s (method={method})"
        )
        return 1

    def recover(self, vm_name: str, namespace: str, disable_auto_restart: bool = False) -> int:
        """
        Recover a deleted VMI, either by waiting for auto-recovery or manually recreating it.
        
        :param vm_name: Name of the VMI to recover
        :param namespace: Namespace of the VMI
        :param disable_auto_restart: Whether auto-restart was disabled during injection
        :return: 0 for success, 1 for failure
        """
        try:
            logging.info(f"Attempting to recover VMI {vm_name} in namespace {namespace}")

            if not hasattr(self, 'affected_vmi') or self.affected_vmi is None:
                self.affected_vmi = AffectedVMI(vmi_name=vm_name, namespace=namespace)

            if self.original_vmi:
                logging.info(f"Auto-recovery didn't occur for VMI {vm_name}. Attempting manual recreation")
                
                try:
                    # Clean up server-generated fields
                    vmi_dict = self.original_vmi.copy()
                    if 'metadata' in vmi_dict:
                        metadata = vmi_dict['metadata']
                        for field in ['resourceVersion', 'uid', 'creationTimestamp', 'generation']:
                            if field in metadata:
                                del metadata[field]
                    
                    # Create the VMI
                    self.k8s_client.create_vmi(vm_name, namespace, vmi_dict)
                    logging.info(f"Successfully recreated VMI {vm_name}")
                    
                    # Wait for VMI to start running
                    self.wait_for_running(vm_name,namespace)
                    
                    logging.warning(f"VMI {vm_name} was recreated but didn't reach Running state in time")
                    return 0  # Still consider it a success as the VMI was recreated
                    
                except Exception as e:
                    logging.error(f"Error recreating VMI {vm_name}: {e}")
                    log_exception(str(e))
                    return 1
            else:
                logging.error(f"Failed to recover VMI {vm_name}: No original state captured and auto-recovery did not occur")
                return 1
                
        except Exception as e:
            logging.error(f"Unexpected error recovering VMI {vm_name}: {e}")
            log_exception(str(e))
            return 1
