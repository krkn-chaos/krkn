#!/usr/bin/env python3
import sys
import os
import typing
import yaml
import logging
import time
import random
import re
from dataclasses import dataclass, field
from traceback import format_exc
from jinja2 import Environment, FileSystemLoader
from krkn_lib.k8s import KrknKubernetes
from arcaflow_plugin_sdk import plugin, validation
from kubernetes import client
from kubernetes.client.api.apiextensions_v1_api import ApiextensionsV1Api
from kubernetes.client.api.custom_objects_api import CustomObjectsApi
from . import cerberus


def get_test_pods(
    pod_name: str, pod_label: str, namespace: str, kubecli: KrknKubernetes
) -> typing.List[str]:
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
    pods_list = kubecli.list_pods(
        label_selector=pod_label, namespace=namespace)
    if pod_name and pod_name not in pods_list:
        raise Exception("pod name not found in namespace ")
    elif pod_name and pod_name in pods_list:
        pods_list.clear()
        pods_list.append(pod_name)
        return pods_list
    else:
        return pods_list


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


def delete_jobs(kubecli: KrknKubernetes, job_list: typing.List[str]):
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
            api_response = kubecli.get_job_status(
                job_name, namespace="default")
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
            logging.warn("Exception in getting job status: %s" % str(e))
        api_response = kubecli.delete_job(name=job_name, namespace="default")


