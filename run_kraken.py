#!/usr/bin/env python

import sys
import os
import time
import optparse
import logging
import yaml
import requests
import kraken.kubernetes.client as kubecli
import kraken.invoke.command as runcommand
import pyfiglet
import kraken.node_actions.read_node_scenarios as read_node_scenarios
import kraken.node_actions.common_node_actions as node_actions


# Main function
def main(cfg):
    # Start kraken
    print(pyfiglet.figlet_format("kraken"))
    logging.info("Starting kraken")

    # Parse and read the config
    if os.path.isfile(cfg):
        with open(cfg, 'r') as f:
            config = yaml.full_load(f)
        kubeconfig_path = config["kraken"]["kubeconfig_path"]
        scenarios = config["kraken"]["scenarios"]
        node_scenario_files = config['kraken']['node_scenarios']
        cerberus_enabled = config["cerberus"]["cerberus_enabled"]
        wait_duration = config["tunings"]["wait_duration"]
        iterations = config["tunings"]["iterations"]
        daemon_mode = config["tunings"]['daemon_mode']

        # Initialize clients
        if not os.path.isfile(kubeconfig_path):
            kubeconfig_path = None
        logging.info("Initializing client to talk to the Kubernetes cluster")

        kubecli.initialize_clients(kubeconfig_path)

        # Cluster info
        logging.info("Fetching cluster info")
        cluster_version = runcommand.invoke("kubectl get clusterversion")
        cluster_info = runcommand.invoke("kubectl cluster-info | awk 'NR==1' | sed -r "
                                         "'s/\x1B\[([0-9]{1,3}(;[0-9]{1,2})?)?[mGK]//g'")  # noqa
        logging.info("\n%s%s" % (cluster_version, cluster_info))
        # might be good to open and read node_scenarios here and make into json
        # so that when continuous iterations don't have to keep open/reading
        node_scenarios = read_node_scenarios.read_file_return_json(node_scenario_files)

        # Initialize the start iteration to 0
        iteration = 0

        # Set the number of iterations to loop to infinity if daemon mode is
        # enabled or else set it to the provided iterations count in the config
        if daemon_mode:
            logging.info("Daemon mode enabled, kraken will cause chaos forever")
            logging.info("Ignoring the iterations set")
            iterations = float('inf')
        else:
            logging.info("Daemon mode not enabled, will run through %s iterations"
                         % str(iterations))
            iterations = int(iterations)

        # Loop to run the chaos starts here
        while (int(iteration) < iterations):
            if scenarios:
                # Inject chaos scenarios specified in the config
                try:
                    # Loop to run the scenarios starts here
                    for scenario in scenarios:
                        logging.info("Injecting scenario: %s" % (scenario))
                        runcommand.invoke("powerfulseal autonomous --use-pod-delete-instead-of-ssh-kill"
                                          " --policy-file %s --kubeconfig %s --no-cloud"
                                          " --inventory-kubernetes --headless"
                                          % (scenario, kubeconfig_path))
                        logging.info("Scenario: %s has been successfully injected!" % (scenario))

                        if cerberus_enabled:
                            cerberus_url = config["cerberus"]["cerberus_url"]
                            if not cerberus_url:
                                logging.error("url where Cerberus publishes True/False signal "
                                              "is not provided.")
                                sys.exit(1)
                            cerberus_status = requests.get(cerberus_url).content
                            cerberus_status = True if cerberus_status == b'True' else False
                            if not cerberus_status:
                                logging.error("Received a no-go signal from Cerberus, looks like the"
                                              " cluster is unhealthy. Please check the Cerberus report"
                                              " for more details. Test failed.")
                                sys.exit(1)
                            else:
                                logging.info("Received a go signal from Ceberus, the cluster is "
                                             "healthy. Test passed.")
                        logging.info("Waiting for the specified duration: %s" % (wait_duration))
                        time.sleep(wait_duration)
                except Exception as e:
                    logging.error("Failed to run scenario: %s. Encountered the following exception: %s"
                                  % (scenario, e))
            elif node_scenarios:
                # Inject chaos scenarios specified in the config
                try:
                    for node_scenario in node_scenarios:
                        # put inner loop from node actions here?
                        logging.info("Injecting scenario: %s" % str(node_scenario))
                        node_actions.run_and_select_node(node_scenario)
                        logging.info("Scenario: %s has been successfully injected!" % (node_scenario))
                        logging.info("Waiting for the specified duration: %s" % (wait_duration))
                        time.sleep(wait_duration)
                        if cerberus_enabled:
                            cerberus_url = config["cerberus"]["cerberus_url"]
                            if not cerberus_url:
                                logging.error("url where Cerberus publishes True/False signal "
                                              "is not provided.")
                                sys.exit(1)
                            cerberus_status = requests.get(cerberus_url).content
                            cerberus_status = True if cerberus_status == b'True' else False
                            if not cerberus_status:
                                logging.error("Received a no-go signal from Cerberus, looks like the "
                                              "cluster is unhealthy. Please check the Cerberus report "
                                              "for more details. Test failed.")
                                sys.exit(1)
                            else:
                                logging.info("Received a go signal from Ceberus, the cluster is healthy. "
                                             "Test passed.")
                except Exception as e:
                    logging.error("Failed to run scenario: %s. Encountered the following exception: %s"
                                  % (node_scenario, e))
            iteration += 1
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
