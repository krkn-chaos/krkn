#!/usr/bin/env python

import os
import sys
import time
import yaml
import logging
import optparse
import requests
import pyfiglet
import kraken.kubernetes.client as kubecli
import kraken.invoke.command as runcommand
import kraken.node_actions.common_node_functions as nodeaction
from kraken.node_actions.aws_node_scenarios import aws_node_scenarios


# Get the node scenarios object of specfied cloud type
def get_node_scenario_object(node_scenario):
    if node_scenario['cloud_type'] == 'aws':
        return aws_node_scenarios()


# Inject the specified node scenario
def inject_node_scenario(action, node_scenario, node_scenario_object):
    # Get the node scenario configurations
    instance_kill_count = node_scenario.get("instance_kill_count", 1)
    node_name = node_scenario.get("node_name", "")
    label_selector = node_scenario.get("label_selector", "")
    timeout = node_scenario.get("timeout", 120)

    # Get the node to apply the scenario
    node = nodeaction.get_node(node_name, label_selector)

    if action == "node_start_scenario":
        node_scenario_object.node_start_scenario(instance_kill_count, node, timeout)
    elif action == "node_stop_scenario":
        node_scenario_object.node_stop_scenario(instance_kill_count, node, timeout)
    elif action == "node_stop_start_scenario":
        node_scenario_object.node_stop_start_scenario(instance_kill_count, node, timeout)
    elif action == "node_termination_scenario":
        node_scenario_object.node_termination_scenario(instance_kill_count, node, timeout)
    elif action == "node_reboot_scenario":
        node_scenario_object.node_reboot_scenario(instance_kill_count, node, timeout)
    elif action == "stop_kubelet_scenario":
        node_scenario_object.stop_kubelet_scenario(instance_kill_count, node, timeout)
    elif action == "stop_start_kubelet_scenario":
        node_scenario_object.stop_start_kubelet_scenario(instance_kill_count, node, timeout)
    elif action == "node_crash_scenario":
        node_scenario_object.node_crash_scenario(instance_kill_count, node, timeout)


# Get cerberus status
def cerberus_integration(config):
    cerberus_status = True
    if config["cerberus"]["cerberus_enabled"]:
        cerberus_url = config["cerberus"]["cerberus_url"]
        if not cerberus_url:
            logging.error("url where Cerberus publishes True/False signal is not provided.")
            sys.exit(1)
        cerberus_status = requests.get(cerberus_url).content
        cerberus_status = True if cerberus_status == b'True' else False
        if not cerberus_status:
            logging.error("Received a no-go signal from Cerberus, looks like "
                          "the cluster is unhealthy. Please check the Cerberus "
                          "report for more details. Test failed.")
            sys.exit(1)
        else:
            logging.info("Received a go signal from Ceberus, the cluster is healthy. "
                         "Test passed.")
    return cerberus_status


# Function to publish kraken status to cerberus
def publish_kraken_status(config, failed_post_scenarios):
    cerberus_status = cerberus_integration(config)
    if not cerberus_status:
        if failed_post_scenarios:
            if config['kraken']['exit_on_failure']:
                logging.info("Cerberus status is not healthy and post action scenarios "
                             "are still failing, exiting kraken run")
                sys.exit(1)
            else:
                logging.info("Cerberus status is not healthy and post action scenarios "
                             "are still failing")
    else:

        if failed_post_scenarios:
            if config['kraken']['exit_on_failure']:
                logging.info("Cerberus status is healthy but post action scenarios "
                             "are still failing, exiting kraken run")
                sys.exit(1)
            else:
                logging.info("Cerberus status is healthy but post action scenarios "
                             "are still failing")


def run_post_action(kubeconfig_path, scenario, pre_action_output=""):

    if scenario.endswith(".yaml") or scenario.endswith(".yml"):
        action_output = runcommand.invoke("powerfulseal autonomous "
                                          "--use-pod-delete-instead-of-ssh-kill"
                                          " --policy-file %s --kubeconfig %s --no-cloud"
                                          " --inventory-kubernetes --headless"
                                          % (scenario, kubeconfig_path))
        # read output to make sure no error
        if "ERROR" in action_output:
            action_output.split("ERROR")[1].split('\n')[0]
            if not pre_action_output:
                logging.info("Powerful seal pre action check failed for " + str(scenario))
            return False
        else:
            logging.info(scenario + " post action checks passed")

    elif scenario.endswith(".py"):
        action_output = runcommand.invoke("python3 " + scenario).strip()
        if pre_action_output:
            if pre_action_output == action_output:
                logging.info(scenario + " post action checks passed")
            else:
                logging.info(scenario + ' post action response did not match pre check output')
                return False
    elif scenario != "":
        # invoke custom bash script
        action_output = runcommand.invoke(scenario).strip()
        if pre_action_output:
            if pre_action_output == action_output:
                logging.info(scenario + " post action checks passed")
            else:
                logging.info(scenario + ' post action response did not match pre check output')
                return False

    return action_output