def wait_for_job(
    job_list: typing.List[str], kubecli: KrknKubernetes, timeout: int = 300
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
                api_response = kubecli.get_job_status(
                    job_name, namespace="default")
                if (
                    api_response.status.succeeded is not None
                    or api_response.status.failed is not None
                ):
                    count += 1
                    job_list.remove(job_name)
            except Exception:
                logging.warn("Exception in getting job status")
            if time.time() > wait_time:
                raise Exception(
                    "Jobs did not complete within "
                    "the {0}s timeout period".format(timeout)
                )
            time.sleep(5)


def get_bridge_name(cli: ApiextensionsV1Api,
                    custom_obj: CustomObjectsApi) -> str:
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


def apply_outage_policy(
    node_dict: typing.Dict[str, str],
    ports: typing.List[str],
    job_template,
    pod_template,
    direction: str,
    duration: str,
    bridge_name: str,
    kubecli: KrknKubernetes,
) -> typing.List[str]:
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
    cookie = random.randint(100, 10000)
    net_direction = {"egress": "nw_src", "ingress": "nw_dst"}
    br = "br0"
    table = 0
    if bridge_name == "br-int":
        br = "br-int"
        table = 8
    for node, ips in node_dict.items():
        while len(check_cookie(node, pod_template, br, cookie, kubecli)) > 2:
            cookie = random.randint(100, 10000)
        exec_cmd = ""
        for ip in ips:
            for port in ports:
                target_port = port
                exec_cmd = f"{exec_cmd}ovs-ofctl -O  OpenFlow13 add-flow {br} cookie={cookie},table={table},priority=65535,tcp,{net_direction[direction]}={ip},tp_dst={target_port},actions=drop;"
                exec_cmd = f"{exec_cmd}ovs-ofctl -O  OpenFlow13 add-flow {br} cookie={cookie},table={table},priority=65535,udp,{net_direction[direction]}={ip},tp_dst={target_port},actions=drop;"
            if not ports:
                exec_cmd = f"{exec_cmd}ovs-ofctl -O  OpenFlow13 add-flow {br} cookie={cookie},table={table},priority=65535,ip,{net_direction[direction]}={ip},actions=drop;"
        exec_cmd = f"{exec_cmd}sleep {duration};ovs-ofctl -O  OpenFlow13  del-flows {br} cookie={cookie}/-1"
        logging.info("Executing %s on node %s" % (exec_cmd, node))

        job_body = yaml.safe_load(
            job_template.render(
                jobname=str(hash(node))[:5] + str(random.randint(0, 10000)),
                nodename=node,
                cmd=exec_cmd,
            )
        )
        api_response = kubecli.create_job(job_body)
        if api_response is None:
            raise Exception("Error creating job")

        job_list.append(job_body["metadata"]["name"])
    return job_list


def apply_ingress_policy(
    mod: str,
    node: str,
    ips: typing.List[str],
    job_template,
    pod_template,
    network_params: typing.Dict[str, str],
    duration: str,
    bridge_name: str,
    kubecli: KrknKubernetes,
    test_execution: str,
) -> typing.List[str]:
    """
    Function that applies ingress traffic shaping to pod interface.

    Args:

        mod (String)
            - Traffic shaping filter to apply

        node (String)
            - node associated with the pod

        ips (List)
            - IPs of pods found in the node

        job_template (jinja2.environment.Template)
            - The YAML template used to instantiate a job to apply and remove
              the filters on the interfaces

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interface

        network_params (Dictionary with key and value as string)
            - Loss/Delay/Bandwidth and their corresponding value

        duration (string)
            - Duration for which the traffic control is to be done

        bridge_name (string):
            - bridge to which  filter rules need to be applied

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

        test_execution (String)
            - The order in which the filters are applied

    Returns:
        The name of the job created that executes the traffic shaping
        filter
    """

    job_list = []

    create_virtual_interfaces(kubecli, len(ips), node, pod_template)

    for count, pod_ip in enumerate(set(ips)):
        pod_inf = get_pod_interface(
            node, pod_ip, pod_template, bridge_name, kubecli)
        exec_cmd = get_ingress_cmd(
            test_execution, pod_inf, mod, count, network_params, duration
        )
        logging.info("Executing %s on pod %s in node %s" %
                     (exec_cmd, pod_ip, node))
        job_body = yaml.safe_load(
            job_template.render(jobname=mod + str(pod_ip),
                                nodename=node, cmd=exec_cmd)
        )
        job_list.append(job_body["metadata"]["name"])
        api_response = kubecli.create_job(job_body)
        if api_response is None:
            raise Exception("Error creating job")
        if pod_ip == node:
            break
    return job_list


def apply_net_policy(
    mod: str,
    node: str,
    ips: typing.List[str],
    job_template,
    pod_template,
    network_params: typing.Dict[str, str],
    duration: str,
    bridge_name: str,
    kubecli: KrknKubernetes,
    test_execution: str,
) -> typing.List[str]:
    """
    Function that applies egress traffic shaping to pod interface.

    Args:

        mod (String)
            - Traffic shaping filter to apply

        node (String)
            - node associated with the pod

        ips (List)
            - IPs of pods found in the node

        job_template (jinja2.environment.Template)
            - The YAML template used to instantiate a job to apply and remove
              the filters on the interfaces

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interface

        network_params (Dictionary with key and value as string)
            - Loss/Delay/Bandwidth and their corresponding value

        duration (string)
            - Duration for which the traffic control is to be done

        bridge_name (string):
            - bridge to which  filter rules need to be applied

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

        test_execution (String)
            - The order in which the filters are applied

    Returns:
        The name of the job created that executes the traffic shaping
        filter
    """

    job_list = []

    for pod_ip in set(ips):
        pod_inf = get_pod_interface(
            node, pod_ip, pod_template, bridge_name, kubecli)
        exec_cmd = get_egress_cmd(
            test_execution, pod_inf, mod, network_params, duration
        )
        logging.info("Executing %s on pod %s in node %s" %
                     (exec_cmd, pod_ip, node))
        job_body = yaml.safe_load(
            job_template.render(jobname=mod + str(pod_ip),
                                nodename=node, cmd=exec_cmd)
        )
        job_list.append(job_body["metadata"]["name"])
        api_response = kubecli.create_job(job_body)
        if api_response is None:
            raise Exception("Error creating job")
    return job_list


def get_ingress_cmd(
    execution: str,
    test_interface: str,
    mod: str,
    count: int,
    vallst: typing.List[str],
    duration: str,
) -> str:
    """
    Function generates ingress filter to apply on pod

    Args:
        execution (str):
            - The order in which the filters are applied

        test_interface (str):
            - Pod interface

        mod (str):
            - Filter to apply

        count (int):
            - IFB device number

        vallst (typing.List[str]):
            - List of filters to apply

        duration (str):
            - Duration for which the traffic control is to be done

    Returns:
        str: ingress filter
    """
    ifb_dev = 'ifb{0}'.format(count)
    tc_set = tc_unset = tc_ls = ""
    param_map = {"latency": "delay", "loss": "loss", "bandwidth": "rate"}
    tc_set = "tc qdisc add dev {0} ingress ;".format(test_interface)
    tc_set = "{0} tc filter add dev {1} ingress matchall action mirred egress redirect dev {2} ;".format(
        tc_set, test_interface, ifb_dev)
    tc_set = "{0} tc qdisc replace dev {1} root netem".format(
        tc_set, ifb_dev)
    tc_unset = "{0} tc qdisc del dev {1} root ;".format(
        tc_unset, ifb_dev)
    tc_unset = "{0} tc qdisc del dev {1} ingress".format(
        tc_unset, test_interface)
    tc_ls = "{0} tc qdisc ls dev {1} ;".format(tc_ls, ifb_dev)
    if execution == "parallel":
        for val in vallst.keys():
            tc_set += " {0} {1} ".format(param_map[val], vallst[val])
        tc_set += ";"
    else:
        tc_set += " {0} {1} ;".format(param_map[mod], vallst[mod])
    exec_cmd = "{0} {1} sleep {2};{3}".format(
        tc_set, tc_ls, duration, tc_unset)

    return exec_cmd


def get_egress_cmd(
    execution: str,
    test_interface: str,
    mod: str,
    vallst: typing.List[str],
    duration: str,
) -> str:
    """
    Function generates egress filter to apply on pod

    Args:
        execution (str):
            - The order in which the filters are applied

        test_interface (str):
            - Pod interface

        mod (str):
            - Filter to apply

        vallst (typing.List[str]):
            - List of filters to apply

        duration (str):
            - Duration for which the traffic control is to be done

    Returns:
        str: egress filter
    """
    tc_set = tc_unset = tc_ls = ""
    param_map = {"latency": "delay", "loss": "loss", "bandwidth": "rate"}
    tc_set = "{0} tc qdisc replace dev {1} root netem".format(
        tc_set, test_interface)
    tc_unset = "{0} tc qdisc del dev {1} root ;".format(
        tc_unset, test_interface)
    tc_ls = "{0} tc qdisc ls dev {1} ;".format(tc_ls, test_interface)
    if execution == "parallel":
        for val in vallst.keys():
            tc_set += " {0} {1} ".format(param_map[val], vallst[val])
        tc_set += ";"
    else:
        tc_set += " {0} {1} ;".format(param_map[mod], vallst[mod])
    exec_cmd = "{0} {1} sleep {2};{3}".format(
        tc_set, tc_ls, duration, tc_unset)

    return exec_cmd


def create_virtual_interfaces(
    kubecli: KrknKubernetes,
    nummber: int,
    node: str,
    pod_template
) -> None:
    """
    Function that creates a privileged pod and uses it to create
    virtual interfaces on the node

    Args:
        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

        interface_list (List of strings)
            - The list of interfaces on the node for which virtual interfaces
              are to be created

        node (string)
            - The node on which the virtual interfaces are created

        pod_template (jinja2.environment.Template))
            - The YAML template used to instantiate a pod to create
              virtual interfaces on the node
    """
    pod_body = yaml.safe_load(
        pod_template.render(nodename=node)
    )
    kubecli.create_pod(pod_body, "default", 300)
    logging.info(
        "Creating {0} virtual interfaces on node {1} using a pod".format(
            nummber,
            node
        )
    )
    create_ifb(kubecli, nummber, 'modtools')
    logging.info("Deleting pod used to create virtual interfaces")
    kubecli.delete_pod("modtools", "default")


def delete_virtual_interfaces(
    kubecli: KrknKubernetes,
    node_list: typing.List[str],
    pod_template
):
    """
    Function that creates a privileged pod and uses it to delete all
    virtual interfaces on the specified nodes

    Args:
        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

        node_list (List of strings)
            - The list of nodes on which the list of virtual interfaces are
              to be deleted

        node (string)
            - The node on which the virtual interfaces are created

        pod_template (jinja2.environment.Template))
            - The YAML template used to instantiate a pod to delete
              virtual interfaces on the node
    """

    for node in node_list:
        pod_body = yaml.safe_load(
            pod_template.render(nodename=node)
        )
        kubecli.create_pod(pod_body, "default", 300)
        logging.info(
            "Deleting all virtual interfaces on node {0}".format(node)
        )
        delete_ifb(kubecli, 'modtools')
        kubecli.delete_pod("modtools", "default")


def create_ifb(kubecli: KrknKubernetes, number: int, pod_name: str):
    """
    Function that creates virtual interfaces in a pod.
    Makes use of modprobe commands
    """

    exec_command = [
        '/host',
        'modprobe', 'ifb', 'numifbs=' + str(number)
    ]
    kubecli.exec_cmd_in_pod(
        exec_command,
        pod_name,
        'default',
        base_command="chroot")

    for i in range(0, number):
        exec_command = ['/host', 'ip', 'link', 'set', 'dev']
        exec_command += ['ifb' + str(i), 'up']
        kubecli.exec_cmd_in_pod(
            exec_command,
            pod_name,
            'default',
            base_command="chroot"
        )


def delete_ifb(kubecli: KrknKubernetes, pod_name: str):
    """
    Function that deletes all virtual interfaces in a pod.
    Makes use of modprobe command
    """

    exec_command = ['/host', 'modprobe', '-r', 'ifb']
    kubecli.exec_cmd_in_pod(
        exec_command,
        pod_name,
        'default',
        base_command="chroot")


def list_bridges(
    node: str, pod_template, kubecli: KrknKubernetes
) -> typing.List[str]:
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
            logging.error(f"Exception occurred while executing command {cmd} in pod")
            sys.exit(1)

        bridges = output.split("\n")

    finally:
        logging.info("Deleting pod to query interface on node")
        kubecli.delete_pod("modtools", "default")

    return bridges


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
            logging.error(f"Exception occurred while executing command {cmd} in pod")
            sys.exit(1)

        flow_list = output.split("\n")

    finally:
        logging.info("Deleting pod to query interface on node")
        kubecli.delete_pod("modtools", "default")

    return flow_list


def get_pod_interface(
    node: str, ip: str, pod_template, br_name, kubecli: KrknKubernetes
) -> str:
    """
    Function to query the pod interface on a node

    Args:
        node (string):
            - node in which to check for the flow rules

        ip (string):
            - Pod IP

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interfaces

        br_name (string):
            - bridge against which the flows rules need to be checked

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

    Returns
        Returns the pod interface name
    """

    pod_body = yaml.safe_load(pod_template.render(nodename=node))
    logging.info("Creating pod to query pod interface on node %s" % node)
    kubecli.create_pod(pod_body, "default", 300)
    inf = ""

    try:
        if br_name == "br-int":
            find_ip = f"external-ids:ip_addresses={ip}/23"
        else:
            find_ip = f"external-ids:ip={ip}"
                       
        cmd = [
            "/host",
            "ovs-vsctl",
            "--bare",
            "--columns=name",
            "find",
            "interface",
            find_ip,
        ]
      
        output = kubecli.exec_cmd_in_pod(
            cmd, "modtools", "default", base_command="chroot"
        )
        if not output:
            cmd= [
                "/host",
                "ip",
                "addr",
                "show"
            ]
            output = kubecli.exec_cmd_in_pod(
                cmd, "modtools", "default", base_command="chroot")
            for if_str in output.split("\n"):
                if re.search(ip,if_str):
                    inf = if_str.split(' ')[-1]
        else:
            inf = output       
    finally:
        logging.info("Deleting pod to query interface on node")
        kubecli.delete_pod("modtools", "default")
    return inf


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


@dataclass
class InputParams:
    """
    This is the data structure for the input parameters of the step defined below.
    """

    namespace: typing.Annotated[str, validation.min(1)] = field(
        metadata={
            "name": "Namespace",
            "description": "Namespace of the pod to which filter need to be applied"
            "for details.",
        }
    )

    direction: typing.List[str] = field(
        default_factory=lambda: ["ingress", "egress"],
        metadata={
            "name": "Direction",
            "description": "List of directions to apply filters"
            "Default both egress and ingress.",
        },
    )

    ingress_ports: typing.List[int] = field(
        default_factory=list,
        metadata={
            "name": "Ingress ports",
            "description": "List of ports to block traffic on"
            "Default [], i.e. all ports",
        },
    )

    egress_ports: typing.List[int] = field(
        default_factory=list,
        metadata={
            "name": "Egress ports",
            "description": "List of ports to block traffic on"
            "Default [], i.e. all ports",
        },
    )
    kubeconfig_path: typing.Optional[str] = field(
        default=None,
        metadata={
            "name": "Kubeconfig path",
            "description": "Kubeconfig file as string\n"
            "See https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/ for "
            "details.",
        },
    )
    pod_name: typing.Annotated[
        typing.Optional[str],
        validation.required_if_not("label_selector"),
    ] = field(
        default=None,
        metadata={
            "name": "Pod name",
            "description": "When label_selector is not specified, pod matching the name will be"
            "selected for the chaos scenario",
        },
    )

    label_selector: typing.Annotated[
        typing.Optional[str], validation.required_if_not("pod_name")
    ] = field(
        default=None,
        metadata={
            "name": "Label selector",
            "description": "Kubernetes label selector for the target pod. "
            "When pod_name is not specified, pod with matching label_selector is selected for chaos scenario",
        },
    )

    kraken_config: typing.Optional[str] = field(
        default=None,
        metadata={
            "name": "Kraken Config",
            "description": "Path to the config file of Kraken. "
            "Set this field if you wish to publish status onto Cerberus",
        },
    )

    test_duration: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=120,
        metadata={
            "name": "Test duration",
            "description": "Duration for which each step of the ingress chaos testing "
            "is to be performed.",
        },
    )

    wait_duration: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=300,
        metadata={
            "name": "Wait Duration",
            "description": "Wait duration for finishing a test and its cleanup."
            "Ensure that it is significantly greater than wait_duration",
        },
    )

    instance_count: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=1,
        metadata={
            "name": "Instance Count",
            "description": "Number of pods to perform action/select that match "
            "the label selector.",
        },
    )


