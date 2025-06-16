import logging
from datetime import time
from random import random

import yaml
from krkn_lib.k8s import KrknKubernetes
from kubernetes.client import ApiextensionsV1Api, CustomObjectsApi


def get_bridge_name(cli: ApiextensionsV1Api, custom_obj: CustomObjectsApi) -> str:
    """
    Function that gets OVS bridge present in node.

    Args:
        cli (ApiextensionsV1Api)
            - Object to interact with Kubernetes Python client's Apiextensions API

        custom_obj (CustomObjectsApi)
            - Object to interact with Kubernetes Python client's CustomObjects API

    Returns
        OVS bridge name
    """

    current_crds = [
        x["metadata"]["name"].lower()
        for x in cli.list_custom_resource_definition().to_dict()["items"]
    ]
    if "networks.config.openshift.io" not in current_crds:
        raise Exception("OpenShiftSDN or OVNKubernetes not found in cluster ")
    else:
        resource = custom_obj.get_cluster_custom_object(
            group="config.openshift.io", version="v1", name="cluster", plural="networks"
        )
        network_type = resource["spec"]["networkType"]
        if network_type == "OpenShiftSDN":
            bridge = "br0"
        elif network_type == "OVNKubernetes":
            bridge = "br-int"
        else:
            raise Exception(
                f"OpenShiftSDN or OVNKubernetes not found in cluster {network_type}"
            )
    return bridge

def get_test_pods(
    pod_name: str, pod_label: str, namespace: str, kubecli: KrknKubernetes
) -> list[str]:
    """
    Function that returns a list of pods to apply network policy

    Args:
        pod_name (string)
            - pod on which network policy need to be applied

        pod_label (string)
            - pods matching the label on which network policy
              need to be applied

        namepsace (string)
            - namespace in which the pod is present

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

    Returns:
        pod names (string) in the namespace
    """
    pods_list = []
    pods_list = kubecli.list_pods(label_selector=pod_label, namespace=namespace)
    if pod_name and pod_name not in pods_list:
        raise Exception("pod name not found in namespace ")
    elif pod_name and pod_name in pods_list:
        pods_list.clear()
        pods_list.append(pod_name)
        return pods_list
    else:
        return pods_list

def check_bridge_interface(
    node_name: str, pod_template, bridge_name: str, kubecli: KrknKubernetes
) -> bool:
    """
    Function  is used to check if the required OVS or OVN bridge is found in
    in the node.

    Args:
        node_name (string):
            - node in which to check for the bridge interface

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interfaces

        bridge_name (string):
            - bridge name to check for in the node.

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

    Returns:
        Returns True if the bridge is found in the  node.
    """
    nodes = kubecli.get_node(node_name, None, 1)
    node_bridge = []
    for node in nodes:
        node_bridge = list_bridges(node, pod_template, kubecli)
    if bridge_name not in node_bridge:
        raise Exception(f"OVS bridge {bridge_name} not found on the node ")

    return True

def list_bridges(node: str, pod_template, kubecli: KrknKubernetes) -> typing.List[str]:
    """
    Function that returns a list of bridges on the node

    Args:
        node (string)
            - Node from which the list of bridges is to be returned

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interface

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

    Returns:
        List of bridges on the node.
    """

    pod_body = yaml.safe_load(pod_template.render(nodename=node))
    logging.info("Creating pod to query bridge on node %s" % node)
    kubecli.create_pod(pod_body, "default", 300)

    try:
        cmd = ["/host", "ovs-vsctl", "list-br"]
        output = kubecli.exec_cmd_in_pod(
            cmd, "modtools", "default", base_command="chroot"
        )

        if not output:
            raise Exception(f"Exception occurred while executing command {cmd} in pod")

        bridges = output.split("\n")

    finally:
        logging.info("Deleting pod to query interface on node")
        kubecli.delete_pod("modtools", "default")

    return bridges

