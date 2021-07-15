import logging
import kraken.invoke.command as runcommand
import kraken.cerberus.setup as cerberus
import kraken.post_actions.actions as post_actions
import kraken.kubernetes.client as kubecli
import time
import yaml
import sys
import random


# Run pod based scenarios
def run(kubeconfig_path, scenarios_list, config, failed_post_scenarios, wait_duration):
    try:
        # Loop to run the scenarios starts here
        for pod_scenario in scenarios_list:
            if len(pod_scenario) > 1:
                pre_action_output = post_actions.run(kubeconfig_path, pod_scenario[1])
            else:
                pre_action_output = ""
            scenario_logs = runcommand.invoke(
                "powerfulseal autonomous --use-pod-delete-instead-"
                "of-ssh-kill --policy-file %s --kubeconfig %s "
                "--no-cloud --inventory-kubernetes --headless" % (pod_scenario[0], kubeconfig_path)
            )

            # Display pod scenario logs/actions
            print(scenario_logs)

            logging.info("Scenario: %s has been successfully injected!" % (pod_scenario[0]))
            logging.info("Waiting for the specified duration: %s" % (wait_duration))
            time.sleep(wait_duration)

            failed_post_scenarios = post_actions.check_recovery(
                kubeconfig_path, pod_scenario, failed_post_scenarios, pre_action_output
            )
            cerberus.publish_kraken_status(config, failed_post_scenarios)
    except Exception as e:
        logging.error("Failed to run scenario: %s. Encountered the following " "exception: %s" % (pod_scenario[0], e))
    return failed_post_scenarios


def container_run(kubeconfig_path, scenarios_list, config, failed_post_scenarios, wait_duration):
    for container_scenario_config in scenarios_list:
        with open(container_scenario_config[0], "r") as f:
            cont_scenario_config = yaml.full_load(f)
            for cont_scenario in cont_scenario_config["scenarios"]:
                if len(container_scenario_config) > 1:
                    pre_action_output = post_actions.run(kubeconfig_path, container_scenario_config[1])
                else:
                    pre_action_output = ""
                container_killing_in_pod(cont_scenario)
                logging.info("Waiting for the specified duration: %s" % (wait_duration))
                time.sleep(wait_duration)
                failed_post_scenarios = post_actions.check_recovery(
                    kubeconfig_path, container_scenario_config, failed_post_scenarios, pre_action_output
                )
                cerberus.publish_kraken_status(config, failed_post_scenarios)
                logging.info("")


def container_killing_in_pod(cont_scenario):
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

            container_names = runcommand.invoke(
                'oc get pods %s -n %s -o jsonpath="{.spec.containers[*].name}"' % (pod[0], pod[1])
            ).split(" ")
            container_pod_list.append([pod[0], pod[1], container_names])
        else:
            container_names = runcommand.invoke(
                'oc get pods %s -n %s -o jsonpath="{.spec.containers[*].name}"' % (pod, namespace)
            ).split(" ")
            container_pod_list.append([pod, namespace, container_names])

    killed_count = 0

    while killed_count < kill_count:
        if len(container_pod_list) == 0:
            logging.error("Trying to kill more containers than were found, try lowering kill count")
            logging.error("Scenario " + scenario_name + " failed")
            sys.exit(1)
        selected_container_pod = container_pod_list[random.randint(0, len(container_pod_list) - 1)]
        for c_name in selected_container_pod[2]:
            if container_name != "":
                if c_name == container_name:
                    retry_container_killing(kill_action, selected_container_pod[0], selected_container_pod[1], c_name)
                    break
            else:
                retry_container_killing(kill_action, selected_container_pod[0], selected_container_pod[1], c_name)
                break
        container_pod_list.remove(selected_container_pod)
        killed_count += 1
    logging.info("Scenario " + scenario_name + " successfully injected")


def retry_container_killing(kill_action, podname, namespace, container_name):
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