@dataclass
class PodOutageSuccessOutput:
    """
    This is the output data structure for the success case.
    """

    test_pods: typing.List[str] = field(
        metadata={
            "name": "Test pods",
            "description": "List of test pods where the selected for chaos scenario",
        }
    )

    direction: typing.List[str] = field(
        metadata={
            "name": "Direction",
            "description": "List of directions to which the filters were applied.",
        }
    )

    ingress_ports: typing.List[int] = field(
        metadata={
            "name": "Ingress ports",
            "description": "List of ports to block traffic on",
        }
    )

    egress_ports: typing.List[int] = field(
        metadata={
            "name": "Egress ports",
            "description": "List of ports to block traffic on",
        }
    )


@dataclass
class PodOutageErrorOutput:
    error: str = field(
        metadata={
            "name": "Error",
            "description": "Error message when there is a run-time error during "
            "the execution of the scenario",
        }
    )


@plugin.step(
    id="pod_network_outage",
    name="Pod Outage",
    description="Blocks ingress and egress network traffic at pod level",
    outputs={"success": PodOutageSuccessOutput, "error": PodOutageErrorOutput},
)
def pod_outage(
    params: InputParams,
) -> typing.Tuple[str, typing.Union[PodOutageSuccessOutput, PodOutageErrorOutput]]:
    """
    Function that performs pod outage chaos scenario based
    on the provided confiapply_net_policyguration

    Args:
        params (InputParams,)
            - The object containing the configuration for the scenario

    Returns
        A 'success' or 'error' message along with their details
    """
    direction = ["ingress", "egress"]
    file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
    env = Environment(loader=file_loader)
    job_template = env.get_template("job.j2")
    pod_module_template = env.get_template("pod_module.j2")
    test_namespace = params.namespace
    test_label_selector = params.label_selector
    test_pod_name = params.pod_name
    filter_dict = {}
    job_list = []
    publish = False

    if params.kraken_config:
        failed_post_scenarios = ""
        try:
            with open(params.kraken_config, "r") as f:
                config = yaml.full_load(f)
        except Exception:
            logging.error("Error reading Kraken config from %s" %
                          params.kraken_config)
            return "error", PodOutageErrorOutput(format_exc())
        publish = True

    for i in params.direction:
        filter_dict[i] = eval(f"params.{i}_ports")

    try:
        ip_set = set()
        node_dict = {}
        label_set = set()

        kubecli = KrknKubernetes(kubeconfig_path=params.kubeconfig_path)
        api_ext = client.ApiextensionsV1Api(kubecli.api_client)
        custom_obj = client.CustomObjectsApi(kubecli.api_client)

        br_name = get_bridge_name(api_ext, custom_obj)
        pods_list = get_test_pods(
            test_pod_name, test_label_selector, test_namespace, kubecli
        )

        while not len(pods_list) <= params.instance_count:
            pods_list.pop(random.randint(0, len(pods_list) - 1))

        for pod_name in pods_list:
            pod_stat = kubecli.read_pod(pod_name, test_namespace)
            ip_set.add(pod_stat.status.pod_ip)
            node_dict.setdefault(pod_stat.spec.node_name, [])
            node_dict[pod_stat.spec.node_name].append(pod_stat.status.pod_ip)
            for key, value in pod_stat.metadata.labels.items():
                label_set.add("%s=%s" % (key, value))

        check_bridge_interface(
            list(node_dict.keys())[0], pod_module_template, br_name, kubecli
        )

        for direction, ports in filter_dict.items():
            pass
            job_list.extend(
                apply_outage_policy(
                    node_dict,
                    ports,
                    job_template,
                    pod_module_template,
                    direction,
                    params.test_duration,
                    br_name,
                    kubecli,
                )
            )

        start_time = int(time.time())
        logging.info("Waiting for job to finish")
        wait_for_job(job_list[:], kubecli, params.test_duration + 300)
        end_time = int(time.time())
        if publish:
            cerberus.publish_kraken_status(
                config, failed_post_scenarios, start_time, end_time
            )

        return "success", PodOutageSuccessOutput(
            test_pods=pods_list,
            direction=params.direction,
            ingress_ports=params.ingress_ports,
            egress_ports=params.egress_ports,
        )
    except Exception as e:
        logging.error(
            "Pod network outage scenario exiting due to Exception - %s" % e)
        return "error", PodOutageErrorOutput(format_exc())
    finally:
        logging.info("Deleting jobs(if any)")
        delete_jobs(kubecli, job_list[:])