# Perform the post scenario actions to see if components recovered
def post_actions(kubeconfig_path, scenario, failed_post_scenarios, pre_action_output):

    for failed_scenario in failed_post_scenarios:
        post_action_output = run_post_action(kubeconfig_path,
                                             failed_scenario[0], failed_scenario[1])
        if post_action_output is not False:
            failed_post_scenarios.remove(failed_scenario)
        else:
            logging.info('Post action scenario ' + str(failed_scenario) + "is still failing")

    # check post actions
    if len(scenario) > 1:
        post_action_output = run_post_action(kubeconfig_path, scenario[1], pre_action_output)
        if post_action_output is False:
            failed_post_scenarios.append([scenario[1], pre_action_output])

    return failed_post_scenarios


# Main function
def main(cfg):
    # Start kraken
    print(pyfiglet.figlet_format("kraken"))
    logging.info("Starting kraken")

    # Parse and read the config
    if os.path.isfile(cfg):
        with open(cfg, 'r') as f:
            config = yaml.full_load(f)
        kubeconfig_path = config["kraken"].get("kubeconfig_path", "")
        scenarios = config["kraken"].get("scenarios", [])
        node_scenarios = config["kraken"].get("node_scenarios", [])
        wait_duration = config["tunings"].get("wait_duration", 60)
        iterations = config["tunings"].get("iterations", 1)
        daemon_mode = config["tunings"].get("daemon_mode", False)

        # Initialize clients
        if not os.path.isfile(kubeconfig_path):
            kubeconfig_path = None
        logging.info("Initializing client to talk to the Kubernetes cluster")
        kubecli.initialize_clients(kubeconfig_path)

        # find node kraken might be running on
        kubecli.find_kraken_node()

        # Cluster info
        logging.info("Fetching cluster info")
        cluster_version = runcommand.invoke("kubectl get clusterversion")
        cluster_info = runcommand.invoke("kubectl cluster-info | awk 'NR==1' | sed -r "
                                         "'s/\x1B\[([0-9]{1,3}(;[0-9]{1,2})?)?[mGK]//g'")  # noqa
        logging.info("\n%s%s" % (cluster_version, cluster_info))

        # Initialize the start iteration to 0
        iteration = 0

        # Set the number of iterations to loop to infinity if daemon mode is
        # enabled or else set it to the provided iterations count in the config
        if daemon_mode:
            logging.info("Daemon mode enabled, kraken will cause chaos forever\n")
            logging.info("Ignoring the iterations set")
            iterations = float('inf')
        else:
            logging.info("Daemon mode not enabled, will run through %s iterations\n"
                         % str(iterations))
            iterations = int(iterations)

        failed_post_scenarios = []
        # Loop to run the chaos starts here
        while (int(iteration) < iterations):
            # Inject chaos scenarios specified in the config
            logging.info("Executing scenarios for iteration " + str(iteration))
            if scenarios:
                try:
                    # Loop to run the scenarios starts here
                    for scenario in scenarios:

                        if len(scenario) > 1:
                            pre_action_output = run_post_action(kubeconfig_path, scenario[1])
                        else:
                            pre_action_output = ''
                        runcommand.invoke("powerfulseal autonomous --use-pod-delete-instead-of-ssh-kill"  # noqa
                                          " --policy-file %s --kubeconfig %s --no-cloud"
                                          " --inventory-kubernetes --headless"
                                          % (scenario[0], kubeconfig_path))

                        logging.info("Scenario: %s has been successfully injected!" % (scenario[0]))
                        logging.info("Waiting for the specified duration: %s" % (wait_duration))
                        time.sleep(wait_duration)

                        failed_post_scenarios = post_actions(kubeconfig_path, scenario,
                                                             failed_post_scenarios,
                                                             pre_action_output)
                        publish_kraken_status(config, failed_post_scenarios)
                except Exception as e:
                    logging.error("Failed to run scenario: %s. Encountered the following "
                                  "exception: %s" % (scenario[0], e))

            # Inject node chaos scenarios specified in the config
            if node_scenarios:
                for node_scenario_config in node_scenarios:
                    with open(node_scenario_config, 'r') as f:
                        node_scenario_config = yaml.full_load(f)
                        for node_scenario in node_scenario_config['node_scenarios']:
                            node_scenario_object = get_node_scenario_object(node_scenario)
                            if node_scenario['actions']:
                                for action in node_scenario['actions']:
                                    inject_node_scenario(action, node_scenario,
                                                         node_scenario_object)
                                    logging.info("Waiting for the specified duration: %s"
                                                 % (wait_duration))
                                    time.sleep(wait_duration)
                                    cerberus_integration(config)
                                    logging.info("")

            iteration += 1
            logging.info("")
        if failed_post_scenarios:
            logging.error("Post scenarios are still failing at the end of all iterations")
            sys.exit(1)
    else:
        logging.error("Cannot find a config at %s, please check" % (cfg))
        sys.exit(1)


if __name__ == "__main__":
    # Initialize the parser to read the config
    parser = optparse.OptionParser()
    parser.add_option(
        "-c", "--config",
        dest="cfg",
        help="config location",
        default="config/config.yaml",
    )
    (options, args) = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler("kraken.report", mode='w'),
            logging.StreamHandler()
        ]
    )
    if (options.cfg is None):
        logging.error("Please check if you have passed the config")
        sys.exit(1)
    else:
        main(options.cfg)
