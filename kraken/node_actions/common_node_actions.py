import time
import random
import logging
import kraken.kubernetes.client as kubecli
import kraken.invoke.command as command


def run_and_select_node(scenario_yaml):

    for scenario in scenario_yaml['node_scenarios']:
        logging.info('\n\n\n1 scenario ' + str(scenario))

        node_names = kubecli.list_nodes(scenario['label_selector'])
        kill_count = 1
        if "instance_kill_count" in scenario.keys():
            kill_count = int(scenario['instance_kill_count'])
        for i in range(kill_count):
            # randomly pick node from node names
            node_name = random.choice(node_names)
            logging.info('node name ' + str(node_name))
            for action in scenario['actions']:
                if action == "stop_kubelet":
                    stop_kubelet(node_name)
                elif action == "node_crash":
                    crash_node(node_name)
                else:
                    logging.info("cloud type " + str(scenario['cloud_type']))
            timeout = int(scenario['timeout'])
            logging.info("Time out" + str(timeout))
            time.sleep(timeout)


# Stop the kubelet on one of the nodes
def stop_kubelet(node_name):
    stop_kubelet_response = command.invoke_debug_helper(node_name, "systemctl is-active kubelet")
    logging.info("Response from invoke " + str(stop_kubelet_response))


# Crash specific node
def crash_node(node_name):
    crash_node_response = command.invoke_debug_helper(node_name, "echo c > /proc/sysrq-trigger")
    logging.info("Crash node " + str(crash_node_response))
