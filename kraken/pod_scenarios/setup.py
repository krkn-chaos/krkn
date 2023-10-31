import logging
import time
import yaml
import sys
import random
import arcaflow_plugin_kill_pod
import kraken.cerberus.setup as cerberus
import kraken.post_actions.actions as post_actions
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from arcaflow_plugin_sdk import serialization
from krkn_lib.utils.functions import get_yaml_item_value, log_exception


# Run pod based scenarios
def run(kubeconfig_path, scenarios_list, config, failed_post_scenarios, wait_duration):
    # Loop to run the scenarios starts here
    for pod_scenario in scenarios_list:
        if len(pod_scenario) > 1:
            pre_action_output = post_actions.run(kubeconfig_path, pod_scenario[1])
        else:
            pre_action_output = ""
        try:
            # capture start time
            start_time = int(time.time())

            input = serialization.load_from_file(pod_scenario)

            s = arcaflow_plugin_kill_pod.get_schema()
            input_data: arcaflow_plugin_kill_pod.KillPodConfig = s.unserialize_input("pod", input)

            if kubeconfig_path is not None:
                input_data.kubeconfig_path = kubeconfig_path

            output_id, output_data = s.call_step("pod", input_data)

            if output_id == "error":
                data: arcaflow_plugin_kill_pod.PodErrorOutput = output_data
                logging.error("Failed to run pod scenario: {}".format(data.error))
            else:
                data: arcaflow_plugin_kill_pod.PodSuccessOutput = output_data
                for pod in data.pods:
                    print("Deleted pod {} in namespace {}\n".format(pod.pod_name, pod.pod_namespace))
        except Exception as e:
            logging.error(
                "Failed to run scenario: %s. Encountered the following " "exception: %s" % (pod_scenario[0], e)
            )
            sys.exit(1)

        logging.info("Scenario: %s has been successfully injected!" % (pod_scenario[0]))
        logging.info("Waiting for the specified duration: %s" % (wait_duration))
        time.sleep(wait_duration)

        try:
            failed_post_scenarios = post_actions.check_recovery(
                kubeconfig_path, pod_scenario, failed_post_scenarios, pre_action_output
            )
        except Exception as e:
            logging.error("Failed to run post action checks: %s" % e)
            sys.exit(1)

        # capture end time
        end_time = int(time.time())

        # publish cerberus status
        cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)
    return failed_post_scenarios


# krkn_lib
def container_run(kubeconfig_path,
                  scenarios_list,
                  config,
                  failed_post_scenarios,
                  wait_duration,
                  kubecli: KrknKubernetes,
                  telemetry: KrknTelemetryKubernetes) -> (list[str], list[ScenarioTelemetry]):

    failed_scenarios = []
    scenario_telemetries: list[ScenarioTelemetry] = []

    for container_scenario_config in scenarios_list:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = container_scenario_config[0]
        scenario_telemetry.startTimeStamp = time.time()
        telemetry.set_parameters_base64(scenario_telemetry, container_scenario_config[0])
        if len(container_scenario_config) > 1:
            pre_action_output = post_actions.run(kubeconfig_path, container_scenario_config[1])
        else:
            pre_action_output = ""
        with open(container_scenario_config[0], "r") as f:
            cont_scenario_config = yaml.full_load(f)
            for cont_scenario in cont_scenario_config["scenarios"]:
                # capture start time
                start_time = int(time.time())
                try:
                    killed_containers = container_killing_in_pod(cont_scenario, kubecli)
                    if len(container_scenario_config) > 1:
                        failed_post_scenarios = post_actions.check_recovery(
                            kubeconfig_path,
                            container_scenario_config,
                            failed_post_scenarios,
                            pre_action_output
                        )
                    else:
                        failed_post_scenarios = check_failed_containers(
                            killed_containers, cont_scenario.get("retry_wait", 120), kubecli
                        )

                    logging.info("Waiting for the specified duration: %s" % (wait_duration))
                    time.sleep(wait_duration)

                    # capture end time
                    end_time = int(time.time())

                    # publish cerberus status
                    cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)
                except (RuntimeError, Exception):
                    failed_scenarios.append(container_scenario_config[0])
                    log_exception(container_scenario_config[0])
                    scenario_telemetry.exitStatus = 1
                    # removed_exit
                    # sys.exit(1)
                else:
                    scenario_telemetry.exitStatus = 0
                scenario_telemetry.endTimeStamp = time.time()
                scenario_telemetries.append(scenario_telemetry)

    return failed_scenarios, scenario_telemetries


