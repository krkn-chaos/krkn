# Import standard libraries
from abc import ABC, abstractmethod
import logging
import os
import time
import yaml

# Import Kraken framework components
from krkn.invoke.command import invoke, run
from krkn_lib.utils import log_exception


class SnapshotDisruptionBase(ABC):
    """
    This is an abstract base class that provides shared logic for CNV VM snapshot
    disruption scenarios. It is NOT a runnable scenario plugin itself.
    
    It encapsulates the common workflow for all snapshot disruption scenarios,
    including:
      - Loading and validating common configuration parameters.
      - Preparing the target VM (either creating it or verifying its existence).
      - Executing a template `run` method that wraps the specific test logic.
      - Reliably cleaning up resources in a `finally` block.
    
    Child classes are expected to inherit from this class and from
    `AbstractScenarioPlugin` to become runnable plugins.
    """

    def __init__(self, cfg):
        """
        The constructor for the base class.
        
        NOTE: The child class's __init__ must properly initialize the logger.
        """
        self.logger = None
        
        # Initialize default parameters shared across all snapshot scenarios.
        self.vm_name = "chaos-vm-snapshot-test"
        self.vm_namespace = "default"
        self.vm_manifest_path = None
        self.snapshot_creation_wait_time = 20
        self.cleanup_resources = True
        self.snapshot_name = "chaos-snapshot"
        self.snapshot_controller_namespace = "openshift-cluster-storage-operator"
        self.snapshot_controller_label = "app=csi-snapshot-controller"
        self.create_vm = True
        self.created_vm = False

    @abstractmethod
    def execute_test_logic(self):
        """
        (Abstract Method) This method must be implemented by child classes.
        
        It should contain the specific chaos logic for the scenario and raise
        an exception if any of its critical steps fail.
        """
        pass

    def run(self, run_uuid=None, scenario=None, **kwargs):
        """
        Executes the full chaos scenario using a template method pattern.
        """

        if not self._load_config(scenario):
            return 1

        self.logger.info(f"Starting {self._NAME} scenario...")
        result = 1  # Default to failure
        self.created_vm = False
        try:
            # Prepare the target VM
            if self.create_vm:
                self.logger.info(f"Mode: Create. Creating VM '{self.vm_name}'...")
                if not self._create_vm():
                    return 1
                self.created_vm = True
                self.logger.info(f"VM '{self.vm_name}' created successfully.")
            else:
                self.logger.info(f"Mode: Target. Verifying pre-existing VM '{self.vm_name}'...")
                if not self._check_vm_exists():
                    self.logger.error(f"Pre-existing VM '{self.vm_name}' not found in namespace '{self.vm_namespace}'.")
                    return 1
                self.logger.info(f"Successfully found pre-existing VM '{self.vm_name}'.")

            # Wait for the VM to be ready
            self.logger.info(f"Waiting for VM '{self.vm_name}' to enter the 'Running' state...")
            if not self._wait_for_vm_running():
                return 1
            self.logger.info(f"VM '{self.vm_name}' is running.")
            
            # Execute the specific test steps defined in the child class
            self.execute_test_logic()

            self.logger.info(f"Scenario '{self._NAME}' completed successfully.")
            result = 0  # Set result to success
        
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during the scenario: {e}")
            log_exception(str(e))
            result = 1

        finally:
            # The finally block ensures that cleanup is always attempted.
            if self.cleanup_resources:
                self.logger.info("Starting resource cleanup...")
                self._delete_snapshot()
                if self.created_vm:
                    self._delete_vm()
                else:
                    self.logger.info(f"Skipping deletion of pre-existing VM '{self.vm_name}'.")
            else:
                self.logger.info("Skipping resource cleanup as configured.")
            
            return result

    #
    # Helper Methods (Shared Logic)
    #

    def _load_config(self, scenario_path: str) -> bool:
        """Loads and validates common parameters from the scenario YAML file."""
        # ... (implementation remains the same)
        if not scenario_path or not os.path.exists(scenario_path):
            self.logger.error(f"Scenario YAML file path is missing or invalid: {scenario_path}")
            return False

        try:
            with open(scenario_path, "r") as f:
                scenario_data = yaml.safe_load(f)

            scenarios_list = scenario_data.get("scenarios", [])
            scenario_params = {}
            for item in scenarios_list:
                if self._NAME in item:
                    scenario_params = item[self._NAME].get("parameters", {})
                    break

            if not scenario_params:
                self.logger.error(f"Could not find a definition for '{self._NAME}' in {scenario_path}.")
                return False

            self.vm_name = scenario_params.get("vm_name", self.vm_name)
            self.vm_namespace = scenario_params.get("vm_namespace", self.vm_namespace)
            self.vm_manifest_path = scenario_params.get("vm_manifest_path")
            self.snapshot_creation_wait_time = int(scenario_params.get("snapshot_creation_wait_time", 20))
            self.cleanup_resources = bool(scenario_params.get("cleanup_resources", True))
            self.create_vm = bool(scenario_params.get("create_vm", True))
            self.snapshot_name = scenario_params.get("snapshot_name", self.snapshot_name)
            self.snapshot_controller_namespace = scenario_params.get(
                "snapshot_controller_namespace", self.snapshot_controller_namespace
            )
            self.snapshot_controller_label = scenario_params.get(
                "snapshot_controller_label", self.snapshot_controller_label
            )

            if self.create_vm and not self.vm_manifest_path:
                self.logger.error("Required parameter 'vm_manifest_path' is missing when 'create_vm' is true.")
                return False
                
            return True

        except Exception as e:
            self.logger.error(f"Failed to load or parse scenario configuration from {scenario_path}: {e}")
            log_exception(str(e))
            return False


    # -- VM Operations --

    def _create_vm(self) -> bool:
        """Applies the VM manifest to create the test VM."""
        try:
            invoke(f"oc apply -f {self.vm_manifest_path} -n {self.vm_namespace}")
            return True
        except Exception as e:
            log_exception(f"Error applying VM manifest for '{self.vm_name}': {e}")
            return False

    def _wait_for_vm_running(self) -> bool:
        """Waits for the VM to reach the 'Ready' condition."""
        try:
            invoke(f"oc wait --for=condition=Ready --timeout=300s vm/{self.vm_name} -n {self.vm_namespace}")
            return True
        except Exception as e:
            log_exception(f"Error waiting for VM '{self.vm_name}' to become ready: {e}")
            return False

    def _check_vm_exists(self) -> bool:
        """Checks if the target VM exists in the specified namespace."""
        try:
            invoke(f"oc get vm {self.vm_name} -n {self.vm_namespace}")
            return True
        except Exception:
            return False

    def _delete_vm(self):
        """Helper method to delete the test VM."""
        self.logger.info(f"Deleting VM '{self.vm_name}'...")
        try:
            invoke(f"oc delete vm {self.vm_name} -n {self.vm_namespace} --ignore-not-found=true")
            run(f"oc wait --for=delete vm/{self.vm_name} -n {self.vm_namespace} --timeout=120s")
            self.logger.info(f"VM '{self.vm_name}' deleted successfully.")
        except Exception as e:
            self.logger.warning(f"Failed to confirm VM deletion, it might have been already deleted: {e}")
            
    # -- Snapshot and Controller Operations --

    def _create_snapshot(self) -> bool:
        """Creates a VirtualMachineSnapshot resource for the test VM."""
        try:
            snapshot_yaml = f"""
apiVersion: snapshot.kubevirt.io/v1alpha1
kind: VirtualMachineSnapshot
metadata:
  name: {self.snapshot_name}
  namespace: {self.vm_namespace}
spec:
  source:
    apiGroup: kubevirt.io
    kind: VirtualMachine
    name: {self.vm_name}
"""
            with open(f"/tmp/{self.snapshot_name}.yaml", "w") as f:
                f.write(snapshot_yaml)

            invoke(f"oc apply -f /tmp/{self.snapshot_name}.yaml")
            return True
        except Exception as e:
            log_exception(f"Error creating snapshot '{self.snapshot_name}': {e}")
            return False

    def _verify_snapshot_created(self) -> bool:
        """Waits for the snapshot to reach the 'Ready' condition."""
        try:
            invoke(f"oc wait --for=condition=Ready --timeout=300s vmsnapshot/{self.snapshot_name} -n {self.vm_namespace}")
            output = invoke(f"oc get vmsnapshot/{self.snapshot_name} -n {self.vm_namespace}")
            self.logger.info(f"Final snapshot status:\n{output}")
            return True
        except Exception as e:
            log_exception(f"Error waiting for snapshot '{self.snapshot_name}' to complete: {e}")
            return False

    def _get_snapshot_controller_pod_name(self) -> str | None:
        """Finds the name of the active csi-snapshot-controller pod."""
        try:
            pod_name = invoke(
                f"oc get pods -n {self.snapshot_controller_namespace} "
                f"-l {self.snapshot_controller_label} "
                "-o jsonpath='{.items[0].metadata.name}'"
            ).strip()

            if not pod_name:
                self.logger.warning("Could not find the snapshot controller pod.")
                return None
            return pod_name
        except Exception as e:
            log_exception(f"Error finding the snapshot controller pod: {e}")
            return None

    def _kill_snapshot_controller(self) -> bool:
        """Deletes the snapshot controller pod to simulate a failure."""
        pod_name = self._get_snapshot_controller_pod_name()
        if not pod_name:
            return False

        try:
            invoke(f"oc delete pod {pod_name} -n {self.snapshot_controller_namespace}")
            return True
        except Exception as e:
            log_exception(f"Error deleting pod '{pod_name}': {e}")
            return False
            
    def _delete_snapshot(self):
        """Helper method to delete any snapshot created by the scenario."""
        self.logger.info(f"Deleting snapshot '{self.snapshot_name}'...")
        try:
            invoke(f"oc delete vmsnapshot {self.snapshot_name} -n {self.vm_namespace} --ignore-not-found=true")
            self.logger.info(f"Snapshot '{self.snapshot_name}' deleted successfully.")
        except Exception as e:
            self.logger.warning(f"Failed to delete snapshot, it might have been already deleted: {e}")

