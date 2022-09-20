from kubernetes import config, client
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
import sys
import time
import logging
import random

def setup_kubernetes(kubeconfig_path):
    """
    Sets up the Kubernetes client
    """

    if kubeconfig_path is None:
        kubeconfig_path = config.KUBE_CONFIG_DEFAULT_LOCATION
    config.load_kube_config(kubeconfig_path)
    cli = client.CoreV1Api()
    batch_cli = client.BatchV1Api()

    return cli, batch_cli


def create_job(batch_cli, body, namespace="default"):
    """
    Function used to create a job from a YAML config
    """

    try:
        api_response = batch_cli.create_namespaced_job(body=body, namespace=namespace)
        return api_response
    except ApiException as api:
        logging.warn(
            "Exception when calling \
                       BatchV1Api->create_job: %s"
            % api
        )
        if api.status == 409:
            logging.warn("Job already present")
    except Exception as e:
        logging.error(
            "Exception when calling \
                       BatchV1Api->create_namespaced_job: %s"
            % e
        )
        raise


def delete_pod(cli, name, namespace):
    """
    Function that deletes a pod and waits until deletion is complete
    """

    try:
        cli.delete_namespaced_pod(name=name, namespace=namespace)
        while cli.read_namespaced_pod(name=name, namespace=namespace):
            time.sleep(1)
    except ApiException as e:
        if e.status == 404:
            logging.info("Pod deleted")
        else:
            logging.error("Failed to delete pod %s" % e)
            raise e


def create_pod(cli, body, namespace, timeout=120):
    """
    Function used to create a pod from a YAML config
    """

    try:
        pod_stat = None
        pod_stat = cli.create_namespaced_pod(body=body, namespace=namespace)
        end_time = time.time() + timeout
        while True:
            pod_stat = cli.read_namespaced_pod(name=body["metadata"]["name"], namespace=namespace)
            if pod_stat.status.phase == "Running":
                break
            if time.time() > end_time:
                raise Exception("Starting pod failed")
            time.sleep(1)
    except Exception as e:
        logging.error("Pod creation failed %s" % e)
        if pod_stat:
            logging.error(pod_stat.status.container_statuses)
        delete_pod(cli, body["metadata"]["name"], namespace)
        sys.exit(1)


def exec_cmd_in_pod(cli, command, pod_name, namespace, container=None):
    """
    Function used to execute a command in a running pod
    """

    exec_command = command
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
    except Exception as e:
        return False

    return ret


def create_ifb(cli, number, pod_name):
    """
    Function that creates virtual interfaces in a pod. Makes use of modprobe commands
    """

    exec_command = ['chroot', '/host', 'modprobe', 'ifb','numifbs=' + str(number)]
    resp = exec_cmd_in_pod(cli, exec_command, pod_name, 'default')

    for i in range(0, number):
        exec_command = ['chroot', '/host','ip','link','set','dev']   
        exec_command+= ['ifb' + str(i), 'up']
        resp = exec_cmd_in_pod(cli, exec_command, pod_name, 'default')


def delete_ifb(cli, pod_name):
    """
    Function that deletes all virtual interfaces in a pod. Makes use of modprobe command
    """

    exec_command = ['chroot', '/host', 'modprobe', '-r', 'ifb']
    resp = exec_cmd_in_pod(cli, exec_command, pod_name, 'default')
    

def list_pods(cli, namespace, label_selector=None):
    """
    Function used to list pods in a given namespace and having a certain label
    """

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
        raise e
    for pod in ret.items:
        pods.append(pod.metadata.name)

    return pods


def get_job_status(batch_cli, name, namespace="default"):
    """
    Function that retrieves the status of a running job in a given namespace
    """

    try:
        return batch_cli.read_namespaced_job_status(name=name, namespace=namespace)
    except Exception as e:
        logging.error(
            "Exception when calling \
                       BatchV1Api->read_namespaced_job_status: %s"
            % e
        )
        raise


def get_pod_log(cli, name, namespace="default"):
    """
    Function that retrieves the logs of a running pod in a given namespace
    """

    return cli.read_namespaced_pod_log(
        name=name, namespace=namespace, _return_http_data_only=True, _preload_content=False
    )


def read_pod(cli, name, namespace="default"):
    """
    Function that retrieves the info of a running pod in a given namespace
    """

    return cli.read_namespaced_pod(name=name, namespace=namespace)



def delete_job(batch_cli, name, namespace="default"):
    """
    Deletes a job with the input name and namespace
    """

    try:
        api_response = batch_cli.delete_namespaced_job(
            name=name,
            namespace=namespace,
            body=client.V1DeleteOptions(propagation_policy="Foreground", grace_period_seconds=0),
        )
        logging.debug("Job deleted. status='%s'" % str(api_response.status))
        return api_response
    except ApiException as api:
        logging.warn(
            "Exception when calling \
                       BatchV1Api->create_namespaced_job: %s"
            % api
        )
        logging.warn("Job already deleted\n")
    except Exception as e:
        logging.error(
            "Exception when calling \
                       BatchV1Api->delete_namespaced_job: %s\n"
            % e
        )
        sys.exit(1)


def list_ready_nodes(cli, label_selector=None):
    """
    Returns a list of ready nodes
    """

    nodes = []
    try:
        if label_selector:
            ret = cli.list_node(pretty=True, label_selector=label_selector)
        else:
            ret = cli.list_node(pretty=True)
    except ApiException as e:
        logging.error("Exception when calling CoreV1Api->list_node: %s\n" % e)
        raise e
    for node in ret.items:
        for cond in node.status.conditions:
            if str(cond.type) == "Ready" and str(cond.status) == "True":
                nodes.append(node.metadata.name)

    return nodes


def get_node(node_name, label_selector, instance_kill_count, cli):
    """
    Returns active node(s) on which the scenario can be performed 
    """

    if node_name in list_ready_nodes(cli):
        return [node_name]
    elif node_name:
        logging.info(
            "Node with provided node_name does not exist or the node might "
            "be in NotReady state."
        )
    nodes = list_ready_nodes(cli, label_selector)
    if not nodes:
        raise Exception("Ready nodes with the provided label selector do not exist")
    logging.info(
        "Ready nodes with the label selector %s: %s" % (label_selector, nodes)
    )
    number_of_nodes = len(nodes)
    if instance_kill_count == number_of_nodes:
        return nodes
    nodes_to_return = []
    for i in range(instance_kill_count):
        node_to_add = nodes[random.randint(0, len(nodes) - 1)]
        nodes_to_return.append(node_to_add)
        nodes.remove(node_to_add)
    return nodes_to_return
