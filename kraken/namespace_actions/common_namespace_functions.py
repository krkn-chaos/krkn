import time
import random
import logging
import kraken.invoke.command as runcommand
import kraken.kubernetes.client as kubecli
import kraken.cerberus.setup as cerberus
import yaml
import sys


def run(scenarios_list, config, wait_duration):
    for scenario_config in scenarios_list:
        with open(scenario_config, "r") as f:
            scenario_config = yaml.full_load(f)
            for scenario in scenario_config["scenarios"]:
                scenario_namespace = scenario.get("namespace", "^.*$")
                scenario_label = scenario.get("label_selector", None)
                run_count = scenario.get("runs", 1)
                namespace_action = scenario.get("action", "delete")
                run_sleep = scenario.get("sleep", 10)
                namespaces = kubecli.check_namespaces([scenario_namespace], scenario_label)
                for i in range(run_count):
                    if len(namespaces) == 0:
                        logging.error(
                            "Couldn't %s %s namespaces, not enough namespaces matching %s with label %s"
                            % (namespace_action, str(run_count), scenario_namespace, str(scenario_label))
                        )
                        sys.exit(1)
                    selected_namespace = namespaces[random.randint(0, len(namespaces) - 1)]
                    try:
                        runcommand.invoke("oc %s project %s" % (namespace_action, selected_namespace))
                        logging.info(namespace_action + " on namespace " + str(selected_namespace) + " was successful")
                    except Exception as e:
                        logging.info(
                            namespace_action + " on namespace " + str(selected_namespace) + " was unsuccessful"
                        )
                        logging.info("Namespace action error: " + str(e))
                    namespaces.remove(selected_namespace)
                    logging.info("Waiting %s seconds between namespace deletions" % str(run_sleep))
                    time.sleep(run_sleep)

                logging.info("Waiting for the specified duration: %s" % wait_duration)
                time.sleep(wait_duration)
                cerberus.get_status(config)
