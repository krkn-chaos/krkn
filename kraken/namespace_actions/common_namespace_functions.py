import time
import random
import logging
import kraken.invoke.command as runcommand
import kraken.kubernetes.client as kubecli
import kraken.cerberus.setup as cerberus
import kraken.post_actions.actions as post_actions
import yaml
import sys


def run(scenarios_list, config, wait_duration, failed_post_scenarios, kubeconfig_path):
    for scenario_config in scenarios_list:
        if len(scenario_config) > 1:
            pre_action_output = post_actions.run(kubeconfig_path, scenario_config[1])
        else:
            pre_action_output = ""
        with open(scenario_config[0], "r") as f:
            scenario_config_yaml = yaml.full_load(f)
            for scenario in scenario_config_yaml["scenarios"]:
                scenario_namespace = scenario.get("namespace", "^.*$")
                scenario_label = scenario.get("label_selector", None)
                run_count = scenario.get("runs", 1)
                namespace_action = scenario.get("action", "delete")
                run_sleep = scenario.get("sleep", 10)
                wait_time = scenario.get("wait_time", 30)
                killed_namespaces = []
                namespaces = kubecli.check_namespaces([scenario_namespace], scenario_label)
                start_time = int(time.time())
                for i in range(run_count):
                    if len(namespaces) == 0:
                        logging.error(
                            "Couldn't %s %s namespaces, not enough namespaces matching %s with label %s"
                            % (namespace_action, str(run_count), scenario_namespace, str(scenario_label))
                        )
                        sys.exit(1)
                    selected_namespace = namespaces[random.randint(0, len(namespaces) - 1)]
                    killed_namespaces.append(selected_namespace)
                    try:
                        runcommand.invoke("oc %s project %s" % (namespace_action, selected_namespace))
                        logging.info(namespace_action + " on namespace " + str(selected_namespace) + " was successful")
                    except Exception as e:
                        logging.info(
                            namespace_action + " on namespace " + str(selected_namespace) + " was unsuccessful"
                        )
                        logging.info("Namespace action error: " + str(e))
                        sys.exit(1)
                    namespaces.remove(selected_namespace)
                    logging.info("Waiting %s seconds between namespace deletions" % str(run_sleep))
                    time.sleep(run_sleep)

                logging.info("Waiting for the specified duration: %s" % wait_duration)
                time.sleep(wait_duration)
                if len(scenario_config) > 1:
                    try:
                        failed_post_scenarios = post_actions.check_recovery(
                            kubeconfig_path, scenario_config, failed_post_scenarios, pre_action_output
                        )
                    except Exception as e:
                        logging.error("Failed to run post action checks: %s" % e)
                        sys.exit(1)
                else:
                    failed_post_scenarios = check_active_namespace(killed_namespaces, wait_time)
                end_time = int(time.time())
                cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)


def check_active_namespace(killed_namespaces, wait_time):
    active_namespace = []
    timer = 0
    while timer < wait_time and killed_namespaces:
        for namespace_name in killed_namespaces:
            if namespace_name in kubecli.list_namespaces():
                response = kubecli.get_namespace_status(namespace_name).strip()
                if response != "Active":
                    continue
                else:
                    active_namespace.append(namespace_name)
        killed_namespaces = set(killed_namespaces) - set(active_namespace)
        if len(killed_namespaces) == 0:
            return []

        timer += 5
        time.sleep(5)
        logging.info("Waiting 5 seconds for namespaces to become active")

    logging.error("Namespaces are still not active after waiting " + str(wait_time) + "seconds")
    logging.error("Non active namespaces " + str(killed_namespaces))
    return killed_namespaces