def container_killing_in_pod(cont_scenario, kubecli: KrknKubernetes):
    scenario_name = get_yaml_item_value(cont_scenario, "name", "")
    namespace = get_yaml_item_value(cont_scenario, "namespace", "*")
    label_selector = get_yaml_item_value(cont_scenario, "label_selector", None)
    pod_names = get_yaml_item_value(cont_scenario, "pod_names", [])
    container_name = get_yaml_item_value(cont_scenario, "container_name", "")
    kill_action = get_yaml_item_value(cont_scenario, "action", 1)
    kill_count = get_yaml_item_value(cont_scenario, "count", 1)
    if not isinstance(kill_action, int):
        logging.error("Please make sure the action parameter defined in the "
                      "config is an integer")
        raise RuntimeError()
    if (kill_action < 1) or (kill_action > 15):
        logging.error("Only 1-15 kill signals are supported.")
        raise RuntimeError()
    kill_action = "kill " + str(kill_action)
    if type(pod_names) != list:
        logging.error("Please make sure your pod_names are in a list format")
        # removed_exit
        # sys.exit(1)
        raise RuntimeError()
    if len(pod_names) == 0:
        if namespace == "*":
            # returns double array of pod name and namespace
            pods = kubecli.get_all_pods(label_selector)
        else:
            # Only returns pod names
            pods = kubecli.list_pods(namespace, label_selector)
    else:
        if namespace == "*":
            logging.error("You must specify the namespace to kill a container in a specific pod")
            logging.error("Scenario " + scenario_name + " failed")
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()
        pods = pod_names
    # get container and pod name
    container_pod_list = []
    for pod in pods:
        if type(pod) == list:
            pod_output = kubecli.get_pod_info(pod[0], pod[1])
            container_names = [container.name for container in pod_output.containers]

            container_pod_list.append([pod[0], pod[1], container_names])
        else:
            pod_output = kubecli.get_pod_info(pod, namespace)
            container_names = [container.name for container in pod_output.containers]
            container_pod_list.append([pod, namespace, container_names])

    killed_count = 0
    killed_container_list = []
    while killed_count < kill_count:
        if len(container_pod_list) == 0:
            logging.error("Trying to kill more containers than were found, try lowering kill count")
            logging.error("Scenario " + scenario_name + " failed")
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()
        selected_container_pod = container_pod_list[random.randint(0, len(container_pod_list) - 1)]
        for c_name in selected_container_pod[2]:
            if container_name != "":
                if c_name == container_name:
                    killed_container_list.append([selected_container_pod[0], selected_container_pod[1], c_name])
                    retry_container_killing(kill_action, selected_container_pod[0], selected_container_pod[1], c_name, kubecli)
                    break
            else:
                killed_container_list.append([selected_container_pod[0], selected_container_pod[1], c_name])
                retry_container_killing(kill_action, selected_container_pod[0], selected_container_pod[1], c_name, kubecli)
                break
        container_pod_list.remove(selected_container_pod)
        killed_count += 1
    logging.info("Scenario " + scenario_name + " successfully injected")
    return killed_container_list


def retry_container_killing(kill_action, podname, namespace, container_name, kubecli: KrknKubernetes):
    i = 0
    while i < 5:
        logging.info("Killing container %s in pod %s (ns %s)" % (str(container_name), str(podname), str(namespace)))
        response = kubecli.exec_cmd_in_pod(kill_action, podname, namespace, container_name)
        i += 1
        # Blank response means it is done
        if not response:
            break
        elif "unauthorized" in response.lower() or "authorization" in response.lower():
            time.sleep(2)
            continue
        else:
            logging.warning(response)
            continue


def check_failed_containers(killed_container_list, wait_time, kubecli: KrknKubernetes):

    container_ready = []
    timer = 0
    while timer <= wait_time:
        for killed_container in killed_container_list:
            # pod namespace contain name
            pod_output = kubecli.get_pod_info(killed_container[0], killed_container[1])

            for container in pod_output.containers:
                if container.name == killed_container[2]:
                    if container.ready:
                        container_ready.append(killed_container)
        if len(container_ready) != 0:
            for item in container_ready:
                killed_container_list = killed_container_list.remove(item)
        if killed_container_list is None or len(killed_container_list) == 0:
            return []
        timer += 5
        logging.info("Waiting 5 seconds for containers to become ready")
        time.sleep(5)
    return killed_container_list
