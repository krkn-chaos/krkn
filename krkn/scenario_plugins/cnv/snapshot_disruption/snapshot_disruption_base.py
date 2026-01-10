# Import standard libraries
import logging
import time
from abc import ABC, abstractmethod

import yaml
# Import Krkn/Kubernetes components
from krkn_lib.k8s.krkn_kubernetes import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.models.k8s import AffectedPod, PodsStatus
from krkn_lib.utils import log_exception


class SnapshotDisruptionBase(ABC):
    """
    Abstract base class for CNV VM snapshot disruption scenarios.
    """

    def __init__(self):
        """
        Initializes the base class for a snapshot disruption scenario.
        """

        # --- Scenario Parameters with Defaults (To be overridden by YAML) ---
        # Target VM Parameters
        self.vm_name = "" # e.g: chaos-vm-snapshot-test
        self.vm_namespace = "" # e.g: default
        self.vmi_wait_timeout = 300

        # Snapshot Disruption Parameters
        self.snapshot_name = "" # e.g: chaos-snapshot
        self.snapshot_controller_namespace = "" # e.g: openshift-cluster-storage-operator
        self.snapshot_controller_label = "" # e.g: app=csi-snapshot-controller
        self.snapshot_creation_wait_time = 5
        self.snapshot_ready_timeout = 300

        # Resource Management
        self.cleanup_resources = True

        # --- Internal State ---
        self.k8s_client: KrknKubernetes = None
        self.pods_status = PodsStatus()
        self.affected_pod = None

    def init_clients(self, k8s_client: KrknKubernetes):
        """Initializes the KrknKubernetes client."""
        self.k8s_client = k8s_client
        logging.info("Successfully initialized KrknKubernetes client")

    @abstractmethod
    def execute_test_logic(self):
        """
        (Abstract Method) Contains the specific chaos logic for the scenario.
        """
        pass

    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry
    ) -> int:
        """
        Main entry point for the plugin.
        Parses the scenario configuration and executes the standard workflow 
        for the snapshot disruption chaos scenario.
        """

        if not self._load_config(scenario):
            return 1

        self.init_clients(lib_telemetry.get_lib_kubernetes())
        logging.info(f"Starting {self._NAME} scenario (run ID: {run_uuid})...")

        self.affected_pod = AffectedPod(
            pod_name=self.vm_name, namespace=self.vm_namespace
        )
        start_time = time.time()

        try:
            if not self.k8s_client.get_vm(self.vm_name, self.vm_namespace):
                logging.error(
                    f"Target VM '{self.vm_name}' not found in namespace '{self.vm_namespace}'."
                )
                return 1

            if not self._wait_for_vmi_running():
                return 1

            self.execute_test_logic()

            self.affected_pod.pod_readiness_time = time.time() - start_time
            self.affected_pod.total_recovery_time = self.affected_pod.pod_readiness_time
            self.affected_pod.pod_rescheduling_time = 0.0
            self.pods_status.recovered.append(self.affected_pod)

            logging.info(f"Scenario '{self._NAME}' completed successfully.")
            return 0

        except Exception as e:
            logging.error(f"Scenario '{self._NAME}' (run ID: {run_uuid}) failed: {e}")
            log_exception(e)
            self.affected_pod.total_recovery_time = time.time() - start_time
            self.pods_status.unrecovered.append(self.affected_pod)
            return 1

        finally:
            scenario_telemetry.affected_pods = self.pods_status
            if self.cleanup_resources:
                self._cleanup()

    def _load_config(self, scenario_path: str) -> bool:
        """Loads and validates the scenario configuration from a YAML file."""
        try:
            with open(scenario_path, "r") as f:
                config_data = yaml.safe_load(f)

            scenario_entry = None
            for s in config_data.get("scenarios", []):
                if s.get(self._NAME):
                    scenario_entry = s
                    break

            if not scenario_entry:
                logging.error(
                    f"Scenario '{self._NAME}' not found in config file: {scenario_path}"
                )
                return False

            params = scenario_entry.get(self._NAME, {}).get("parameters", {})

            # Load parameters in the same order as the YAML file
            self.vm_name = params.get("vm_name", self.vm_name)
            self.vm_namespace = params.get("vm_namespace", self.vm_namespace)
            self.vmi_wait_timeout = params.get("vmi_wait_timeout", self.vmi_wait_timeout)

            self.snapshot_name = params.get("snapshot_name", self.snapshot_name)
            self.snapshot_controller_namespace = params.get(
                "snapshot_controller_namespace", self.snapshot_controller_namespace
            )
            self.snapshot_controller_label = params.get(
                "snapshot_controller_label", self.snapshot_controller_label
            )
            self.snapshot_creation_wait_time = params.get(
                "snapshot_creation_wait_time", self.snapshot_creation_wait_time
            )
            self.snapshot_ready_timeout = params.get(
                "snapshot_ready_timeout", self.snapshot_ready_timeout
            )
            
            self.cleanup_resources = params.get("cleanup_resources", self.cleanup_resources)

            logging.info("Scenario configuration loaded successfully with the following parameters:")
            logging.info(f"  VM Name: {self.vm_name}")
            logging.info(f"  VM Namespace: {self.vm_namespace}")
            logging.info(f"  VMI Wait Timeout: {self.vmi_wait_timeout}s")
            logging.info(f"  Snapshot Name: {self.snapshot_name}")
            logging.info(f"  Snapshot Controller Namespace: {self.snapshot_controller_namespace}")
            logging.info(f"  Snapshot Controller Label: {self.snapshot_controller_label}")
            logging.info(f"  Snapshot Creation Wait Time: {self.snapshot_creation_wait_time}s")
            logging.info(f"  Snapshot Ready Timeout: {self.snapshot_ready_timeout}s")
            logging.info(f"  Cleanup Resources: {self.cleanup_resources}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to load or parse config file '{scenario_path}': {e}")
            log_exception(e)
            return False

    def _wait_for_vmi_running(self) -> bool:
        """Polls until the VMI's status phase is 'Running' or a timeout occurs."""
        start_time = time.time()
        logging.info(
            f"Waiting up to {self.vmi_wait_timeout}s for VMI '{self.vm_name}' to enter 'Running' state..."
        )
        while time.time() - start_time < self.vmi_wait_timeout:
            vmi = self.k8s_client.get_vmi(self.vm_name, self.vm_namespace)
            if vmi and vmi.get("status", {}).get("phase") == "Running":
                logging.info(f"VMI '{self.vm_name}' is running.")
                return True
            time.sleep(5)
        logging.error(
            f"Timeout: VMI '{self.vm_name}' did not start within {self.vmi_wait_timeout}s."
        )
        return False

    def _kill_snapshot_controller(self) -> bool:
        """
        Finds and deletes the active snapshot controller pod to disrupt the process.
        """
        logging.info(
            f"Searching for running snapshot controller pod with label '{self.snapshot_controller_label}' "
            f"in namespace '{self.snapshot_controller_namespace}'..."
        )
        pods = self.k8s_client.list_pods(
            namespace=self.snapshot_controller_namespace,
            label_selector=self.snapshot_controller_label,
            field_selector="status.phase=Running",
        )
        if not pods:
            logging.warning("No running snapshot controller pod found to disrupt.")
            return False

        if len(pods) > 1:
            logging.warning(
                f"Found {len(pods)} running snapshot controller pods; will kill the first one: {pods[0]}."
            )

        pod_to_kill = pods[0]
        logging.info(f"Killing snapshot controller pod '{pod_to_kill}'...")
        self.k8s_client.delete_pod(pod_to_kill, self.snapshot_controller_namespace)
        return True

    def _cleanup(self):
        """
        Cleans up resources created during the scenario.
        """
        logging.info("Cleaning up scenario resources...")
        try:
            logging.info(
                f"Deleting snapshot '{self.snapshot_name}' in namespace '{self.vm_namespace}'..."
            )
            self.k8s_client.delete_snapshot(self.snapshot_name, self.vm_namespace)
            logging.info("Snapshot deleted successfully.")

        except Exception as e:
            logging.warning(f"Error during resource cleanup: {e}")
            log_exception(e)