def apply_outage_policy(
    node_dict: dict[str, str],
    ports: list[str],
    job_template,
    pod_template,
    direction: str,
    duration: str,
    bridge_name: str,
    kubecli: KrknKubernetes,
) -> list[str]:
    """
    Function that applies filters(ingress or egress) to block traffic.

    Args:
        node_dict (Dict)
            - node to pod IP mapping

        ports (List)
            - List of ports to block

        job_template (jinja2.environment.Template)
            - The YAML template used to instantiate a job to apply and remove
              the filters on the interfaces

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interface

        direction (string)
            - Duration for which the traffic control is to be done

        bridge_name (string):
            - bridge to which  filter rules need to be applied

        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

        batch_cli (BatchV1Api)
            - Object to interact with Kubernetes Python client's BatchV1Api API

    Returns:
        The name of the job created that executes the commands on a node
        for ingress chaos scenario
    """

    job_list = []
    yml_list = []
    cookie_list = []
    cookie = random.randint(100, 10000)
    net_direction = {"egress": "nw_src", "ingress": "nw_dst"}
    br = "br0"
    table = 0
    if bridge_name == "br-int":
        br = "br-int"
        table = 8
    for node, ips in node_dict.items():
        while len(check_cookie(node, pod_template, br, cookie, kubecli)) > 2 or cookie in cookie_list:
            cookie = random.randint(100, 10000)
        exec_cmd = ""
        for ip in ips:
            for port in ports:
                target_port = port
                exec_cmd = f"{exec_cmd}ovs-ofctl -O  OpenFlow13 add-flow {br} cookie={cookie},table={table},priority=65535,tcp,{net_direction[direction]}={ip},tp_dst={target_port},actions=drop;"
                exec_cmd = f"{exec_cmd}ovs-ofctl -O  OpenFlow13 add-flow {br} cookie={cookie},table={table},priority=65535,udp,{net_direction[direction]}={ip},tp_dst={target_port},actions=drop;"
            if not ports:
                exec_cmd = f"{exec_cmd}ovs-ofctl -O  OpenFlow13 add-flow {br} cookie={cookie},table={table},priority=65535,ip,{net_direction[direction]}={ip},actions=drop;"
        exec_cmd = f"sleep 30;{exec_cmd}sleep {duration};ovs-ofctl -O  OpenFlow13  del-flows {br} cookie={cookie}/-1"
        cookie_list.append(cookie)
        logging.info("Executing %s on node %s" % (exec_cmd, node))

        job_body = yaml.safe_load(
            job_template.render(
                jobname=str(hash(node))[:5] + str(random.randint(0, 10000)),
                nodename=node,
                cmd=exec_cmd,
            )
        )
        yml_list.append(job_body)
    for job_body in yml_list:
        api_response = kubecli.create_job(job_body)
        if api_response is None:
            raise Exception("Error creating job")

        job_list.append(job_body["metadata"]["name"])
    return job_list

def check_cookie(
    node: str, pod_template, br_name, cookie, kubecli: KrknKubernetes
) -> str:
    """
    Function to check for matching flow rules

    Args:
        node (string):
            - node in which to check for the flow rules

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interfaces

        br_name (string):
            - bridge against which the flows rules need to be checked

        cookie (string):
            - flows matching the cookexec_cmd_in_podie are listed

        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

    Returns
        Returns the matching flow rules
    """

    pod_body = yaml.safe_load(pod_template.render(nodename=node))
    logging.info("Creating pod to query duplicate rules on node %s" % node)
    kubecli.create_pod(pod_body, "default", 300)

    try:
        cmd = [
            "chroot",
            "/host",
            "ovs-ofctl",
            "-O",
            "OpenFlow13",
            "dump-flows",
            br_name,
            f"cookie={cookie}/-1",
        ]
        output = kubecli.exec_cmd_in_pod(
            cmd, "modtools", "default", base_command="chroot"
        )

        if not output:
            raise Exception(f"Exception occurred while executing command {cmd} in pod")

        flow_list = output.split("\n")

    finally:
        logging.info("Deleting pod to query interface on node")
        kubecli.delete_pod("modtools", "default")

    return flow_list


def wait_for_job(
    job_list: list[str], kubecli: KrknKubernetes, timeout: int = 300
) -> None:
    """
    Function that waits for a list of jobs to finish within a time period

    Args:
        job_list (List of strings)
            - The list of jobs to check for completion

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

        timeout (int)
            - Max duration to wait for checking whether the jobs are completed
    """

    wait_time = time.time() + timeout
    count = 0
    job_len = len(job_list)
    while count != job_len:
        for job_name in job_list:
            try:
                api_response = kubecli.get_job_status(job_name, namespace="default")
                if (
                    api_response.status.succeeded is not None
                    or api_response.status.failed is not None
                ):
                    count += 1
                    job_list.remove(job_name)
            except Exception:
                logging.warning("Exception in getting job status")
            if time.time() > wait_time:
                raise Exception(
                    "Jobs did not complete within "
                    "the {0}s timeout period".format(timeout)
                )
            time.sleep(5)

def delete_jobs(kubecli: KrknKubernetes, job_list: list[str]):
    """
    Function that deletes jobs

    Args:
        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

        job_list (List of strings)
            - The list of jobs to delete
    """

    for job_name in job_list:
        try:
            api_response = kubecli.get_job_status(job_name, namespace="default")
            if api_response.status.failed is not None:
                pod_name = get_job_pods(kubecli, api_response)
                pod_stat = kubecli.read_pod(name=pod_name, namespace="default")
                logging.error(pod_stat.status.container_statuses)
                pod_log_response = kubecli.get_pod_log(
                    name=pod_name, namespace="default"
                )
                pod_log = pod_log_response.data.decode("utf-8")
                logging.error(pod_log)
        except Exception as e:
            logging.warning("Exception in getting job status: %s" % str(e))


def get_job_pods(kubecli: KrknKubernetes, api_response):
    """
    Function that gets the pod corresponding to the job

    Args:
        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

        api_response
            - The API response for the job status

    Returns
        Pod corresponding to the job
    """

    controllerUid = api_response.metadata.labels["controller-uid"]
    pod_label_selector = "controller-uid=" + controllerUid
    pods_list = kubecli.list_pods(
        label_selector=pod_label_selector, namespace="default"
    )

    return pods_list[0]