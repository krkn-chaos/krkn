import logging
import random
import time

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.k8s.pods_monitor_pool import PodsMonitorPool
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value
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
        pool = PodsMonitorPool(lib_telemetry.get_lib_kubernetes())
        try:
            with open(scenario, "r") as f:
                cont_scenario_config = yaml.full_load(f)
                for kill_scenario in cont_scenario_config:
                    kill_scenario_config = kill_scenario["config"]
                    self.start_monitoring(
                        kill_scenario, pool
                    )
                    return_status = self.killing_pods(
                        kill_scenario_config, lib_telemetry.get_lib_kubernetes()
                    )
                    if return_status != 0: 
                        result = pool.cancel()
                    else:
                        result = pool.join()
                if result.error:
                    logging.error(
                        logging.error(
                            f"PodDisruptionScenariosPlugin pods failed to recovery: {result.error}"
                        )
                    )
                    return 1
                
                scenario_telemetry.affected_pods = result

        except (RuntimeError, Exception) as e:
            logging.error("PodDisruptionScenariosPlugin exiting due to Exception %s" % e)
            return 1
        else:
            return 0

    def get_scenario_types(self) -> list[str]:
        return ["pod_disruption_scenarios"]

    def start_monitoring(self, kill_scenario: dict, pool: PodsMonitorPool):
        
        recovery_time = kill_scenario["config"]["krkn_pod_recovery_time"]
        if (
            "namespace_pattern" in kill_scenario["config"]
            and "label_selector" in kill_scenario["config"]
        ):
            namespace_pattern = kill_scenario["config"]["namespace_pattern"]
            label_selector = kill_scenario["config"]["label_selector"]
            pool.select_and_monitor_by_namespace_pattern_and_label(
                namespace_pattern=namespace_pattern,
                label_selector=label_selector,
                max_timeout=recovery_time,
                field_selector="status.phase=Running"
            )

        elif (
            "namespace_pattern" in kill_scenario["config"]
            and "name_pattern" in kill_scenario["config"]
        ):
            namespace_pattern = kill_scenario["config"]["namespace_pattern"]
            name_pattern = kill_scenario["config"]["name_pattern"]
            pool.select_and_monitor_by_name_pattern_and_namespace_pattern(
                pod_name_pattern=name_pattern,
                namespace_pattern=namespace_pattern,
                max_timeout=recovery_time,
                field_selector="status.phase=Running"
            )
            
        else:
            raise Exception(
                f"impossible to determine monitor parameters, check {kill_scenario} configuration"
            )
        logging.info(
                f"waiting up to {recovery_time} seconds for pod recovery, "
                f"pod name pattern: {name_pattern} namespace pattern: {namespace_pattern}"
            )

    def get_pods(self, name_pattern, label_selector,namespace, kubecli: KrknKubernetes, field_selector: str =None): 
        if label_selector and name_pattern: 
            logging.error('Only, one of name pattern or label pattern can be specified')
        elif label_selector:
            pods = kubecli.select_pods_by_namespace_pattern_and_label(label_selector=label_selector,namespace_pattern=namespace, field_selector=field_selector)
        elif name_pattern:
            pods = kubecli.select_pods_by_name_pattern_and_namespace_pattern(pod_name_pattern=name_pattern, namespace_pattern=namespace, field_selector=field_selector)
        else: 
            logging.error('Name pattern or label pattern must be specified ')
        return pods
    
    def killing_pods(self, config: dict, kubecli: KrknKubernetes):
        # region Select target pods
            
        namespace = get_yaml_item_value(config,'namespace_pattern',"")
        if not namespace: 
            logging.error('Namespace pattern must be specified')

        name_pattern = get_yaml_item_value(config,'name_pattern', "")
        label_selector = get_yaml_item_value(config,'label_selector',"")

        kill = get_yaml_item_value(config,"kill", 1)
        timeout = get_yaml_item_value(config,"timeout", 120)
        duration = get_yaml_item_value(config, "duration", 10)

        pods = self.get_pods(name_pattern,label_selector,namespace, kubecli, field_selector="status.phase=Running")
        pods_count = len(pods)
        if len(pods) < kill:
            logging.error("Not enough pods match the criteria, expected {} but found only {} pods".format(
                    kill, len(pods)))
            return 1
        
        random.shuffle(pods)
        for i in range(kill):

            pod = pods[i]
            logging.info(pod)
            logging.info(f'Deleting pod {pod[0]}')
            kubecli.delete_pod(pod[0], pod[1])
        
        self.wait_for_pods(label_selector,name_pattern,namespace, pods_count, duration, timeout, kubecli)
        return 0

    def wait_for_pods(
        self, label_selector, pod_name, namespace, pod_count, duration, wait_timeout, kubecli: KrknKubernetes
    ):
        timeout = False
        start_time = datetime.now()

        while not timeout:
            pods = self.get_pods(name_pattern=pod_name, label_selector=label_selector,namespace=namespace, field_selector="status.phase=Running", kubecli=kubecli)
            logging.info('pod count ' + str(pod_count) + " " + str(len(pods)))
            if pod_count == len(pods):
                return
               
            time.sleep(duration)

            now_time = datetime.now()

            time_diff = now_time - start_time
            if time_diff.seconds > wait_timeout:
                logging.error("timeout while waiting for pods to come up")
                return 1
        return 0
