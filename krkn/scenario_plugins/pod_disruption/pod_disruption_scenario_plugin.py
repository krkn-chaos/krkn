import logging
import random
import time
from asyncio import Future
import traceback
import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.k8s.pod_monitor import select_and_monitor_by_namespace_pattern_and_label, \
    select_and_monitor_by_name_pattern_and_namespace_pattern

from krkn.scenario_plugins.pod_disruption.models.models import InputParams
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.pod_monitor.models import PodsSnapshot
from datetime import datetime
from dataclasses import dataclass

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin

@dataclass
class Pod:
    namespace: str
    name: str
    creation_timestamp : str

class PodDisruptionScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario, "r") as f:
                cont_scenario_config = yaml.full_load(f)
                for kill_scenario in cont_scenario_config:
                    kill_scenario_config = InputParams(kill_scenario["config"])
                    future_snapshot=self.start_monitoring(
                        kill_scenario_config,
                        lib_telemetry
                    )
                    ret = self.killing_pods(
                        kill_scenario_config, lib_telemetry.get_lib_kubernetes()
                    )
                    # returning 2 if configuration issue and exiting immediately
                    if ret > 1:
                        # Cancel the monitoring future since killing_pods already failed
                        logging.info("Cancelling pod monitoring future")
                        future_snapshot.cancel()
                        # Wait for the future to finish (monitoring will stop when stop_event is set)
                        while not future_snapshot.done():
                            logging.info("waiting for future to finish")
                            time.sleep(1)
                        logging.info("future snapshot cancelled and finished")
                        # Get the snapshot result (even if cancelled, it will have partial data)
                        snapshot = future_snapshot.result()
                        result = snapshot.get_pods_status()
                        scenario_telemetry.affected_pods = result

                        logging.error("PodDisruptionScenarioPlugin failed during setup" + str(result))
                        return 1
                    
                    snapshot = future_snapshot.result()
                    result = snapshot.get_pods_status()
                    scenario_telemetry.affected_pods = result
                    if len(result.unrecovered) > 0:
                        logging.info("PodDisruptionScenarioPlugin failed with unrecovered pods")
                        return 1

                    if ret > 0:
                        logging.info("PodDisruptionScenarioPlugin failed")
                        return 1
                    
        except (RuntimeError, Exception) as e:
            logging.error("Stack trace:\n%s", traceback.format_exc())
            logging.error("PodDisruptionScenariosPlugin exiting due to Exception %s" % e)
            return 1
        else:
            return 0

    def get_scenario_types(self) -> list[str]:
        return ["pod_disruption_scenarios"]

    def start_monitoring(self, kill_scenario: InputParams, lib_telemetry: KrknTelemetryOpenshift) -> Future:

        recovery_time = kill_scenario.krkn_pod_recovery_time
        if (
            kill_scenario.namespace_pattern
            and kill_scenario.label_selector
        ):
            namespace_pattern = kill_scenario.namespace_pattern
            label_selector = kill_scenario.label_selector
            future_snapshot = select_and_monitor_by_namespace_pattern_and_label(
                namespace_pattern=namespace_pattern,
                label_selector=label_selector,
                max_timeout=recovery_time,
                v1_client=lib_telemetry.get_lib_kubernetes().cli
            )
            logging.info(
                f"waiting up to {recovery_time} seconds for pod recovery, "
                f"pod label pattern: {label_selector} namespace pattern: {namespace_pattern}"
            )
            return future_snapshot

        elif (
            kill_scenario.namespace_pattern
            and kill_scenario.name_pattern
        ):
            namespace_pattern = kill_scenario.namespace_pattern
            name_pattern = kill_scenario.name_pattern
            future_snapshot = select_and_monitor_by_name_pattern_and_namespace_pattern(
                pod_name_pattern=name_pattern,
                namespace_pattern=namespace_pattern,
                max_timeout=recovery_time,
                v1_client=lib_telemetry.get_lib_kubernetes().cli
            )
            logging.info(
                f"waiting up to {recovery_time} seconds for pod recovery, "
                f"pod name pattern: {name_pattern} namespace pattern: {namespace_pattern}"
            )
            return future_snapshot
        else:
            raise Exception(
                f"impossible to determine monitor parameters, check {kill_scenario} configuration"
            )
    
    def _select_pods_with_field_selector(self, name_pattern, label_selector, namespace, kubecli: KrknKubernetes, field_selector: str, node_name: str = None):
        """Helper function to select pods using either label_selector or name_pattern with field_selector, optionally filtered by node"""
        # Combine field selectors if node targeting is specified
        if node_name:
            node_field_selector = f"spec.nodeName={node_name}"
            if field_selector:
                combined_field_selector = f"{field_selector},{node_field_selector}"
            else:
                combined_field_selector = node_field_selector
        else:
            combined_field_selector = field_selector
        
        if label_selector:
            return kubecli.select_pods_by_namespace_pattern_and_label(
                label_selector=label_selector, 
                namespace_pattern=namespace, 
                field_selector=combined_field_selector
            )
        else:  # name_pattern
            return kubecli.select_pods_by_name_pattern_and_namespace_pattern(
                pod_name_pattern=name_pattern, 
                namespace_pattern=namespace, 
                field_selector=combined_field_selector
            )

    def get_pods(self, name_pattern, label_selector, namespace, kubecli: KrknKubernetes, field_selector: str = None, node_label_selector: str = None, node_names: list = None): 
        if label_selector and name_pattern: 
            logging.error('Only, one of name pattern or label pattern can be specified')
            return []
        
        if not label_selector and not name_pattern:
            logging.error('Name pattern or label pattern must be specified ')
            return []
        
        # If specific node names are provided, make multiple calls with field selector
        if node_names:
            logging.debug(f"Targeting pods on {len(node_names)} specific nodes")
            all_pods = []
            for node_name in node_names:
                pods = self._select_pods_with_field_selector(
                    name_pattern, label_selector, namespace, kubecli, field_selector, node_name
                )
                
                if pods:
                    all_pods.extend(pods)
            
            logging.debug(f"Found {len(all_pods)} target pods across {len(node_names)} nodes")
            return all_pods
        
        #  Node label selector approach - use field selectors
        if node_label_selector:
            # Get nodes matching the label selector first
            nodes_with_label = kubecli.list_nodes(label_selector=node_label_selector)
            if not nodes_with_label:
                logging.debug(f"No nodes found with label selector: {node_label_selector}")
                return []
            
            logging.debug(f"Targeting pods on {len(nodes_with_label)} nodes with label: {node_label_selector}")
            # Use field selector for each node
            all_pods = []
            for node_name in nodes_with_label:
                pods = self._select_pods_with_field_selector(
                    name_pattern, label_selector, namespace, kubecli, field_selector, node_name
                )
                
                if pods:
                    all_pods.extend(pods)
            
            logging.debug(f"Found {len(all_pods)} target pods across {len(nodes_with_label)} nodes")
            return all_pods
        
        # Standard pod selection (no node targeting)
        return self._select_pods_with_field_selector(
            name_pattern, label_selector, namespace, kubecli, field_selector
        )
    
    def killing_pods(self, config: InputParams, kubecli: KrknKubernetes):
        # region Select target pods
        try:
            namespace = config.namespace_pattern
            if not namespace: 
                logging.error('Namespace pattern must be specified')

            pods = self.get_pods(config.name_pattern,config.label_selector,config.namespace_pattern, kubecli, field_selector="status.phase=Running", node_label_selector=config.node_label_selector, node_names=config.node_names)
            exclude_pods = set()
            if config.exclude_label:
                _exclude_pods = self.get_pods("",config.exclude_label,config.namespace_pattern, kubecli, field_selector="status.phase=Running", node_label_selector=config.node_label_selector, node_names=config.node_names)
                for pod in _exclude_pods:
                    exclude_pods.add(pod[0])


            pods_count = len(pods)
            if len(pods) < config.kill:
                logging.error("Not enough pods match the criteria, expected {} but found only {} pods".format(
                        config.kill, len(pods)))
                return 1
            
            random.shuffle(pods)
            for i in range(config.kill):
                pod = pods[i]
                logging.info(pod)
                if pod[0] in exclude_pods:
                    logging.info(f"Excluding {pod[0]} from chaos")
                else:
                    logging.info(f'Deleting pod {pod[0]}')
                    kubecli.delete_pod(pod[0], pod[1])
            
            return_val = self.wait_for_pods(config.label_selector,config.name_pattern,config.namespace_pattern, pods_count, config.duration, config.timeout, kubecli, config.node_label_selector, config.node_names)
        except Exception as e:
            raise(e)

        return return_val

    def wait_for_pods(
        self, label_selector, pod_name, namespace, pod_count, duration, wait_timeout, kubecli: KrknKubernetes, node_label_selector, node_names
    ):
        timeout = False
        start_time = datetime.now()

        while not timeout:
            pods = self.get_pods(name_pattern=pod_name, label_selector=label_selector,namespace=namespace, field_selector="status.phase=Running", kubecli=kubecli, node_label_selector=node_label_selector, node_names=node_names)
            if pod_count == len(pods):
                return 0
            
            time.sleep(duration)

            now_time = datetime.now()

            time_diff = now_time - start_time
            if time_diff.seconds > wait_timeout:
                logging.error("timeout while waiting for pods to come up")
                return 1

        return 0
