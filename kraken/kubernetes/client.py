from kubernetes import client, config
from kubernetes.stream import stream
from kubernetes.client.rest import ApiException
import logging
import kraken.invoke.command as runcommand
import sys
import re

kraken_node_name = ""


# Load kubeconfig and initialize kubernetes python client
def initialize_clients(kubeconfig_path):
    global cli
    try:
        config.load_kube_config(kubeconfig_path)
        cli = client.CoreV1Api()
    except ApiException as e:
        logging.error("Failed to initialize kubernetes client: %s\n" % e)
        sys.exit(1)


# List all namespaces
def list_namespaces(label_selector=None):
    namespaces = []
    try:
        if label_selector:
            ret = cli.list_namespace(pretty=True, label_selector=label_selector)
        else:
            ret = cli.list_namespace(pretty=True)
    except ApiException as e:
        logging.error("Exception when calling CoreV1Api->list_namespaced_pod: %s\n" % e)
    for namespace in ret.items:
        namespaces.append(namespace.metadata.name)
    return namespaces


# Check if all the watch_namespaces are valid
def check_namespaces(namespaces, label_selectors=None):
    try:
        valid_namespaces = list_namespaces(label_selectors)
        regex_namespaces = set(namespaces) - set(valid_namespaces)
        final_namespaces = set(namespaces) - set(regex_namespaces)
        valid_regex = set()
        if regex_namespaces:
            for namespace in valid_namespaces:
                for regex_namespace in regex_namespaces:
                    if re.search(regex_namespace, namespace):
                        final_namespaces.add(namespace)
                        valid_regex.add(regex_namespace)
                        break
        invalid_namespaces = regex_namespaces - valid_regex
        if invalid_namespaces:
            raise Exception("There exists no namespaces matching: %s" % (invalid_namespaces))
        return list(final_namespaces)
    except Exception as e:
        logging.info("%s" % (e))
        sys.exit(1)


# List nodes in the cluster
def list_nodes(label_selector=None):
    nodes = []
    try:
        if label_selector:
            ret = cli.list_node(pretty=True, label_selector=label_selector)
        else:
            ret = cli.list_node(pretty=True)
    except ApiException as e:
        logging.error("Exception when calling CoreV1Api->list_node: %s\n" % e)
    for node in ret.items:
        nodes.append(node.metadata.name)
    return nodes


# List nodes in the cluster that can be killed
def list_killable_nodes(label_selector=None):
    nodes = []
    try:
        if label_selector:
            ret = cli.list_node(pretty=True, label_selector=label_selector)
        else:
            ret = cli.list_node(pretty=True)
    except ApiException as e:
        logging.error("Exception when calling CoreV1Api->list_node: %s\n" % e)
    for node in ret.items:
        if kraken_node_name != node.metadata.name:
            for cond in node.status.conditions:
                if str(cond.type) == "Ready" and str(cond.status) == "True":
                    nodes.append(node.metadata.name)
    return nodes


# List pods in the given namespace
def list_pods(namespace, label_selector=None):
    pods = []
    try:
        if label_selector:
            ret = cli.list_namespaced_pod(namespace, pretty=True, label_selector=label_selector)
        else:
            ret = cli.list_namespaced_pod(namespace, pretty=True)
    except ApiException as e:
        logging.error(
            "Exception when calling \
                       CoreV1Api->list_namespaced_pod: %s\n"
            % e
        )
    for pod in ret.items:
        pods.append(pod.metadata.name)
    return pods


def get_all_pods(label_selector=None):
    pods = []
    if label_selector:
        ret = cli.list_pod_for_all_namespaces(pretty=True, label_selector=label_selector)
    else:
        ret = cli.list_pod_for_all_namespaces(pretty=True)
    for pod in ret.items:
        pods.append([pod.metadata.name, pod.metadata.namespace])
    return pods


# Execute command in pod
def exec_cmd_in_pod(command, pod_name, namespace, container=None):

    exec_command = ["bash", "-c", command]
    try:
        if container:
            ret = stream(
                cli.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                container=container,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            )
        else:
            ret = stream(
                cli.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            )
    except Exception:
        return False
    return ret


# Obtain node status
def get_node_status(node):
    try:
        node_info = cli.read_node_status(node, pretty=True)
    except ApiException as e:
        logging.error(
            "Exception when calling \
                       CoreV1Api->read_node_status: %s\n"
            % e
        )
    for condition in node_info.status.conditions:
        if condition.type == "Ready":
            return condition.status


# Monitor the status of the cluster nodes and set the status to true or false
def monitor_nodes():
    nodes = list_nodes()
    notready_nodes = []
    node_kerneldeadlock_status = "False"
    for node in nodes:
        try:
            node_info = cli.read_node_status(node, pretty=True)
        except ApiException as e:
            logging.error(
                "Exception when calling \
                           CoreV1Api->read_node_status: %s\n"
                % e
            )
        for condition in node_info.status.conditions:
            if condition.type == "KernelDeadlock":
                node_kerneldeadlock_status = condition.status
            elif condition.type == "Ready":
                node_ready_status = condition.status
            else:
                continue
        if node_kerneldeadlock_status != "False" or node_ready_status != "True":  # noqa  # noqa
            notready_nodes.append(node)
    if len(notready_nodes) != 0:
        status = False
    else:
        status = True
    return status, notready_nodes


# Monitor the status of the pods in the specified namespace
# and set the status to true or false
def monitor_namespace(namespace):
    pods = list_pods(namespace)
    notready_pods = []
    for pod in pods:
        try:
            pod_info = cli.read_namespaced_pod_status(pod, namespace, pretty=True)
        except ApiException as e:
            logging.error(
                "Exception when calling \
                           CoreV1Api->read_namespaced_pod_status: %s\n"
                % e
            )
        pod_status = pod_info.status.phase
        if pod_status != "Running" and pod_status != "Completed" and pod_status != "Succeeded":
            notready_pods.append(pod)
    if len(notready_pods) != 0:
        status = False
    else:
        status = True
    return status, notready_pods


# Monitor component namespace
def monitor_component(iteration, component_namespace):
    watch_component_status, failed_component_pods = monitor_namespace(component_namespace)
    logging.info("Iteration %s: %s: %s" % (iteration, component_namespace, watch_component_status))
    return watch_component_status, failed_component_pods


# Find the node kraken is deployed on
# Set global kraken node to not delete
def find_kraken_node():
    pods = get_all_pods()
    kraken_pod_name = None
    for pod in pods:
        if "kraken-deployment" in pod[0]:
            kraken_pod_name = pod[0]
            kraken_project = pod[1]
            break
    # have to switch to proper project

    if kraken_pod_name:
        # get kraken-deployment pod, find node name
        try:
            node_name = runcommand.invoke(
                "kubectl get pods/"
                + str(kraken_pod_name)
                + ' -o jsonpath="{.spec.nodeName}"'
                + " -n"
                + str(kraken_project)
            )

            global kraken_node_name
            kraken_node_name = node_name
        except Exception as e:
            logging.info("%s" % (e))
            sys.exit(1)
