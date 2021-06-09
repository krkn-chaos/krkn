import time
import random
import logging
import paramiko
import yaml
import sys
import kraken.kubernetes.client as kubecli
import kraken.invoke.command as runcommand
import kraken.cerberus.setup as cerberus
import kraken.node_actions.common_node_functions as nodeaction
from kraken.node_actions.aws_node_scenarios import aws_node_scenarios
from kraken.node_actions.general_cloud_node_scenarios import general_node_scenarios
from kraken.node_actions.az_node_scenarios import azure_node_scenarios
from kraken.node_actions.gcp_node_scenarios import gcp_node_scenarios
from kraken.node_actions.openstack_node_scenarios import openstack_node_scenarios


node_general = False


# Pick a random node with specified label selector
def get_node(node_name, label_selector):
    if node_name in kubecli.list_killable_nodes():
        return node_name
    elif node_name:
        logging.info("Node with provided node_name does not exist or the node might " "be in NotReady state.")
    nodes = kubecli.list_killable_nodes(label_selector)
    if not nodes:
        raise Exception("Ready nodes with the provided label selector do not exist")
    logging.info("Ready nodes with the label selector %s: %s" % (label_selector, nodes))
    number_of_nodes = len(nodes)
    node = nodes[random.randint(0, number_of_nodes - 1)]
    return node


# Wait till node status becomes Ready
def wait_for_ready_status(node, timeout):
    runcommand.invoke("kubectl wait --for=condition=Ready " "node/" + node + " --timeout=" + str(timeout) + "s")


# Wait till node status becomes NotReady
def wait_for_unknown_status(node, timeout):
    for _ in range(timeout):
        if kubecli.get_node_status(node) == "Unknown":
            break
        time.sleep(1)
    if kubecli.get_node_status(node) != "Unknown":
        raise Exception("Node condition status isn't Unknown")


# Get the ip of the cluster node
def get_node_ip(node):
    return runcommand.invoke(
        "kubectl get node %s -o " "jsonpath='{.status.addresses[?(@.type==\"InternalIP\")].address}'" % (node)
    )


def check_service_status(node, service, ssh_private_key, timeout):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    i = 0
    sleeper = 1
    while i <= timeout:
        try:
            time.sleep(sleeper)
            i += sleeper
            logging.info("Trying to ssh to instance: %s" % (node))
            connection = ssh.connect(
                node, username="root", key_filename=ssh_private_key, timeout=800, banner_timeout=400
            )
            if connection is None:
                break
        except Exception:
            pass
    for service_name in service:
        logging.info("Checking status of Service: %s" % (service_name))
        stdin, stdout, stderr = ssh.exec_command(
            "systemctl status %s  | grep '^   Active' " "|  awk '{print $2}'" % (service_name)
        )
        service_status = stdout.readlines()[0]
        logging.info("Status of service %s is %s \n" % (service_name, service_status.strip()))
        if service_status.strip() != "active":
            logging.error("Service %s is in %s state" % (service_name, service_status.strip()))
    ssh.close()


# Run defined scenarios
def run(scenarios_list, config, wait_duration):
    for node_scenario_config in scenarios_list:
        with open(node_scenario_config, "r") as f:
            node_scenario_config = yaml.full_load(f)
            for node_scenario in node_scenario_config["node_scenarios"]:
                node_scenario_object = get_node_scenario_object(node_scenario)
                if node_scenario["actions"]:
                    for action in node_scenario["actions"]:
                        inject_node_scenario(action, node_scenario, node_scenario_object)
                        logging.info("Waiting for the specified duration: %s" % (wait_duration))
                        time.sleep(wait_duration)
                        cerberus.get_status(config)
                        logging.info("")


# Inject the specified node scenario
def inject_node_scenario(action, node_scenario, node_scenario_object):
    generic_cloud_scenarios = ("stop_kubelet_scenario", "node_crash_scenario")
    # Get the node scenario configurations
    instance_kill_count = node_scenario.get("instance_kill_count", 1)
    node_name = node_scenario.get("node_name", "")
    label_selector = node_scenario.get("label_selector", "")
    timeout = node_scenario.get("timeout", 120)
    service = node_scenario.get("service", "")
    ssh_private_key = node_scenario.get("ssh_private_key", "~/.ssh/id_rsa")
    # Get the node to apply the scenario
    node = nodeaction.get_node(node_name, label_selector)

    if node_general and action not in generic_cloud_scenarios:
        logging.info("Scenario: " + action + " is not set up for generic cloud type, skipping action")
    else:
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
        elif action == "stop_start_kubelet_scenario":
            node_scenario_object.stop_start_kubelet_scenario(instance_kill_count, node, timeout)
        elif action == "stop_kubelet_scenario":
            node_scenario_object.stop_kubelet_scenario(instance_kill_count, node, timeout)
        elif action == "node_crash_scenario":
            node_scenario_object.node_crash_scenario(instance_kill_count, node, timeout)
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
                    instance_kill_count, node_scenario["helper_node_ip"], timeout
                )
                node_scenario_object.helper_node_service_status(
                    node_scenario["helper_node_ip"], service, ssh_private_key, timeout
                )
        else:
            logging.info("There is no node action that matches %s, skipping scenario" % action)


# Get the node scenarios object of specfied cloud type
def get_node_scenario_object(node_scenario):
    if "cloud_type" not in node_scenario.keys() or node_scenario["cloud_type"] == "generic":
        global node_general
        node_general = True
        return general_node_scenarios()
    if node_scenario["cloud_type"] == "aws":
        return aws_node_scenarios()
    elif node_scenario["cloud_type"] == "gcp":
        return gcp_node_scenarios()
    elif node_scenario["cloud_type"] == "openstack":
        return openstack_node_scenarios()
    elif node_scenario["cloud_type"] == "azure" or node_scenario["cloud_type"] == "az":
        return azure_node_scenarios()
    else:
        logging.error(
            "Cloud type " + node_scenario["cloud_type"] + " is not currently supported; "
            "try using 'generic' if wanting to stop/start kubelet or fork bomb on any "
            "cluster"
        )
        sys.exit(1)