@dataclass
class EgressParams:
    """
    This is the data structure for the input parameters of the step defined below.
    """

    namespace: typing.Annotated[str, validation.min(1)] = field(
        metadata={
            "name": "Namespace",
            "description": "Namespace of the pod to which filter need to be applied"
            "for details.",
        }
    )

    network_params: typing.Dict[str, str] = field(
        metadata={
            "name": "Network Parameters",
            "description": "The network filters that are applied on the interface. "
            "The currently supported filters are latency, "
            "loss and bandwidth",
        },
    )

    kubeconfig_path: typing.Optional[str] = field(
        default=None,
        metadata={
            "name": "Kubeconfig path",
            "description": "Kubeconfig file as string\n"
            "See https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/ for "
            "details.",
        },
    )
    pod_name: typing.Annotated[
        typing.Optional[str],
        validation.required_if_not("label_selector"),
    ] = field(
        default=None,
        metadata={
            "name": "Pod name",
            "description": "When label_selector is not specified, pod matching the name will be"
            "selected for the chaos scenario",
        },
    )

    label_selector: typing.Annotated[
        typing.Optional[str], validation.required_if_not("pod_name")
    ] = field(
        default=None,
        metadata={
            "name": "Label selector",
            "description": "Kubernetes label selector for the target pod. "
            "When pod_name is not specified, pod with matching label_selector is selected for chaos scenario",
        },
    )

    kraken_config: typing.Optional[str] = field(
        default=None,
        metadata={
            "name": "Kraken Config",
            "description": "Path to the config file of Kraken. "
            "Set this field if you wish to publish status onto Cerberus",
        },
    )

    test_duration: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=90,
        metadata={
            "name": "Test duration",
            "description": "Duration for which each step of the ingress chaos testing "
            "is to be performed.",
        },
    )

    wait_duration: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=300,
        metadata={
            "name": "Wait Duration",
            "description": "Wait duration for finishing a test and its cleanup."
            "Ensure that it is significantly greater than wait_duration",
        },
    )

    instance_count: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=1,
        metadata={
            "name": "Instance Count",
            "description": "Number of pods to perform action/select that match "
            "the label selector.",
        },
    )

    execution_type: typing.Optional[str] = field(
        default="parallel",
        metadata={
            "name": "Execution Type",
            "description": "The order in which the ingress filters are applied. "
            "Execution type can be 'serial' or 'parallel'",
        },
    )


