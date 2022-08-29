from kubernetes import config, client
from kubernetes.client.rest import ApiException
import logging
import random
from enum import Enum


class Actions(Enum):
    """
    This enumeration indicates different kinds of node operations
    """

    START = "Start"
    STOP = "Stop"
    TERMINATE = "Terminate"
    REBOOT = "Reboot"


def setup_kubernetes(kubeconfig_path):
    """
    Sets up the Kubernetes client
    """

    if kubeconfig_path is None:
        kubeconfig_path = config.KUBE_CONFIG_DEFAULT_LOCATION
    kubeconfig = config.kube_config.KubeConfigMerger(kubeconfig_path)

    if kubeconfig.config is None:
        raise Exception(
            "Invalid kube-config file: %s. " "No configuration found." % kubeconfig_path
        )
    loader = config.kube_config.KubeConfigLoader(
        config_dict=kubeconfig.config,
    )
    client_config = client.Configuration()
    loader.load_and_set(client_config)
    return client.ApiClient(configuration=client_config)


def list_killable_nodes(core_v1, label_selector=None):
    """
    Returns a list of nodes that can be stopped/reset/released
    """

    nodes = []
    try:
        if label_selector:
            ret = core_v1.list_node(pretty=True, label_selector=label_selector)
        else:
            ret = core_v1.list_node(pretty=True)
    except ApiException as e:
        logging.error("Exception when calling CoreV1Api->list_node: %s\n" % e)
        raise e
    for node in ret.items:
        for cond in node.status.conditions:
            if str(cond.type) == "Ready" and str(cond.status) == "True":
                nodes.append(node.metadata.name)
    return nodes


def list_startable_nodes(core_v1, label_selector=None):
    """
    Returns a list of nodes that can be started
    """

    nodes = []
    try:
        if label_selector:
            ret = core_v1.list_node(pretty=True, label_selector=label_selector)
        else:
            ret = core_v1.list_node(pretty=True)
    except ApiException as e:
        logging.error("Exception when calling CoreV1Api->list_node: %s\n" % e)
        raise e
    for node in ret.items:
        for cond in node.status.conditions:
            if str(cond.type) == "Ready" and str(cond.status) != "True":
                nodes.append(node.metadata.name)
    return nodes


def get_node_list(cfg, action, core_v1):
    """
    Returns a list of nodes to be used in the node scenarios. The list returned is constructed as follows:
        - If the key 'name' is present in the node scenario config, the value is extracted and split into
          a list
        - Each node in the list is fed to the get_node function which checks if the node is killable or
          fetches the node using the label selector
    """

    def get_node(node_name, label_selector, instance_kill_count, action, core_v1):
        list_nodes_func = (
            list_startable_nodes if action == Actions.START else list_killable_nodes
        )
        if node_name in list_nodes_func(core_v1):
            return [node_name]
        elif node_name:
            logging.info(
                "Node with provided node_name does not exist or the node might "
                "be in NotReady state."
            )
        nodes = list_nodes_func(core_v1, label_selector)
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

    if cfg.name:
        input_nodes = cfg.name.split(",")
    else:
        input_nodes = [""]
    scenario_nodes = set()

    if cfg.skip_openshift_checks:
        scenario_nodes = input_nodes
    else:
        for node in input_nodes:
            nodes = get_node(
                node, cfg.label_selector, cfg.instance_count, action, core_v1
            )
            scenario_nodes.update(nodes)

    return list(scenario_nodes)


def watch_node_status(node, status, timeout, watch_resource, core_v1):
    """
    Monitor the status of a node for change
    """
    count = timeout
    for event in watch_resource.stream(
        core_v1.list_node,
        field_selector=f"metadata.name={node}",
        timeout_seconds=timeout,
    ):
        conditions = [
            status
            for status in event["object"].status.conditions
            if status.type == "Ready"
        ]
        if conditions[0].status == status:
            watch_resource.stop()
            break
        else:
            count -= 1
            logging.info("Status of node " + node + ": " + str(conditions[0].status))
        if not count:
            watch_resource.stop()


def wait_for_ready_status(node, timeout, watch_resource, core_v1):
    """
    Wait until the node status becomes Ready
    """
    watch_node_status(node, "True", timeout, watch_resource, core_v1)


def wait_for_not_ready_status(node, timeout, watch_resource, core_v1):
    """
    Wait until the node status becomes Not Ready
    """
    watch_node_status(node, "False", timeout, watch_resource, core_v1)


def wait_for_unknown_status(node, timeout, watch_resource, core_v1):
    """
    Wait until the node status becomes Unknown
    """
    watch_node_status(node, "Unknown", timeout, watch_resource, core_v1)
