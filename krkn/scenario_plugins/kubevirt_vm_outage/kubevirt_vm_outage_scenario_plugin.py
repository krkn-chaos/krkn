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
            logging.error("KubeVirt VM Outage scenario failed: %s", e)
            log_exception(e)
            return 1

    def init_clients(self, k8s_client: KrknKubernetes):
        """
        Initialize Kubernetes client for KubeVirt operations.
        """
        self.k8s_client = k8s_client
        self.custom_object_client = k8s_client.custom_object_client
        logging.info("Successfully initialized Kubernetes client for KubeVirt operations")

    def get_vmi(self, name: str, namespace: str) -> Optional[Dict]:
        """
        Get a Virtual Machine Instance by name and namespace.
        
        :param name: Name of the VMI to retrieve
        :param namespace: Namespace of the VMI
        :return: The VMI object if found, None otherwise
        """
        try:
            vmi = self.custom_object_client.get_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=namespace,
                plural="virtualmachineinstances",
                name=name
            )
            return vmi
        except ApiException as e:
            if e.status == 404:
                logging.warning(
                    "VMI %s not found in namespace %s",
                    name,
                    namespace,
                )
                return None
            else:
                logging.error("Error getting VMI %s: %s", name, e)
                raise
        except Exception as e:
            logging.error("Unexpected error getting VMI %s: %s", name, e)
            raise
            
    def get_vmis(self, regex_name: str, namespace: str) -> Optional[Dict]:
        """
        Get a Virtual Machine Instance by name and namespace.
        
        :param name: Name of the VMI to retrieve
        :param namespace: Namespace of the VMI
        :return: The VMI object if found, None otherwise
        """
        try:
            namespaces = self.k8s_client.list_namespaces_by_regex(namespace)
            for namespace in namespaces:
                vmis = self.custom_object_client.list_namespaced_custom_object(
                    group="kubevirt.io",
                    version="v1",
                    namespace=namespace,
                    plural="virtualmachineinstances",
                )

                for vmi in vmis.get("items"):
                    vmi_name = vmi.get("metadata",{}).get("name")
                    match = re.match(regex_name, vmi_name)
                    if match:
                        self.vmis_list.append(vmi)
        except ApiException as e:
            if e.status == 404:
                logging.warning(
                    "VMI %s not found in namespace %s",
                    regex_name,
                    namespace,
                )
                return []
            else:
                logging.error("Error getting VMI %s: %s", regex_name, e)
                raise
        except Exception as e:
            logging.error("Unexpected error getting VMI %s: %s", regex_name, e)
            raise
    
    def execute_scenario(self, config: Dict[str, Any], scenario_telemetry: ScenarioTelemetry) -> int:
        """
        Execute a KubeVirt VM outage scenario based on the provided configuration.
        
        :param config: The scenario configuration
        :param scenario_telemetry: The telemetry object for recording metrics
        :return: 0 for success, 1 for failure
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
                return 1
            self.pods_status = PodsStatus()
            self.get_vmis(vm_name,namespace)
            for _ in range(kill_count):
                
                rand_int = random.randint(0, len(self.vmis_list) - 1)
                vmi = self.vmis_list[rand_int]
                    
                logging.info(
                    "Starting KubeVirt VM outage scenario for VM: %s in namespace: %s",
                    vm_name,
                    namespace,
                )
                vmi_name = vmi.get("metadata").get("name")
                vmi_namespace = vmi.get("metadata").get("namespace")
                if not self.validate_environment(vmi_name, vmi_namespace):
                    return 1
                    
                vmi = self.get_vmi(vmi_name, vmi_namespace)
                self.affected_pod = AffectedPod(
                    pod_name=vmi_name,
                    namespace=vmi_namespace,
                )
                if not vmi:
                    logging.error("VMI %s not found in namespace %s", vm_name, namespace)
                    return 1
                    
                self.original_vmi = vmi
                logging.info("Captured initial state of VMI: %s", vm_name)
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
                logging.info(
                    "Successfully completed KubeVirt VM outage scenario for VM: %s",
                    vm_name,
                )
            
            return self.pods_status
            
        except Exception as e:
            logging.error("Error executing KubeVirt VM outage scenario: %s", e)
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
            crd_list = self.custom_object_client.list_namespaced_custom_object("kubevirt.io","v1",namespace,"virtualmachines")
            kubevirt_crds = [crd for crd in crd_list.items() ]
            
            if not kubevirt_crds:
                logging.error("KubeVirt CRDs not found. Ensure KubeVirt/CNV is installed in the cluster")
                return False
                
            # Check if VMI exists
            vmi = self.get_vmi(vm_name, namespace)
            if not vmi:
                logging.error("VMI %s not found in namespace %s", vm_name, namespace)
                return False
                
            logging.info(
                "Validated environment: KubeVirt is installed and VMI %s exists",
                vm_name,
            )
            return True
            
        except Exception as e:
            logging.error("Error validating environment: %s", e)
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
            vm = self.custom_object_client.get_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=namespace,
                plural="virtualmachines",
                name=vm_name
            )
            
            # Update the running state
            if 'spec' not in vm:
                vm['spec'] = {}
            vm['spec']['running'] = running
            
            # Apply the patch
            self.custom_object_client.patch_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=namespace,
                plural="virtualmachines",
                name=vm_name,
                body=vm
            )
            return True
            
        except ApiException as e:
            logging.error("Failed to patch VM %s: %s", vm_name, e)
            return False
        except Exception as e:
            logging.error("Unexpected error patching VM %s: %s", vm_name, e)
            return False
            
    def delete_vmi(self, vm_name: str, namespace: str, disable_auto_restart: bool = False, timeout: int = 120) -> int:
        """
        Delete a Virtual Machine Instance to simulate a VM outage.
        
        :param vm_name: Name of the VMI to delete
        :param namespace: Namespace of the VMI
        :return: 0 for success, 1 for failure
        """
        try:
            logging.info(
                "Injecting chaos: Deleting VMI %s in namespace %s",
                vm_name,
                namespace,
            )
            
            # If auto-restart should be disabled, patch the VM spec first
            if disable_auto_restart:
                logging.info(
                    "Disabling auto-restart for VM %s by setting spec.running=False",
                    vm_name,
                )
                if not self.patch_vm_spec(vm_name, namespace, running=False):
                    logging.error("Failed to disable auto-restart for VM"
                               " - proceeding with deletion but VM may auto-restart")
            start_creation_time =  self.original_vmi.get('metadata', {}).get('creationTimestamp')
            start_time = time.time()
            try:
                self.custom_object_client.delete_namespaced_custom_object(
                    group="kubevirt.io",
                    version="v1",
                    namespace=namespace,
                    plural="virtualmachineinstances",
                    name=vm_name
                )
            except ApiException as e:
                if e.status == 404:
                    logging.warning("VMI %s not found during deletion", vm_name)
                    return 1
                else:
                    logging.error("API error during VMI deletion: %s", e)
                    return 1
            
            # Wait for the VMI to be deleted
            
            while time.time() - start_time < timeout:
                deleted_vmi = self.get_vmi(vm_name, namespace)
                if deleted_vmi:
                    if start_creation_time != deleted_vmi.get('metadata', {}).get('creationTimestamp'):
                        logging.info("VMI %s successfully recreated", vm_name)
                        self.affected_pod.pod_rescheduling_time = time.time() - start_time
                        return 0
                else: 
                    logging.info("VMI %s successfully deleted", vm_name)
                time.sleep(1)
                
            logging.error("Timed out waiting for VMI %s to be deleted", vm_name)
            self.pods_status.unrecovered.append(self.affected_pod)
            return 1
            
        except Exception as e:
            logging.error("Error deleting VMI %s: %s", vm_name, e)
            log_exception(e)
            self.pods_status.unrecovered.append(self.affected_pod)
            return 1

    def wait_for_running(self, vm_name: str, namespace: str, timeout: int = 120) -> int: 
        start_time = time.time()
        while time.time() - start_time < timeout: 

            # Check current state once since we've already waited for the duration
            vmi = self.get_vmi(vm_name, namespace)
            
            if vmi:
                if vmi.get('status', {}).get('phase') == "Running":
                    end_time = time.time()
                    self.affected_pod.pod_readiness_time = end_time - start_time

                    logging.info("VMI %s is already running", vm_name)
                    return 0
                logging.info(
                    "VMI %s exists but is not in Running state. Current state: %s",
                    vm_name,
                    vmi.get('status', {}).get('phase'),
                )
            else:
                logging.info("VMI %s not yet recreated", vm_name)
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
            logging.info(
                "Attempting to recover VMI %s in namespace %s",
                vm_name,
                namespace,
            )
            
            if self.original_vmi:
                logging.info(
                    "Auto-recovery didn't occur for VMI %s. Attempting manual recreation",
                    vm_name,
                )
                
                try:
                    # Clean up server-generated fields
                    vmi_dict = self.original_vmi.copy()
                    if 'metadata' in vmi_dict:
                        metadata = vmi_dict['metadata']
                        for field in ['resourceVersion', 'uid', 'creationTimestamp', 'generation']:
                            if field in metadata:
                                del metadata[field]
                    
                    # Create the VMI
                    self.custom_object_client.create_namespaced_custom_object(
                        group="kubevirt.io",
                        version="v1",
                        namespace=namespace,
                        plural="virtualmachineinstances",
                        body=vmi_dict
                    )
                    logging.info("Successfully recreated VMI %s", vm_name)
                    
                    # Wait for VMI to start running
                    self.wait_for_running(vm_name,namespace)
                    
                    logging.warning(
                        "VMI %s was recreated but didn't reach Running state in time",
                        vm_name,
                    )
                    return 0  # Still consider it a success as the VMI was recreated
                    
                except Exception as e:
                    logging.error("Error recreating VMI %s: %s", vm_name, e)
                    log_exception(e)
                    return 1
            else:
                logging.error(
                    "Failed to recover VMI %s: No original state captured and auto-recovery did not occur",
                    vm_name,
                )
                return 1
                
        except Exception as e:
            logging.error("Unexpected error recovering VMI %s: %s", vm_name, e)
            log_exception(e)
            return 1
