import yaml
import logging
import sys
import time
from kraken.node_actions.aws_node_scenarios import aws_node_scenarios
from kraken.node_actions.general_cloud_node_scenarios import general_node_scenarios
from kraken.node_actions.az_node_scenarios import azure_node_scenarios
from kraken.node_actions.gcp_node_scenarios import gcp_node_scenarios
from kraken.node_actions.openstack_node_scenarios import openstack_node_scenarios
from kraken.node_actions.alibaba_node_scenarios import alibaba_node_scenarios
from kraken.node_actions.bm_node_scenarios import bm_node_scenarios
from kraken.node_actions.docker_node_scenarios import docker_node_scenarios
import kraken.node_actions.common_node_functions as common_node_functions
import kraken.cerberus.setup as cerberus
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.utils.functions import get_yaml_item_value

node_general = False


# Get the node scenarios object of specfied cloud type
# krkn_lib
def get_node_scenario_object(node_scenario, kubecli: KrknKubernetes):
    if "cloud_type" not in node_scenario.keys() or node_scenario["cloud_type"] == "generic":
        global node_general
        node_general = True
        return general_node_scenarios(kubecli)
    if node_scenario["cloud_type"] == "aws":
        return aws_node_scenarios(kubecli)
    elif node_scenario["cloud_type"] == "gcp":
        return gcp_node_scenarios(kubecli)
    elif node_scenario["cloud_type"] == "openstack":
        return openstack_node_scenarios(kubecli)
    elif node_scenario["cloud_type"] == "azure" or node_scenario["cloud_type"] == "az":
        return azure_node_scenarios(kubecli)
    elif node_scenario["cloud_type"] == "alibaba" or node_scenario["cloud_type"] == "alicloud":
        return alibaba_node_scenarios(kubecli)
    elif node_scenario["cloud_type"] == "bm":
        return bm_node_scenarios(
            node_scenario.get("bmc_info"), node_scenario.get("bmc_user", None), node_scenario.get("bmc_password", None),
            kubecli
        )
    elif node_scenario["cloud_type"] == "docker":
        return docker_node_scenarios(kubecli)
    else:
        logging.error(
            "Cloud type " + node_scenario["cloud_type"] + " is not currently supported; "
            "try using 'generic' if wanting to stop/start kubelet or fork bomb on any "
            "cluster"
        )
        sys.exit(1)


# Run defined scenarios
# krkn_lib
def run(scenarios_list, config, wait_duration, kubecli: KrknKubernetes, telemetry: KrknTelemetryKubernetes) -> (list[str], list[ScenarioTelemetry]):
    scenario_telemetries: list[ScenarioTelemetry] = []
    failed_scenarios = []
    for node_scenario_config in scenarios_list:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = node_scenario_config
        scenario_telemetry.startTimeStamp = time.time()
        telemetry.set_parameters_base64(scenario_telemetry, node_scenario_config)
        with open(node_scenario_config, "r") as f:
            node_scenario_config = yaml.full_load(f)
            for node_scenario in node_scenario_config["node_scenarios"]:
                node_scenario_object = get_node_scenario_object(node_scenario, kubecli)
                if node_scenario["actions"]:
                    for action in node_scenario["actions"]:
                        start_time = int(time.time())
                        try:
                            inject_node_scenario(action, node_scenario, node_scenario_object, kubecli)
                            logging.info("Waiting for the specified duration: %s" % (wait_duration))
                            time.sleep(wait_duration)
                            end_time = int(time.time())
                            cerberus.get_status(config, start_time, end_time)
                            logging.info("")
                        except (RuntimeError, Exception) as e:
                            scenario_telemetry.exitStatus = 1
                            failed_scenarios.append(node_scenario_config)
                            log_exception(node_scenario_config)
                        else:
                            scenario_telemetry.exitStatus = 0

                        scenario_telemetry.endTimeStamp = time.time()
                        scenario_telemetries.append(scenario_telemetry)

    return failed_scenarios, scenario_telemetries


# Inject the specified node scenario
def inject_node_scenario(action, node_scenario, node_scenario_object, kubecli: KrknKubernetes):
    generic_cloud_scenarios = ("stop_kubelet_scenario", "node_crash_scenario")
    # Get the node scenario configurations
    run_kill_count = get_yaml_item_value(node_scenario, "runs", 1)
    instance_kill_count = get_yaml_item_value(
        node_scenario, "instance_count", 1
    )
    node_name = get_yaml_item_value(node_scenario, "node_name", "")
    label_selector = get_yaml_item_value(node_scenario, "label_selector", "")
    timeout = get_yaml_item_value(node_scenario, "timeout", 120)
    service = get_yaml_item_value(node_scenario, "service", "")
    ssh_private_key = get_yaml_item_value(
        node_scenario, "ssh_private_key", "~/.ssh/id_rsa"
    )
    # Get the node to apply the scenario
    if node_name:
        node_name_list = node_name.split(",")
    else:
        node_name_list = [node_name]
    for single_node_name in node_name_list:
        nodes = common_node_functions.get_node(single_node_name, label_selector, instance_kill_count, kubecli)
        for single_node in nodes:
            if node_general and action not in generic_cloud_scenarios:
                logging.info("Scenario: " + action + " is not set up for generic cloud type, skipping action")
            else:
                if action == "node_start_scenario":
                    node_scenario_object.node_start_scenario(run_kill_count, single_node, timeout)
                elif action == "node_stop_scenario":
                    node_scenario_object.node_stop_scenario(run_kill_count, single_node, timeout)
                elif action == "node_stop_start_scenario":
                    node_scenario_object.node_stop_start_scenario(run_kill_count, single_node, timeout)
                elif action == "node_termination_scenario":
                    node_scenario_object.node_termination_scenario(run_kill_count, single_node, timeout)
                elif action == "node_reboot_scenario":
                    node_scenario_object.node_reboot_scenario(run_kill_count, single_node, timeout)
                elif action == "stop_start_kubelet_scenario":
                    node_scenario_object.stop_start_kubelet_scenario(run_kill_count, single_node, timeout)
                elif action == "stop_kubelet_scenario":
                    node_scenario_object.stop_kubelet_scenario(run_kill_count, single_node, timeout)
                elif action == "node_crash_scenario":
                    node_scenario_object.node_crash_scenario(run_kill_count, single_node, timeout)
                elif action == "stop_start_helper_node_scenario":
                    if node_scenario["cloud_type"] != "openstack":
                        logging.error(
                            "Scenario: " + action + " is not supported for "
                            "cloud type " + node_scenario["cloud_type"] + ", skipping action"
                        )
                    else:
                        if not node_scenario["helper_node_ip"]:
                            logging.error("Helper node IP address is not provided")
                            sys.exit(1)
                        node_scenario_object.helper_node_stop_start_scenario(
                            run_kill_count, node_scenario["helper_node_ip"], timeout
                        )
                        node_scenario_object.helper_node_service_status(
                            node_scenario["helper_node_ip"], service, ssh_private_key, timeout
                        )
                else:
                    logging.info("There is no node action that matches %s, skipping scenario" % action)