@dataclass
class PodEgressNetShapingSuccessOutput:
    """
    This is the output data structure for the success case.
    """

    test_pods: typing.List[str] = field(
        metadata={
            "name": "Test pods",
            "description": "List of test pods where the selected for chaos scenario",
        }
    )

    network_parameters: typing.Dict[str, str] = field(
        metadata={
            "name": "Network Parameters",
            "description": "The network filters that are applied on the interfaces",
        }
    )

    execution_type: str = field(
        metadata={
            "name": "Execution Type",
            "description": "The order in which the filters are applied",
        }
    )


@dataclass
class PodEgressNetShapingErrorOutput:
    error: str = field(
        metadata={
            "name": "Error",
            "description": "Error message when there is a run-time error during "
            "the execution of the scenario",
        }
    )


@plugin.step(
    id="pod_egress_shaping",
    name="Pod egress network Shaping",
    description="Does egress network traffic shaping at pod level",
    outputs={
        "success": PodEgressNetShapingSuccessOutput,
        "error": PodEgressNetShapingErrorOutput,
    },
)
def pod_egress_shaping(
    params: EgressParams,
) -> typing.Tuple[
    str, typing.Union[PodEgressNetShapingSuccessOutput,
                      PodEgressNetShapingErrorOutput]
]:
    """
    Function that performs egress pod traffic shaping based
    on the provided configuration

    Args:
        params (EgressParams,)
            - The object containing the configuration for the scenario

    Returns
        A 'success' or 'error' message along with their details
    """

    file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
    env = Environment(loader=file_loader)
    job_template = env.get_template("job.j2")
    pod_module_template = env.get_template("pod_module.j2")
    test_namespace = params.namespace
    test_label_selector = params.label_selector
    test_pod_name = params.pod_name
    job_list = []
    publish = False

    if params.kraken_config:
        failed_post_scenarios = ""
        try:
            with open(params.kraken_config, "r") as f:
                config = yaml.full_load(f)
        except Exception:
            logging.error("Error reading Kraken config from %s" %
                          params.kraken_config)
            return "error", PodEgressNetShapingErrorOutput(format_exc())
        publish = True

    try:
        ip_set = set()
        node_dict = {}
        label_set = set()
        param_lst = ["latency", "loss", "bandwidth"]
        mod_lst = [i for i in param_lst if i in params.network_params]

        kubecli = KrknKubernetes(kubeconfig_path=params.kubeconfig_path)
        api_ext = client.ApiextensionsV1Api(kubecli.api_client)
        custom_obj = client.CustomObjectsApi(kubecli.api_client)

        br_name = get_bridge_name(api_ext, custom_obj)
        pods_list = get_test_pods(
            test_pod_name, test_label_selector, test_namespace, kubecli
        )

        while not len(pods_list) <= params.instance_count:
            pods_list.pop(random.randint(0, len(pods_list) - 1))
        for pod_name in pods_list:
            pod_stat = kubecli.read_pod(pod_name, test_namespace)
            ip_set.add(pod_stat.status.pod_ip)
            node_dict.setdefault(pod_stat.spec.node_name, [])
            node_dict[pod_stat.spec.node_name].append(pod_stat.status.pod_ip)
            for key, value in pod_stat.metadata.labels.items():
                label_set.add("%s=%s" % (key, value))

        check_bridge_interface(
            list(node_dict.keys())[0], pod_module_template, br_name, kubecli
        )

        for mod in mod_lst:
            for node, ips in node_dict.items():
                job_list.extend( apply_net_policy(
                    mod,
                    node,
                    ips,
                    job_template,
                    pod_module_template,
                    params.network_params,
                    params.test_duration,
                    br_name,
                    kubecli,
                    params.execution_type,
                ))
            if params.execution_type == "serial":
                logging.info("Waiting for serial job to finish")
                start_time = int(time.time())
                wait_for_job(job_list[:], kubecli,
                                params.test_duration + 20)
                logging.info("Waiting for wait_duration %s" %
                                params.test_duration)
                time.sleep(params.test_duration)
                end_time = int(time.time())
                if publish:
                    cerberus.publish_kraken_status(
                        config, failed_post_scenarios, start_time, end_time
                    )
            if params.execution_type == "parallel":
                break
        if params.execution_type == "parallel":
            logging.info("Waiting for parallel job to finish")
            start_time = int(time.time())
            wait_for_job(job_list[:], kubecli, params.test_duration + 300)
            logging.info("Waiting for wait_duration %s" % params.test_duration)
            time.sleep(params.test_duration)
            end_time = int(time.time())
            if publish:
                cerberus.publish_kraken_status(
                    config, failed_post_scenarios, start_time, end_time
                )

        return "success", PodEgressNetShapingSuccessOutput(
            test_pods=pods_list,
            network_parameters=params.network_params,
            execution_type=params.execution_type,
        )
    except Exception as e:
        logging.error(
            "Pod network Shaping scenario exiting due to Exception - %s" % e)
        return "error", PodEgressNetShapingErrorOutput(format_exc())
    finally:
        logging.info("Deleting jobs(if any)")
        delete_jobs(kubecli, job_list[:])


