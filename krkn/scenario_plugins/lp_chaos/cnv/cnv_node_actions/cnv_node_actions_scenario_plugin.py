import logging
import time
from typing import Dict, Any
import yaml

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class CnvNodeActionsScenarioPlugin(AbstractScenarioPlugin):
    """
    CNV Node Actions Scenario Plugin.

    Orchestrates a two-phase chaos scenario:
    1. Infrastructure Phase: Delegates node operations (e.g., reboot, stop/start) 
       to the standard 'NodeActionsScenarioPlugin'.
    2. Verification Phase: Performs CNV-specific post-chaos checks.
    """

    def __init__(self, scenario_type: str = None):
        scenario_type = self.get_scenario_types()[0]
        super().__init__(scenario_type)
        self.k8s_client = None
        self.node_actions_plugin = None

    def get_scenario_types(self) -> list[str]:
        return ["cnv_node_actions"]

    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, Any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        """ Main entry point for the plugin. """
        try:
            # 1. Initialize Kubernetes client and the delegate plugin
            self.init_clients(lib_telemetry.get_lib_kubernetes(), krkn_config)
            
            # 2. Load configuration to retrieve CNV-specific parameters later
            config = self.load_config(scenario)
            
            # 3. Execute the core logic
            return self.execute_scenario(config, scenario_telemetry, krkn_config, run_uuid, scenario, lib_telemetry)
        except Exception as e:
            logging.error(f"CNV Node Actions scenario failed with exception: {e}")
            return 1

    def init_clients(self, k8s_client: KrknKubernetes, krkn_config: dict[str, Any]):
        """
        Initialize the Kubernetes client and instantiate the standard NodeActionsScenarioPlugin.
        """
        from krkn.scenario_plugins.node_actions.node_actions_scenario_plugin import NodeActionsScenarioPlugin
        self.k8s_client = k8s_client
        # Instantiate the standard plugin to use its logic for cloud node operations
        self.node_actions_plugin = NodeActionsScenarioPlugin()
        logging.info("Successfully initialized clients and NodeActions plugin.")

    def load_config(self, scenario_file: str) -> Dict[str, Any]:
        """
        Load the scenario configuration from the YAML file.
        Handles the specific structure where 'node_scenarios' is a list.
        """
        try:
            with open(scenario_file, "r") as f:
                root_config = yaml.safe_load(f)
            
            # The YAML structure is a list under "node_scenarios".
            if "node_scenarios" in root_config and isinstance(root_config["node_scenarios"], list):
                 return root_config["node_scenarios"][0]
            
            return root_config
        except Exception as e:
            logging.error(f"Error loading scenario configuration: {e}")
            raise

    def execute_scenario(
        self, 
        config: Dict[str, Any], 
        scenario_telemetry: ScenarioTelemetry, 
        krkn_config: dict[str, Any], 
        run_uuid: str, 
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift
    ) -> int:
        """
        Orchestrates the test: Delegation -> Verification.
        """
        try:
            # --- Phase 1: Delegate Node Chaos Injection ---
            logging.info(f"Phase 1: Delegating node actions to NodeActionsScenarioPlugin using scenario: {scenario}")
            exit_code = self.node_actions_plugin.run(
                run_uuid, 
                scenario,
                krkn_config,
                lib_telemetry, 
                scenario_telemetry
            )
            
            if exit_code != 0:
                logging.error("Phase 1 Failed: Standard Node actions execution returned error.")
                return exit_code
            
            logging.info("Phase 1 Complete: Node actions finished successfully.")

            # --- Phase 2: CNV-Post-Chaos Verification (CNV Specific) ---
            cnv_post_chaos_action = config.get("cnv_post_chaos_action")
            if not cnv_post_chaos_action:
                logging.warning("No 'cnv_post_chaos_action' specified. Skipping Phase 2.")
                return 0

            logging.info(f"Phase 2: Starting CNV post-chaos check -> '{cnv_post_chaos_action}'")

            # Route to the specific verification logic
            if cnv_post_chaos_action == "ssh_vm":
                self.check_vm_ssh_connectivity(config)
            elif cnv_post_chaos_action == "create_vm":
                self.create_vm(config)
            elif cnv_post_chaos_action == "create_snapshot":
                self.create_snapshot(config)
            else:
                logging.warning(f"Unknown cnv_post_chaos_action: '{cnv_post_chaos_action}', skipping verification.")

            logging.info("CNV Node Actions Scenario completed successfully.")
            return 0

        except Exception as e:
            logging.error(f"Error executing CNV node actions scenario: {e}")
            return 1


    # --- Helper Methods for Phase 2 ---
    def create_snapshot(self, config: Dict[str, Any]):
        """
        Creates a VM snapshot and waits for it to become ready.
        """
        vm_name = config.get("vm_name")
        snapshot_name = config.get("snapshot_name")
        namespace = config.get("vm_namespace", "default")
        timeout = config.get("snapshot_timeout", 60)

        if not all([vm_name, snapshot_name]):
            raise ValueError("'vm_name' and 'snapshot_name' are required for 'create_snapshot' action.")

        logging.info(f"Creating snapshot '{snapshot_name}' for VM '{vm_name}' in namespace '{namespace}'...")
        self.k8s_client.create_snapshot(name=snapshot_name, namespace=namespace, vm_name=vm_name)

        logging.info(f"Waiting for snapshot '{snapshot_name}' to be Ready (timeout: {timeout}s)...")
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Snapshot '{snapshot_name}' did not become ready within {timeout} seconds.")
            
            snap = self.k8s_client.get_snapshot(name=snapshot_name, namespace=namespace)
            if snap:
                status = snap.get("status", {})
                phase = status.get("phase", "Unknown")
                ready = status.get("readyToUse", False)

                if ready:
                    logging.info(f"Snapshot '{snapshot_name}' is successfully created and Ready.")
                    break
                if phase == "Failed":
                    raise Exception(f"Snapshot creation failed. Status: {status}")
            
            time.sleep(5)

    def create_vm(self, config: Dict[str, Any]):
        """
        Creates a KubeVirt VM from a YAML manifest file, dynamically setting its
        name and namespace, and then waits for the VMI to enter the 'Running' phase.
        """
        vm_manifest_path = config.get("vm_manifest_path")
        vm_name = config.get("vm_name")
        namespace = config.get("vm_namespace", "default")
        timeout = config.get("vm_timeout", 1200)

        if not vm_manifest_path or not vm_name:
            raise ValueError("'vm_manifest_path' and 'vm_name' are required for the 'create_vm' action.")

        logging.info(f"Loading VM manifest from: {vm_manifest_path}")
        try:
            with open(vm_manifest_path, "r") as f:
                vm_body = yaml.safe_load(f)
        except Exception as e:
            logging.error(f"Failed to load or parse VM manifest at {vm_manifest_path}: {e}")
            raise

        # Override name and namespace from config
        vm_body.setdefault("metadata", {})["name"] = vm_name
        vm_body["metadata"]["namespace"] = namespace

        logging.info(f"Attempting to create VM '{vm_name}' in namespace '{namespace}'...")
        self.k8s_client.custom_object_client.create_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            body=vm_body,
        )
        logging.info(f"Successfully submitted VM '{vm_name}'. Now waiting for it to become Running...")

        self.check_vm_running_status(config)

    def check_vm_running_status(self, config: Dict[str, Any]):
        """
        Checks if a VM is running by polling its VMI status.
        """
        vm_name = config.get("vm_name")
        namespace = config.get("vm_namespace", "default")
        timeout = config.get("vm_timeout", 1200)
        
        if not vm_name:
            raise ValueError("'vm_name' is required for this action.")
        
        logging.info(f"Checking for VMI '{vm_name}' to enter 'Running' phase in namespace '{namespace}' (timeout: {timeout}s)...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            vmi = self.k8s_client.get_vmi(name=vm_name, namespace=namespace)
            if vmi:
                phase = vmi.get("status", {}).get("phase")
                if phase == "Running":
                    logging.info(f"SUCCESS: VMI '{vm_name}' is in 'Running' phase.")
                    return
                else:
                    logging.info(f"VMI '{vm_name}' found, but phase is '{phase}'. Retrying...")
            else:
                logging.info(f"VMI '{vm_name}' not found yet. Retrying...")
            
            time.sleep(300) # Poll every 5 mins

        raise Exception(f"TIMEOUT: VMI '{vm_name}' did not enter 'Running' phase within {timeout} seconds.")

    def check_vm_ssh_connectivity(self, config: Dict[str, Any]):
        vm_name = config.get("vm_name")
        namespace = config.get("vm_namespace", "default")
        ssh_pod_name = f"vm-ssh-check-{int(time.time())}"
        timeout = 120 

        if not vm_name:
            raise ValueError("'vm_name' is required.")

        self.check_vm_running_status(config)

        # Helper pod to run virtctl
        pod_body = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": ssh_pod_name, "namespace": namespace},
            "spec": {
                "containers": [{
                    "name": "virtctl",
                    "image": "quay.io/fedora/fedora:latest",
                    "command": [
                        "/bin/bash", 
                        "-c", 
                        "export VERSION=$(curl -s https://storage.googleapis.com/kubevirt-prow/release/kubevirt/kubevirt/stable.txt) && "
                        "echo Downloading virtctl version: $VERSION && "
                        "curl -L -o /usr/local/bin/virtctl https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/virtctl-${VERSION}-linux-amd64 && "
                        "chmod +x /usr/local/bin/virtctl && "
                        "sleep 3600"
                    ],
                }],
                "restartPolicy": "Never",
                "serviceAccountName": "default", 
            },
        }

        try:
            logging.info(f"Creating SSH check pod '{ssh_pod_name}'...")
            self.k8s_client.create_pod(body=pod_body, namespace=namespace)

            # Wait for pod Running
            start_time = time.time()
            while time.time() - start_time < timeout:
                pod = self.k8s_client.get_pod_info(name=ssh_pod_name, namespace=namespace)
                if pod and pod.status == "Running":
                    break
                time.sleep(2)
            else:
                raise Exception(f"SSH check pod '{ssh_pod_name}' failed to start.")

            # Using 'root' as dummy user to satisfy SSH syntax
            ssh_cmd = [
                "virtctl", "ssh", 
                f"root@{vm_name}", 
                "--namespace", namespace,
                "--known-hosts-file=/dev/null",
                "--identity-file=/dev/null",
                "--command", "exit"
            ]
            
            logging.info(f"Probing SSH port on VM '{vm_name}'...")
            
            try:
                self.k8s_client.exec_cmd_in_pod(
                    command=ssh_cmd,
                    pod_name=ssh_pod_name,
                    namespace=namespace,
                    container="virtctl"
                )
                logging.info("SSH connection established.")

            except Exception as e:
                error_msg = str(e)
                # Success: Permission denied means we reached the SSH service
                if "Permission denied" in error_msg or "authentication failed" in error_msg:
                    logging.info(f"SUCCESS: SSH port is reachable (Auth failed as expected).")
                    return 0
                
                # Failure: Network unreachable or timeout
                if "Connection refused" in error_msg or "timed out" in error_msg:
                    raise Exception(f"FAILED: SSH unreachable. Error: {error_msg}")
                
                logging.warning(f"Ambiguous SSH error: {error_msg}")
                raise e

        except Exception as e:
            logging.error(f"SSH check failed: {e}")
            raise e
        finally:
            logging.info(f"Deleting pod '{ssh_pod_name}'...")
            try:
                self.k8s_client.delete_pod(name=ssh_pod_name, namespace=namespace)
            except Exception:
                pass