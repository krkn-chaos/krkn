import logging
import os.path
import time
from typing import List

import krkn_lib.utils
import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes

from kraken import utils


def run(scenarios_list: list[str], krkn_kubernetes: KrknKubernetes, telemetry: KrknTelemetryKubernetes) -> (list[str], list[ScenarioTelemetry]):
    scenario_telemetries: list[ScenarioTelemetry] = []
    failed_post_scenarios = []
    for scenario in scenarios_list:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = scenario
        scenario_telemetry.start_timestamp = time.time()
        parsed_scenario_config = telemetry.set_parameters_base64(scenario_telemetry, scenario)

        try:
            pod_names = []
            config = parse_config(scenario)
            if config["target-service-label"]:
                target_services = krkn_kubernetes.select_service_by_label(config["namespace"], config["target-service-label"])
            else:
                target_services = [config["target-service"]]

            for target in target_services:
                if not krkn_kubernetes.service_exists(target, config["namespace"]):
                    raise Exception(f"{target} service not found")
                for i in range(config["number-of-pods"]):
                    pod_name = "syn-flood-" + krkn_lib.utils.get_random_string(10)
                    krkn_kubernetes.deploy_syn_flood(pod_name,
                                                     config["namespace"],
                                                     config["image"],
                                                     target,
                                                     config["target-port"],
                                                     config["packet-size"],
                                                     config["window-size"],
                                                     config["duration"],
                                                     config["attacker-nodes"]
                                                     )
                    pod_names.append(pod_name)

            logging.info("waiting all the attackers to finish:")
            did_finish = False
            finished_pods = []
            while not did_finish:
                for pod_name in pod_names:
                    if not krkn_kubernetes.is_pod_running(pod_name, config["namespace"]):
                        finished_pods.append(pod_name)
                    if set(pod_names) == set(finished_pods):
                        did_finish = True
                time.sleep(1)

        except Exception as e:
            logging.error(f"Failed to run syn flood scenario {scenario}: {e}")
            failed_post_scenarios.append(scenario)
            scenario_telemetry.exit_status = 1
        else:
            scenario_telemetry.exit_status = 0
        scenario_telemetry.end_timestamp = time.time()
        utils.populate_cluster_events(scenario_telemetry,
                                      parsed_scenario_config,
                                      telemetry.kubecli,
                                      int(scenario_telemetry.start_timestamp),
                                      int(scenario_telemetry.end_timestamp))
        scenario_telemetries.append(scenario_telemetry)
    return failed_post_scenarios, scenario_telemetries

def parse_config(scenario_file: str) -> dict[str,any]:
    if not os.path.exists(scenario_file):
        raise Exception(f"failed to load scenario file {scenario_file}")

    try:
        with open(scenario_file) as stream:
            config = yaml.safe_load(stream)
    except Exception:
        raise Exception(f"{scenario_file} is not a valid yaml file")

    missing = []
    if not check_key_value(config ,"packet-size"):
        missing.append("packet-size")
    if not check_key_value(config,"window-size"):
        missing.append("window-size")
    if not check_key_value(config, "duration"):
        missing.append("duration")
    if not check_key_value(config, "namespace"):
        missing.append("namespace")
    if not check_key_value(config, "number-of-pods"):
        missing.append("number-of-pods")
    if not check_key_value(config, "target-port"):
        missing.append("target-port")
    if not check_key_value(config, "image"):
        missing.append("image")
    if "target-service" not in config.keys():
        missing.append("target-service")
    if "target-service-label" not in config.keys():
        missing.append("target-service-label")




    if len(missing) > 0:
        raise Exception(f"{(',').join(missing)} parameter(s) are missing")

    if not config["target-service"] and not config["target-service-label"]:
        raise Exception("you have either to set a target service or a label")
    if config["target-service"] and config["target-service-label"]:
        raise Exception("you cannot select both target-service and target-service-label")

    if 'attacker-nodes' and not is_node_affinity_correct(config['attacker-nodes']):
        raise Exception("attacker-nodes format is not correct")
    return config

def check_key_value(dictionary, key):
    if key in dictionary:
        value = dictionary[key]
        if value is not None and value != '':
            return True
    return False

def is_node_affinity_correct(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    for key in obj.keys():
        if not isinstance(key, str):
            return False
        if not isinstance(obj[key], list):
            return False
    return True