@dataclass
class IngressParams:
    """
    This is the data structure for the input parameters of the step defined below.
    """

    namespace: typing.Annotated[str, validation.min(1)] = field(
        metadata={
            "name": "Namespace",
            "description": "Namespace of the pod to which filter need to be applied"
            "for details.",
        }
    )

    network_params: typing.Dict[str, str] = field(
        metadata={
            "name": "Network Parameters",
            "description": "The network filters that are applied on the interface. "
            "The currently supported filters are latency, "
            "loss and bandwidth",
        },
    )

    kubeconfig_path: typing.Optional[str] = field(
        default=None,
        metadata={
            "name": "Kubeconfig path",
            "description": "Kubeconfig file as string\n"
            "See https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/ for "
            "details.",
        },
    )
    pod_name: typing.Annotated[
        typing.Optional[str],
        validation.required_if_not("label_selector"),
    ] = field(
        default=None,
        metadata={
            "name": "Pod name",
            "description": "When label_selector is not specified, pod matching the name will be"
            "selected for the chaos scenario",
        },
    )

    label_selector: typing.Annotated[
        typing.Optional[str], validation.required_if_not("pod_name")
    ] = field(
        default=None,
        metadata={
            "name": "Label selector",
            "description": "Kubernetes label selector for the target pod. "
            "When pod_name is not specified, pod with matching label_selector is selected for chaos scenario",
        },
    )

    kraken_config: typing.Optional[str] = field(
        default=None,
        metadata={
            "name": "Kraken Config",
            "description": "Path to the config file of Kraken. "
            "Set this field if you wish to publish status onto Cerberus",
        },
    )

    test_duration: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=90,
        metadata={
            "name": "Test duration",
            "description": "Duration for which each step of the ingress chaos testing "
            "is to be performed.",
        },
    )

    wait_duration: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=300,
        metadata={
            "name": "Wait Duration",
            "description": "Wait duration for finishing a test and its cleanup."
            "Ensure that it is significantly greater than wait_duration",
        },
    )

    instance_count: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=1,
        metadata={
            "name": "Instance Count",
            "description": "Number of pods to perform action/select that match "
            "the label selector.",
        },
    )

    execution_type: typing.Optional[str] = field(
        default="parallel",
        metadata={
            "name": "Execution Type",
            "description": "The order in which the ingress filters are applied. "
            "Execution type can be 'serial' or 'parallel'",
        },
    )


