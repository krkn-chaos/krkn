import datetime
import time
import random
import logging
import paramiko
from krkn_lib.models.k8s import AffectedNode
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus
from krkn_lib.models.k8s import AffectedNode
from krkn_lib.models.k8s import KrknKubernetes


def get_node_by_name(node_name_list, kubecli: KrknKubernetes):
    killable_nodes = kubecli.list_killable_nodes()
    for node_name in node_name_list:
        if node_name not in killable_nodes:
            logging.info(
                f"Node with provided ${node_name} does not exist or the node might "
                "be in NotReady state."
            )
            return
    return node_name_list
        

# Pick a random node with specified label selector
def get_node(label_selector, instance_kill_count, kubecli: KrknKubernetes):

    label_selector_list  = label_selector.split(",")
    nodes = []
    for label_selector in label_selector_list: 
        nodes.extend(kubecli.list_killable_nodes(label_selector))
    if not nodes:
        raise Exception("Ready nodes with the provided label selector do not exist")
    logging.info("Ready nodes with the label selector %s: %s" % (label_selector_list, nodes))
    number_of_nodes = len(nodes)
    if instance_kill_count == number_of_nodes:
        return nodes
    nodes_to_return = []
    for i in range(instance_kill_count):
        node_to_add = nodes[random.randint(0, len(nodes) - 1)]
        nodes_to_return.append(node_to_add)
        nodes.remove(node_to_add)
    return nodes_to_return

# krkn_lib
# Wait until the node status becomes Ready
def wait_for_ready_status(node, timeout, kubecli: KrknKubernetes, affected_node: AffectedNode = None):
    affected_node =  kubecli.watch_node_status(node, "True", timeout, affected_node)
    return affected_node
   

# krkn_lib
# Wait until the node status becomes Not Ready
def wait_for_not_ready_status(node, timeout, kubecli: KrknKubernetes, affected_node: AffectedNode = None):
    affected_node = kubecli.watch_node_status(node, "False", timeout, affected_node)
    return affected_node
    

# krkn_lib
# Wait until the node status becomes Unknown
def wait_for_unknown_status(node, timeout, kubecli: KrknKubernetes, affected_node: AffectedNode = None):
    affected_node = kubecli.watch_node_status(node, "Unknown", timeout, affected_node)
    return affected_node


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
                node,
                username="root",
                key_filename=ssh_private_key,
                timeout=800,
                banner_timeout=400,
            )
            if connection is None:
                break
        except Exception as e:
            logging.error(
                "Failed to ssh to instance: %s within the timeout duration of %s: %s"
                % (node, timeout, e)
            )

    for service_name in service:
        logging.info("Checking status of Service: %s" % (service_name))
        stdin, stdout, stderr = ssh.exec_command(
            "systemctl status %s  | grep '^   Active' "
            "|  awk '{print $2}'" % (service_name)
        )
        service_status = stdout.readlines()[0]
        logging.info(
            "Status of service %s is %s \n" % (service_name, service_status.strip())
        )
        if service_status.strip() != "active":
            logging.error(
                "Service %s is in %s state" % (service_name, service_status.strip())
            )
    ssh.close()
