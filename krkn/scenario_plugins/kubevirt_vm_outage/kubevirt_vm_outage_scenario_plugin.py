import logging
import time
from typing import Dict, Any, Optional
import random
import re
import yaml
from kubernetes.client.rest import ApiException
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import log_exception
from krkn_lib.models.k8s import AffectedPod, PodsStatus

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class KubevirtVmOutageScenarioPlugin(AbstractScenarioPlugin):
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
        return ["kubevirt_vm_outage"]

    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        """
        Main entry point for the plugin.
        Parses the scenario configuration and executes the chaos scenario.
        """
        try:
            with open(scenario, "r") as f:
                scenario_config = yaml.full_load(f)
            
            self.init_clients(lib_telemetry.get_lib_kubernetes())
            pods_status = PodsStatus()
            for config in scenario_config["scenarios"]:
                if config.get("scenario") == "kubevirt_vm_outage":
                    single_pods_status = self.execute_scenario(config, scenario_telemetry)
                    pods_status.merge(single_pods_status)
            
            scenario_telemetry.affected_pods = pods_status
            if len(scenario_telemetry.affected_pods.unrecovered) > 0: 
                return 1
            return 0
        except Exception as e:
            logging.error(f"KubeVirt VM Outage scenario failed: {e}")
            log_exception(e)
            return 1

    def init_clients(self, k8s_client: KrknKubernetes):
        """
        Initialize Kubernetes client for KubeVirt operations.
        """
        self.k8s_client = k8s_client
        self.custom_object_client = k8s_client.custom_object_client
        logging.info("Successfully initialized Kubernetes client for KubeVirt operations")

    
    def execute_scenario(self, config: Dict[str, Any], scenario_telemetry: ScenarioTelemetry) -> PodsStatus:
        """
        Execute a KubeVirt VM outage scenario based on the provided configuration.

        :param config: The scenario configuration
        :param scenario_telemetry: The telemetry object for recording metrics
        :return: PodsStatus object containing recovered and unrecovered pods
        """
        self.pods_status = PodsStatus()
        try:
            params = config.get("parameters", {})
            vm_name = params.get("vm_name")
            namespace = params.get("namespace", "default")
            timeout = params.get("timeout", 60)
            kill_count = params.get("kill_count", 1)
            disable_auto_restart = params.get("disable_auto_restart", False)

            if not vm_name:
                logging.error("vm_name parameter is required")
                return self.pods_status
            self.pods_status = PodsStatus()
            self.vmis_list = self.k8s_client.get_vmis(vm_name,namespace)
            for _ in range(kill_count):
                
                rand_int = random.randint(0, len(self.vmis_list) - 1)
                vmi = self.vmis_list[rand_int]
                    
                logging.info(f"Starting KubeVirt VM outage scenario for VM: {vm_name} in namespace: {namespace}")
                vmi_name = vmi.get("metadata").get("name")
                vmi_namespace = vmi.get("metadata").get("namespace")

                # Create affected_pod early so we can track failures
                self.affected_pod = AffectedPod(
                    pod_name=vmi_name,
                    namespace=vmi_namespace,
                )

                if not self.validate_environment(vmi_name, vmi_namespace):
                    self.pods_status.unrecovered.append(self.affected_pod)
                    continue

                vmi = self.k8s_client.get_vmi(vmi_name, vmi_namespace)
                if not vmi:
                    logging.error(f"VMI {vm_name} not found in namespace {namespace}")
                    self.pods_status.unrecovered.append(self.affected_pod)
                    continue
                    
                self.original_vmi = vmi
                logging.info(f"Captured initial state of VMI: {vm_name}")
                result = self.delete_vmi(vmi_name, vmi_namespace, disable_auto_restart)
                if result != 0:
                    self.pods_status.unrecovered.append(self.affected_pod)
                    continue

                result = self.wait_for_running(vmi_name,vmi_namespace, timeout)
                if result != 0:
                    self.pods_status.unrecovered.append(self.affected_pod)
                    continue
                
                self.affected_pod.total_recovery_time = (
                    self.affected_pod.pod_readiness_time
                    + self.affected_pod.pod_rescheduling_time
                )

                self.pods_status.recovered.append(self.affected_pod)
                logging.info(f"Successfully completed KubeVirt VM outage scenario for VM: {vm_name}")
            
            return self.pods_status
            
        except Exception as e:
            logging.error(f"Error executing KubeVirt VM outage scenario: {e}")
            log_exception(e)
            return self.pods_status

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
                        self.affected_pod.pod_rescheduling_time = time.time() - start_time
                        return 0
                else: 
                    logging.info(f"VMI {vm_name} successfully deleted")
                time.sleep(1)
                
            logging.error(f"Timed out waiting for VMI {vm_name} to be deleted")
            self.pods_status.unrecovered.append(self.affected_pod)
            return 1
            
        except Exception as e:
            logging.error(f"Error deleting VMI {vm_name}: {e}")
            log_exception(e)
            self.pods_status.unrecovered.append(self.affected_pod)
            return 1

    def wait_for_running(self, vm_name: str, namespace: str, timeout: int = 120) -> int: 
        start_time = time.time()
        while time.time() - start_time < timeout: 

            # Check current state once since we've already waited for the duration
            vmi = self.k8s_client.get_vmi(vm_name, namespace)
            
            if vmi:
                if vmi.get('status', {}).get('phase') == "Running":
                    end_time = time.time()
                    self.affected_pod.pod_readiness_time = end_time - start_time

                    logging.info(f"VMI {vm_name} is already running")
                    return 0
                logging.info(f"VMI {vm_name} exists but is not in Running state. Current state: {vmi.get('status', {}).get('phase')}")
            else:
                logging.info(f"VMI {vm_name} not yet recreated")
            time.sleep(1)
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
                    log_exception(e)
                    return 1
            else:
                logging.error(f"Failed to recover VMI {vm_name}: No original state captured and auto-recovery did not occur")
                return 1
                
        except Exception as e:
            logging.error(f"Unexpected error recovering VMI {vm_name}: {e}")
            log_exception(e)
            return 1
