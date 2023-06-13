import time
import random
import logging
import krkn_lib_kubernetes
import kraken.cerberus.setup as cerberus
import kraken.post_actions.actions as post_actions
import yaml
import sys


# krkn_lib_kubernetes
def run(
        scenarios_list,
        config,
        wait_duration,
        failed_post_scenarios,
        kubeconfig_path,
        kubecli: krkn_lib_kubernetes.KrknLibKubernetes
):

    for scenario_config in scenarios_list:
        if len(scenario_config) > 1:
            pre_action_output = post_actions.run(kubeconfig_path, scenario_config[1])
        else:
            pre_action_output = ""
        with open(scenario_config[0], "r") as f:
            scenario_config_yaml = yaml.full_load(f)
            for scenario in scenario_config_yaml["scenarios"]:
                scenario_namespace = scenario.get("namespace", "")
                scenario_label = scenario.get("label_selector", "")
                if scenario_namespace is not None and scenario_namespace.strip() != "":
                    if scenario_label is not None and scenario_label.strip() != "":
                        logging.error("You can only have namespace or label set in your namespace scenario")
                        logging.error(
                            "Current scenario config has namespace '%s' and label selector '%s'"
                            % (scenario_namespace, scenario_label)
                        )
                        logging.error(
                            "Please set either namespace to blank ('') or label_selector to blank ('') to continue"
                        )
                        sys.exit(1)
                delete_count = scenario.get("delete_count", 1)
                run_count = scenario.get("runs", 1)
                run_sleep = scenario.get("sleep", 10)
                wait_time = scenario.get("wait_time", 30)
                killed_namespaces = []
                start_time = int(time.time())
                for i in range(run_count):
                    namespaces = kubecli.check_namespaces([scenario_namespace], scenario_label)
                    for j in range(delete_count):
                        if len(namespaces) == 0:
                            logging.error(
                                "Couldn't delete %s namespaces, not enough namespaces matching %s with label %s"
                                % (str(run_count), scenario_namespace, str(scenario_label))
                            )
                            sys.exit(1)
                        selected_namespace = namespaces[random.randint(0, len(namespaces) - 1)]
                        killed_namespaces.append(selected_namespace)
                        try:
                            kubecli.delete_namespace(selected_namespace)
                            logging.info("Delete on namespace %s was successful" % str(selected_namespace))
                        except Exception as e:
                            logging.info("Delete on namespace %s was unsuccessful" % str(selected_namespace))
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
                            failed_post_scenarios = check_active_namespace(killed_namespaces, wait_time, kubecli)
                end_time = int(time.time())
                cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)

# krkn_lib_kubernetes
def check_active_namespace(killed_namespaces, wait_time, kubecli: krkn_lib_kubernetes.KrknLibKubernetes):
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