@dataclass
class PodIngressNetShapingSuccessOutput:
    """
    This is the output data structure for the success case.
    """

    test_pods: typing.List[str] = field(
        metadata={
            "name": "Test pods",
            "description": "List of test pods where the selected for chaos scenario",
        }
    )

    network_parameters: typing.Dict[str, str] = field(
        metadata={
            "name": "Network Parameters",
            "description": "The network filters that are applied on the interfaces",
        }
    )

    execution_type: str = field(
        metadata={
            "name": "Execution Type",
            "description": "The order in which the filters are applied",
        }
    )


@dataclass
class PodIngressNetShapingErrorOutput:
    error: str = field(
        metadata={
            "name": "Error",
            "description": "Error message when there is a run-time error during "
            "the execution of the scenario",
        }
    )


@plugin.step(
    id="pod_ingress_shaping",
    name="Pod ingress network Shaping",
    description="Does ingress network traffic shaping at pod level",
    outputs={
        "success": PodIngressNetShapingSuccessOutput,
        "error": PodIngressNetShapingErrorOutput,
    },
)
def pod_ingress_shaping(
    params: IngressParams,
) -> typing.Tuple[
    str, typing.Union[PodIngressNetShapingSuccessOutput,
                      PodIngressNetShapingErrorOutput]
]:
    """
    Function that performs ingress pod traffic shaping based
    on the provided configuration

    Args:
        params (IngressParams,)
            - The object containing the configuration for the scenario

    Returns
        A 'success' or 'error' message along with their details
    """

    file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
    env = Environment(loader=file_loader)
    job_template = env.get_template("job.j2")
    pod_module_template = env.get_template("pod_module.j2")
    test_namespace = params.namespace
    test_label_selector = params.label_selector
    test_pod_name = params.pod_name
    job_list = []
    publish = False

    if params.kraken_config:
        failed_post_scenarios = ""
        try:
            with open(params.kraken_config, "r") as f:
                config = yaml.full_load(f)
        except Exception:
            logging.error("Error reading Kraken config from %s" %
                          params.kraken_config)
            return "error", PodIngressNetShapingErrorOutput(format_exc())
        publish = True

    try:
        ip_set = set()
        node_dict = {}
        label_set = set()
        param_lst = ["latency", "loss", "bandwidth"]
        mod_lst = [i for i in param_lst if i in params.network_params]

        kubecli = KrknKubernetes(kubeconfig_path=params.kubeconfig_path)
        api_ext = client.ApiextensionsV1Api(kubecli.api_client)
        custom_obj = client.CustomObjectsApi(kubecli.api_client)

        br_name = get_bridge_name(api_ext, custom_obj)
        pods_list = get_test_pods(
            test_pod_name, test_label_selector, test_namespace, kubecli
        )

        while not len(pods_list) <= params.instance_count:
            pods_list.pop(random.randint(0, len(pods_list) - 1))
        for pod_name in pods_list:
            pod_stat = kubecli.read_pod(pod_name, test_namespace)
            ip_set.add(pod_stat.status.pod_ip)
            node_dict.setdefault(pod_stat.spec.node_name, [])
            node_dict[pod_stat.spec.node_name].append(pod_stat.status.pod_ip)
            for key, value in pod_stat.metadata.labels.items():
                label_set.add("%s=%s" % (key, value))

        check_bridge_interface(
            list(node_dict.keys())[0], pod_module_template, br_name, kubecli
        )

        for mod in mod_lst:
            for node, ips in node_dict.items():
                job_list.extend(apply_ingress_policy(
                    mod,
                    node,
                    ips,
                    job_template,
                    pod_module_template,
                    params.network_params,
                    params.test_duration,
                    br_name,
                    kubecli,
                    params.execution_type,
                ))
            if params.execution_type == "serial":
                logging.info("Waiting for serial job to finish")
                start_time = int(time.time())
                wait_for_job(job_list[:], kubecli,
                             params.test_duration + 20)
                logging.info("Waiting for wait_duration %s" %
                             params.test_duration)
                time.sleep(params.test_duration)
                end_time = int(time.time())
                if publish:
                    cerberus.publish_kraken_status(
                        config, failed_post_scenarios, start_time, end_time
                    )
            if params.execution_type == "parallel":
                break
        if params.execution_type == "parallel":
            logging.info("Waiting for parallel job to finish")
            start_time = int(time.time())
            wait_for_job(job_list[:], kubecli, params.test_duration + 300)
            logging.info("Waiting for wait_duration %s" % params.test_duration)
            time.sleep(params.test_duration)
            end_time = int(time.time())
            if publish:
                cerberus.publish_kraken_status(
                    config, failed_post_scenarios, start_time, end_time
                )

        return "success", PodIngressNetShapingSuccessOutput(
            test_pods=pods_list,
            network_parameters=params.network_params,
            execution_type=params.execution_type,
        )
    except Exception as e:
        logging.error(
            "Pod network Shaping scenario exiting due to Exception - %s" % e)
        return "error", PodIngressNetShapingErrorOutput(format_exc())
    finally:
        delete_virtual_interfaces(
            kubecli,
            node_dict.keys(),
            pod_module_template
        )
        logging.info("Deleting jobs(if any)")
        delete_jobs(kubecli, job_list[:])
