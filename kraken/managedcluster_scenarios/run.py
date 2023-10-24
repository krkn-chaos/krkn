import yaml
import logging
import time
from kraken.managedcluster_scenarios.managedcluster_scenarios import managedcluster_scenarios
import kraken.managedcluster_scenarios.common_managedcluster_functions as common_managedcluster_functions
import kraken.cerberus.setup as cerberus
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.utils.functions import get_yaml_item_value

# Get the managedcluster scenarios object of specfied cloud type
# krkn_lib
def get_managedcluster_scenario_object(managedcluster_scenario, kubecli: KrknKubernetes):
    return managedcluster_scenarios(kubecli)

# Run defined scenarios
# krkn_lib
def run(scenarios_list, config, wait_duration, kubecli: KrknKubernetes):
    for managedcluster_scenario_config in scenarios_list:
        with open(managedcluster_scenario_config, "r") as f:
            managedcluster_scenario_config = yaml.full_load(f)
            for managedcluster_scenario in managedcluster_scenario_config["managedcluster_scenarios"]:
                managedcluster_scenario_object = get_managedcluster_scenario_object(managedcluster_scenario, kubecli)
                if managedcluster_scenario["actions"]:
                    for action in managedcluster_scenario["actions"]:
                        start_time = int(time.time())
                        inject_managedcluster_scenario(action, managedcluster_scenario, managedcluster_scenario_object, kubecli)
                        logging.info("Waiting for the specified duration: %s" % (wait_duration))
                        time.sleep(wait_duration)
                        end_time = int(time.time())
                        cerberus.get_status(config, start_time, end_time)
                        logging.info("")


# Inject the specified managedcluster scenario
# krkn_lib
def inject_managedcluster_scenario(action, managedcluster_scenario, managedcluster_scenario_object, kubecli: KrknKubernetes):
    # Get the managedcluster scenario configurations
    run_kill_count = get_yaml_item_value(
        managedcluster_scenario, "runs", 1
    )
    instance_kill_count = get_yaml_item_value(
        managedcluster_scenario, "instance_count", 1
    )
    managedcluster_name = get_yaml_item_value(
        managedcluster_scenario, "managedcluster_name", ""
    )
    label_selector = get_yaml_item_value(
        managedcluster_scenario, "label_selector", ""
    )
    timeout = get_yaml_item_value(managedcluster_scenario, "timeout", 120)
    # Get the managedcluster to apply the scenario
    if managedcluster_name:
        managedcluster_name_list = managedcluster_name.split(",")
    else:
        managedcluster_name_list = [managedcluster_name]
    for single_managedcluster_name in managedcluster_name_list:
        managedclusters = common_managedcluster_functions.get_managedcluster(single_managedcluster_name, label_selector, instance_kill_count, kubecli)
        for single_managedcluster in managedclusters:
            if action == "managedcluster_start_scenario":
                managedcluster_scenario_object.managedcluster_start_scenario(run_kill_count, single_managedcluster, timeout)
            elif action == "managedcluster_stop_scenario":
                managedcluster_scenario_object.managedcluster_stop_scenario(run_kill_count, single_managedcluster, timeout)
            elif action == "managedcluster_stop_start_scenario":
                managedcluster_scenario_object.managedcluster_stop_start_scenario(run_kill_count, single_managedcluster, timeout)
            elif action == "managedcluster_termination_scenario":
                managedcluster_scenario_object.managedcluster_termination_scenario(run_kill_count, single_managedcluster, timeout)
            elif action == "managedcluster_reboot_scenario":
                managedcluster_scenario_object.managedcluster_reboot_scenario(run_kill_count, single_managedcluster, timeout)
            elif action == "stop_start_klusterlet_scenario":
                managedcluster_scenario_object.stop_start_klusterlet_scenario(run_kill_count, single_managedcluster, timeout)
            elif action == "start_klusterlet_scenario":
                managedcluster_scenario_object.stop_klusterlet_scenario(run_kill_count, single_managedcluster, timeout)    
            elif action == "stop_klusterlet_scenario":
                managedcluster_scenario_object.stop_klusterlet_scenario(run_kill_count, single_managedcluster, timeout)
            elif action == "managedcluster_crash_scenario":
                managedcluster_scenario_object.managedcluster_crash_scenario(run_kill_count, single_managedcluster, timeout)
            else:
                logging.info("There is no managedcluster action that matches %s, skipping scenario" % action)
