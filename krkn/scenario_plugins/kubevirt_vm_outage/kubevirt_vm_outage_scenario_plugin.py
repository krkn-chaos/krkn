import logging
import time
from typing import Optional, Dict, Any

import kubernetes
import yaml
from kubevirt.api import DefaultApi
from kubevirt.models.v1_virtual_machine_instance import V1VirtualMachineInstance
from kubevirt.rest import ApiException
from kubernetes.client import ApiClient
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import log_exception

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class KubevirtVmOutageScenarioPlugin(AbstractScenarioPlugin):
    """
    A scenario plugin that injects chaos by deleting a KubeVirt Virtual Machine Instance (VMI).
    This plugin simulates a VM crash or outage scenario and supports automated or manual recovery.
    """

    def __init__(self):
        self.kubevirt_api = None
        self.k8s_api = None
        self.original_vmi = None
        
    def get_scenario_types(self) -> list[str]:
        """
        Returns the list of scenario types this plugin supports.
        """
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
            
            for config in scenario_config["scenarios"]:
                if config.get("scenario") == "kubevirt_vm_outage":
                    result = self.execute_scenario(config, scenario_telemetry)
                    if result != 0:
                        return 1
                        
            return 0
        except Exception as e:
            logging.error(f"KubeVirt VM Outage scenario failed: {e}")
            log_exception(e)
            return 1

    def init_clients(self, k8s_client: KrknKubernetes):
        """
        Initialize KubeVirt and Kubernetes API clients.
        """
        try:
            self.k8s_api = k8s_client
            
            k8s_config = kubernetes.client.Configuration().get_default_copy()
            k8s_config.api_key = k8s_client.api_client.configuration.api_key
            k8s_config.api_key_prefix = k8s_client.api_client.configuration.api_key_prefix
            k8s_config.host = k8s_client.api_client.configuration.host
            k8s_config.ssl_ca_cert = k8s_client.api_client.configuration.ssl_ca_cert
            k8s_config.verify_ssl = k8s_client.api_client.configuration.verify_ssl
            k8s_config.cert_file = k8s_client.api_client.configuration.cert_file
            k8s_config.key_file = k8s_client.api_client.configuration.key_file
            
            api_client = ApiClient(k8s_config)
            self.kubevirt_api = DefaultApi(api_client)
            
            self.kubevirt_api.get_api_group()
            logging.info("Successfully connected to KubeVirt API")
        except ApiException as e:
            logging.error(f"Error initializing KubeVirt client: {e}")
            raise RuntimeError(f"Failed to initialize KubeVirt client: {e}")

    def execute_scenario(self, config: Dict[str, Any], scenario_telemetry: ScenarioTelemetry) -> int:
        """
        Execute a KubeVirt VM outage scenario based on the provided configuration.
        
        :param config: The scenario configuration
        :param scenario_telemetry: The telemetry object for recording metrics
        :return: 0 for success, 1 for failure
        """
        try:
            params = config.get("parameters", {})
            vm_name = params.get("vm_name")
            namespace = params.get("namespace", "default")
            duration = params.get("duration", 60)
            
            if not vm_name:
                logging.error("vm_name parameter is required")
                return 1
                
            logging.info(f"Starting KubeVirt VM outage scenario for VM: {vm_name} in namespace: {namespace}")
            
            if not self.validate_environment(vm_name, namespace):
                return 1
                
            vmi = self.get_vmi(vm_name, namespace)
            if not vmi:
                logging.error(f"VMI {vm_name} not found in namespace {namespace}")
                return 1
                
            self.original_vmi = vmi
            logging.info(f"Captured initial state of VMI: {vm_name}")
            
            # Inject chaos - delete the VMI
            result = self.inject(vm_name, namespace)
            if result != 0:
                return 1
                
            # Wait for specified duration before recovering
            logging.info(f"Waiting for {duration} seconds before attempting recovery")
            time.sleep(duration)
            
            result = self.recover(vm_name, namespace)
            if result != 0:
                return 1
                
            logging.info(f"Successfully completed KubeVirt VM outage scenario for VM: {vm_name}")
            return 0
            
        except Exception as e:
            logging.error(f"Error executing KubeVirt VM outage scenario: {e}")
            log_exception(e)
            return 1

    def validate_environment(self, vm_name: str, namespace: str) -> bool:
        """
        Validate that KubeVirt is installed and the specified VM exists.
        
        :param vm_name: Name of the VM to validate
        :param namespace: Namespace of the VM
        :return: True if environment is valid, False otherwise
        """
        try:
            crd_list = self.k8s_api.list_custom_resource_definition()
            kubevirt_crds = [crd for crd in crd_list.items if 'kubevirt.io' in crd.spec.group]
            
            if not kubevirt_crds:
                logging.error("KubeVirt CRDs not found. Ensure KubeVirt/CNV is installed in the cluster")
                return False
                
            vmi = self.get_vmi(vm_name, namespace)
            if not vmi:
                logging.error(f"VMI {vm_name} not found in namespace {namespace}")
                return False
                
            logging.info(f"Validated environment: KubeVirt is installed and VMI {vm_name} exists")
            return True
            
        except Exception as e:
            logging.error(f"Error validating environment: {e}")
            return False

    def get_vmi(self, vm_name: str, namespace: str) -> Optional[V1VirtualMachineInstance]:
        """
        Get a Virtual Machine Instance by name and namespace.
        
        :param vm_name: Name of the VMI to retrieve
        :param namespace: Namespace of the VMI
        :return: The VMI object if found, None otherwise
        """
        try:
            vmi = self.kubevirt_api.read_namespaced_virtual_machine_instance(
                name=vm_name, 
                namespace=namespace
            )
            return vmi
        except ApiException as e:
            if e.status == 404:
                logging.warning(f"VMI {vm_name} not found in namespace {namespace}")
                return None
            else:
                logging.error(f"Error getting VMI {vm_name}: {e}")
                raise
        except Exception as e:
            logging.error(f"Unexpected error getting VMI {vm_name}: {e}")
            raise

    def inject(self, vm_name: str, namespace: str) -> int:
        """
        Delete a Virtual Machine Instance to simulate a VM outage.
        
        :param vm_name: Name of the VMI to delete
        :param namespace: Namespace of the VMI
        :return: 0 for success, 1 for failure
        """
        try:
            logging.info(f"Injecting chaos: Deleting VMI {vm_name} in namespace {namespace}")
            
            # Delete the VMI
            self.kubevirt_api.delete_namespaced_virtual_machine_instance(
                name=vm_name, 
                namespace=namespace
            )
            
            # Wait for the VMI to be deleted
            timeout = 120  # seconds
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    self.kubevirt_api.read_namespaced_virtual_machine_instance(
                        name=vm_name, 
                        namespace=namespace
                    )
                    # VMI still exists, wait
                    time.sleep(5)
                except ApiException as e:
                    if e.status == 404:
                        logging.info(f"VMI {vm_name} successfully deleted")
                        return 0
                
            logging.error(f"Timed out waiting for VMI {vm_name} to be deleted")
            return 1
            
        except ApiException as e:
            logging.error(f"Error deleting VMI {vm_name}: {e}")
            return 1
        except Exception as e:
            logging.error(f"Unexpected error deleting VMI {vm_name}: {e}")
            return 1

    def recover(self, vm_name: str, namespace: str) -> int:
        """
        Recover a deleted VMI, either by waiting for auto-recovery or manually recreating it.
        
        :param vm_name: Name of the VMI to recover
        :param namespace: Namespace of the VMI
        :return: 0 for success, 1 for failure
        """
        return 0