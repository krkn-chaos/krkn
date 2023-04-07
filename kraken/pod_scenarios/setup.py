import logging

from arcaflow_plugin_sdk import serialization
import arcaflow_plugin_kill_pod

import kraken.cerberus.setup as cerberus
import kraken.post_actions.actions as post_actions
import krkn_lib_kubernetes_draft
import time
import yaml
import sys
import random


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

# krkn_lib_kubernetes
def container_run(kubeconfig_path, scenarios_list, config, failed_post_scenarios, wait_duration, kubecli: krkn_lib_kubernetes_draft.KrknLibKubernetes):
    for container_scenario_config in scenarios_list:
        if len(container_scenario_config) > 1:
            pre_action_output = post_actions.run(kubeconfig_path, container_scenario_config[1])
        else:
            pre_action_output = ""
        with open(container_scenario_config[0], "r") as f:
            cont_scenario_config = yaml.full_load(f)
            for cont_scenario in cont_scenario_config["scenarios"]:
                # capture start time
                start_time = int(time.time())
                killed_containers = container_killing_in_pod(cont_scenario, kubecli)

                if len(container_scenario_config) > 1:
                    try:
                        failed_post_scenarios = post_actions.check_recovery(
                            kubeconfig_path, container_scenario_config, failed_post_scenarios, pre_action_output
                        )
                    except Exception as e:
                        logging.error("Failed to run post action checks: %s" % e)
                        sys.exit(1)
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
                logging.info("")


def container_killing_in_pod(cont_scenario, kubecli: krkn_lib_kubernetes_draft.KrknLibKubernetes):
    scenario_name = cont_scenario.get("name", "")
    namespace = cont_scenario.get("namespace", "*")
    label_selector = cont_scenario.get("label_selector", None)
    pod_names = cont_scenario.get("pod_names", [])
    container_name = cont_scenario.get("container_name", "")
    kill_action = cont_scenario.get("action", "kill 1")
    kill_count = cont_scenario.get("count", 1)
    if type(pod_names) != list:
        logging.error("Please make sure your pod_names are in a list format")
        sys.exit(1)
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
            sys.exit(1)
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
            sys.exit(1)
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


def retry_container_killing(kill_action, podname, namespace, container_name, kubecli: krkn_lib_kubernetes_draft.KrknLibKubernetes):
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
            continue


def check_failed_containers(killed_container_list, wait_time, kubecli: krkn_lib_kubernetes_draft.KrknLibKubernetes):

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
