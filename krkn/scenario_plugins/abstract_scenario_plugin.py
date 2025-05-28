import logging
import signal
import sys
import time
import json
import os
import threading
import queue
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Union
from kubernetes import client
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.k8s import KrknKubernetes

from krkn import utils


class ResourceTracker:
    """Thread-safe tracker for resources created during scenarios.
    
    This tracker maintains both an in-memory queue and disk persistence of resources
    to ensure resources can be cleaned up even after unexpected shutdowns.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self._resources = queue.Queue()
        self._lock = threading.Lock()
        self._storage_path = storage_path or os.path.join("artifacts", "resource_tracker.json")
        os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
        self._load_from_disk()
    
    def add_resource(self, resource_type: str, name: str, namespace: str = None, original_yaml: dict = None):
        """Add a resource to be tracked for cleanup."""
        resource = {
            "type": resource_type,
            "name": name,
            "namespace": namespace,
            "original_yaml": original_yaml,
            "timestamp": time.time()
        }
        with self._lock:
            self._resources.put(resource)
            self._save_to_disk()
    
    def get_all_resources(self) -> List[Dict[str, Any]]:
        """Get all tracked resources."""
        with self._lock:
            return list(self._resources.queue)
    
    def clear_resources(self):
        """Clear all tracked resources."""
        with self._lock:
            while not self._resources.empty():
                self._resources.get()
            self._save_to_disk()
    
    def _save_to_disk(self):
        """Save resources to disk."""
        try:
            with open(self._storage_path, 'w') as f:
                json.dump(list(self._resources.queue), f)
        except Exception as e:
            logging.error(f"Error saving resource tracker to disk: {e}")
    
    def _load_from_disk(self):
        if os.path.exists(self._storage_path):
            try:
                with open(self._storage_path, 'r') as f:
                    resources = json.load(f)
                    for resource in resources:
                        self._resources.put(resource)
            except Exception as e:
                logging.error(f"Error loading resource tracker from disk: {e}")


class AbstractScenarioPlugin(ABC):
    def __init__(self):
        """Initialize the scenario plugin with a resource tracker and signal handlers."""
        self._resource_tracker = ResourceTracker()
        self._original_sigint_handler = signal.getsignal(signal.SIGINT)
        self._original_sigterm_handler = signal.getsignal(signal.SIGTERM)
        # Setup signal handlers for cleanup
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle interruption signals by performing cleanup before exiting."""
        logging.info(f"Received signal {signum}, running cleanup...")
        try:
            self.cleanup()
        except Exception as e:
            logging.error(f"Error during cleanup after signal {signum}: {e}")
        finally:
            # Restore original signal handlers
            signal.signal(signal.SIGINT, self._original_sigint_handler)
            signal.signal(signal.SIGTERM, self._original_sigterm_handler)
            # Re-raise the signal to trigger the original handler
            if signum == signal.SIGINT:
                raise KeyboardInterrupt
            else:
                sys.exit(128 + signum)
    
    def cleanup(self):
        """Base cleanup method to handle common resource cleanup.
        
        This method should be overridden by scenarios that need specific cleanup logic.
        The base implementation uses the resource tracker to clean up common resources.
        
        Implementation strategy:
        1. Uses tracked resources to perform cleanup in reverse order of creation
        2. Handles various Kubernetes resource types with appropriate deletion methods
        3. Falls back gracefully when resource cleanup fails
        """
        logging.info("Running base plugin cleanup")
        resources = self._resource_tracker.get_all_resources()
        kubernetes_client = client.ApiClient()
        
        # Clean up resources in reverse order of creation (newest first)
        for resource in sorted(resources, key=lambda x: x.get('timestamp', 0), reverse=True):
            try:
                resource_type = resource.get('type')
                name = resource.get('name')
                namespace = resource.get('namespace')
                original_yaml = resource.get('original_yaml')
                
                if not all([resource_type, name]):
                    logging.warning(f"Incomplete resource information: {resource}")
                    continue
                
                logging.info(f"Cleaning up {resource_type} {name} in namespace {namespace or 'default'}")
                
                # Handle different resource types with appropriate API calls
                if resource_type == 'pod':
                    self._delete_pod(kubernetes_client, name, namespace)
                elif resource_type == 'deployment':
                    self._delete_deployment(kubernetes_client, name, namespace)
                elif resource_type == 'service':
                    self._delete_service(kubernetes_client, name, namespace)
                elif resource_type == 'configmap':
                    self._delete_configmap(kubernetes_client, name, namespace)
                elif resource_type == 'secret':
                    self._delete_secret(kubernetes_client, name, namespace)
                elif resource_type == 'namespace':
                    self._delete_namespace(kubernetes_client, name)
                else:
                    logging.warning(f"Unknown resource type {resource_type}, skipping")
            except Exception as e:
                logging.error(f"Error cleaning up resource {resource}: {e}")
        
        # Clear the resource tracker after cleanup
        self._resource_tracker.clear_resources()
    
    def _delete_pod(self, k8s_client, name, namespace):
        api_instance = client.CoreV1Api(k8s_client)
        api_instance.delete_namespaced_pod(name=name, namespace=namespace or 'default')
    
    def _delete_deployment(self, k8s_client, name, namespace):
        api_instance = client.AppsV1Api(k8s_client)
        api_instance.delete_namespaced_deployment(name=name, namespace=namespace or 'default')
    
    def _delete_service(self, k8s_client, name, namespace):
        api_instance = client.CoreV1Api(k8s_client)
        api_instance.delete_namespaced_service(name=name, namespace=namespace or 'default')
    
    def _delete_configmap(self, k8s_client, name, namespace):
        api_instance = client.CoreV1Api(k8s_client)
        api_instance.delete_namespaced_config_map(name=name, namespace=namespace or 'default')
    
    def _delete_secret(self, k8s_client, name, namespace):
        api_instance = client.CoreV1Api(k8s_client)
        api_instance.delete_namespaced_secret(name=name, namespace=namespace or 'default')
    
    def _delete_namespace(self, k8s_client, name):
        api_instance = client.CoreV1Api(k8s_client)
        api_instance.delete_namespace(name=name)
    
    def track_resource(self, resource_type: str, name: str, namespace: str = None, original_yaml: dict = None):
        """Track a resource for cleanup."""
        self._resource_tracker.add_resource(resource_type, name, namespace, original_yaml)
    
    @abstractmethod
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        """
        This method serves as the entry point for a ScenarioPlugin. To make the plugin loadable,
        the AbstractScenarioPlugin class must be extended, and this method must be implemented.
        No exception must be propagated outside of this method.

        :param run_uuid: the uuid of the chaos run generated by krkn for every single run
        :param scenario: the config file of the scenario that is currently executed
        :param krkn_config: the full dictionary representation of the `config.yaml`
        :param lib_telemetry: it is a composite object of all the
        krkn-lib objects and methods needed by a krkn plugin to run.
        :param scenario_telemetry: the `ScenarioTelemetry` object of the scenario that is currently executed
        :return: 0 if the scenario suceeded 1 if failed
        """
        try:
            # Actual implementation in the derived class
            result = self._run_implementation(
                run_uuid, scenario, krkn_config, lib_telemetry, scenario_telemetry
            )
            return result
        except Exception as e:
            logging.error(f"Exception in scenario execution: {e}")
            try:
                self.cleanup()
            except Exception as cleanup_error:
                logging.error(f"Error during cleanup after exception: {cleanup_error}")
                if self._cleanup_helper is not None:
                    self._cleanup_helper()
            return 1
    
    @abstractmethod
    def _run_implementation(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        """Actual implementation of the scenario to be provided by derived classes."""
        pass

    @abstractmethod
    def get_scenario_types(self) -> list[str]:
        """
        Indicates the scenario types specified in the `config.yaml`. For the plugin to be properly
        loaded, recognized and executed, it must be implemented and must return the matching `scenario_type` strings.
        One plugin can be mapped one or many different strings unique across the other plugins otherwise an exception
        will be thrown.


        :return: the corresponding scenario_type as a list of strings
        """
        pass

    def run_scenarios(
        self,
        run_uuid: str,
        scenarios_list: list[str],
        krkn_config: dict[str, any],
        telemetry: KrknTelemetryOpenshift,
    ) -> tuple[list[str], list[ScenarioTelemetry]]:

        scenario_telemetries: list[ScenarioTelemetry] = []
        failed_scenarios = []
        wait_duration = krkn_config["tunings"]["wait_duration"]
        events_backup = krkn_config["telemetry"]["events_backup"]
        for scenario_config in scenarios_list:
            if isinstance(scenario_config, list):
                logging.error(
                    "post scenarios have been deprecated, please "
                    "remove sub-lists from `scenarios` in config.yaml"
                )
                failed_scenarios.append(scenario_config)
                break

            scenario_telemetry = ScenarioTelemetry()
            scenario_telemetry.scenario = scenario_config
            scenario_telemetry.scenario_type = self.get_scenario_types()[0]
            scenario_telemetry.start_timestamp = time.time()
            parsed_scenario_config = telemetry.set_parameters_base64(
                scenario_telemetry, scenario_config
            )

            try:
                logging.info(
                    f"Running {self.__class__.__name__}: {self.get_scenario_types()} -> {scenario_config}"
                )
                return_value = self.run(
                    run_uuid,
                    scenario_config,
                    krkn_config,
                    telemetry,
                    scenario_telemetry,
                )
            except Exception as e:
                logging.error(
                    f"uncaught exception on scenario `run()` method: {e} "
                    f"please report an issue on https://github.com/krkn-chaos/krkn"
                )
                return_value = 1

            scenario_telemetry.exit_status = return_value
            scenario_telemetry.end_timestamp = time.time()
            utils.collect_and_put_ocp_logs(
                telemetry,
                parsed_scenario_config,
                telemetry.get_telemetry_request_id(),
                int(scenario_telemetry.start_timestamp),
                int(scenario_telemetry.end_timestamp),
            )

            if events_backup: 
                utils.populate_cluster_events(
                    krkn_config,
                    parsed_scenario_config,
                    telemetry.get_lib_kubernetes(),
                    int(scenario_telemetry.start_timestamp),
                    int(scenario_telemetry.end_timestamp),
                )

            if scenario_telemetry.exit_status != 0:
                failed_scenarios.append(scenario_config)
            scenario_telemetries.append(scenario_telemetry)
            logging.info(f"wating {wait_duration} before running the next scenario")
            time.sleep(wait_duration)
        return failed_scenarios, scenario_telemetries
