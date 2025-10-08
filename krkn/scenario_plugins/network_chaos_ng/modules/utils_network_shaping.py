import logging
import re
import time
import random
from typing import Optional

import jinja2
import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.utils import get_random_string
from kubernetes.client import ApiextensionsV1Api, CustomObjectsApi

from krkn.scenario_plugins.network_chaos_ng.modules.utils import taints_to_tolerations


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

        namespace (string)
            - namespace in which the pod is present

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

    Returns:
        pod names (string) in the namespace
    """
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
    node_name: str,
    pod_template,
    bridge_name: str,
    kubecli: KrknKubernetes,
    workload_image: str,
    taints: list[str],
    service_account: str,
) -> bool:
    """
    Function  is used to check if the required OVS or OVN bridge is found
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

        workload_image (string)
            - the workload image deployed to perform the scenario
        taints (list[str])
            - scenario workload taints
        service_account (str)
            - scenario workload service account

    Returns:
        Returns True if the bridge is found in the  node.
    """
    nodes = kubecli.get_node(node_name, "", 1)
    node_bridge = []
    for node in nodes:
        node_bridge = list_bridges(
            node, pod_template, kubecli, workload_image, taints, service_account
        )
    if bridge_name not in node_bridge:
        raise Exception(f"OVS bridge {bridge_name} not found on the node ")

    return True


def list_bridges(
    node: str,
    pod_template,
    kubecli: KrknKubernetes,
    workload_image: str,
    taints: list[str],
    service_account: str,
) -> Optional[list[str]]:
    """
    Function that returns a list of bridges on the node

    Args:
        node (string)
            - Node from which the list of bridges is to be returned

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interface

        workload_image (string)
            - the workload image deployed to perform the scenario
        taints (list[str])
            - scenario workload taints
        service_account (str)
            - scenario workload service account

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

    Returns:
        List of bridges on the node.
    """
    tolerations = taints_to_tolerations(taints)
    pod_name = f"krkn-tools-{get_random_string(5)}"
    pod_body = yaml.safe_load(
        pod_template.render(
            pod_name=pod_name,
            nodename=node,
            workload_image=workload_image,
            taints=tolerations,
            service_account=service_account,
        )
    )
    logging.info("Creating pod to query bridge on node %s" % node)
    kubecli.create_pod(pod_body, "default", 300)
    bridges: list[str] = []
    try:

        cmd = ["/host", "ovs-vsctl", "list-br"]
        output = kubecli.exec_cmd_in_pod(
            cmd, pod_name, "default", base_command="chroot"
        )

        if not output:
            raise Exception(f"Exception occurred while executing command {cmd} in pod")

        bridges.extend(output.split("\n"))

    except Exception as e:
        raise e
    finally:
        logging.info("Deleting pod to query interface on node")
        kubecli.delete_pod(pod_name, "default")
    return bridges


def apply_outage_policy(
    node_dict: dict[str, str],
    ports: list[str],
    job_template,
    pod_template,
    direction: str,
    duration: int,
    bridge_name: str,
    kubecli: KrknKubernetes,
    workload_image: str,
    taints: list[str],
    service_account: str,
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
            - ingress/egress

        duration (int)
            - Duration for which the traffic control is to be done

        bridge_name (string):
            - bridge to which  filter rules need to be applied
        kubecli (KrknKubernetes)
            - Krkn Kubernetes library
        workload_image (str):
            - workload container image
        taints (list[str])
            - scenario workload taints
        service_account (str)
            - scenario workload service account

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
        check = check_cookie(
            node,
            pod_template,
            br,
            f"{cookie}",
            kubecli,
            workload_image,
            taints,
            service_account,
        )
        while len(check) > 2 or cookie in cookie_list:
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
        tolerations = taints_to_tolerations(taints)
        job_body = yaml.safe_load(
            job_template.render(
                jobname=str(hash(node))[:5] + str(random.randint(0, 10000)),
                nodename=node,
                cmd=exec_cmd,
                workload_image=workload_image,
                taints=tolerations,
                service_account=service_account,
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
    node: str,
    pod_template: jinja2.environment.Template,
    br_name: str,
    cookie: str,
    kubecli: KrknKubernetes,
    workload_image: str,
    taints: list[str],
    service_account: str,
) -> Optional[list[str]]:
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

        kubecli (KrknKubernetes)
            - Krkn Kubernetes library
        workload_image (str):
            - workload container image
        taints (list[str])
            - scenario workload taints
        service_account (str)
            - scenario workload service account

    """
    tolerations = taints_to_tolerations(taints)
    pod_name=f"krkn-tools-{get_random_string(5)}"
    pod_body = yaml.safe_load(
        pod_template.render(
            pod_name=pod_name,
            nodename=node,
            workload_image=workload_image,
            taints=tolerations,
            service_account=service_account,
        )
    )
    logging.info("Creating pod to query duplicate rules on node %s" % node)
    kubecli.create_pod(pod_body, "default", 300)
    flow_list: list[str] = []
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
            cmd, pod_name, "default", base_command="chroot"
        )

        if not output:
            raise Exception(f"Exception occurred while executing command {cmd} in pod")

        flow_list.extend(output.split("\n"))

    finally:
        logging.info("Deleting pod to query interface on node")
        kubecli.delete_pod(pod_name, "default")

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

    controller_uid = api_response.metadata.labels["controller-uid"]
    pod_label_selector = "controller-uid=" + controller_uid
    pods_list = kubecli.list_pods(
        label_selector=pod_label_selector, namespace="default"
    )

    return pods_list[0]


def apply_net_policy(
    mod: str,
    node: str,
    ips: list[str],
    job_template,
    pod_template,
    network_params: dict[str, str],
    duration: int,
    bridge_name: str,
    kubecli: KrknKubernetes,
    test_execution: str,
    workload_image: str,
    taints: list[str],
    service_account: str,
) -> list[str]:
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
        workload_image (str):
            - workload container image
        taints (list[str])
            - scenario workload taints
        service_account (str)
            - scenario workload service account


    Returns:
        The name of the job created that executes the traffic shaping
        filter
    """

    job_list = []
    yml_list = []

    for pod_ip in set(ips):
        pod_inf = get_pod_interface(
            node,
            pod_ip,
            pod_template,
            bridge_name,
            kubecli,
            workload_image,
            taints,
            service_account,
        )
        exec_cmd = get_egress_cmd(
            test_execution, pod_inf, mod, network_params, duration
        )
        logging.info("Executing %s on pod %s in node %s" % (exec_cmd, pod_ip, node))
        tolerations = taints_to_tolerations(taints)
        job_body = yaml.safe_load(
            job_template.render(
                jobname=mod + str(pod_ip),
                nodename=node,
                cmd=exec_cmd,
                workload_image=workload_image,
                taints=tolerations,
                service_account=service_account,
            )
        )
        yml_list.append(job_body)

    for job_body in yml_list:
        api_response = kubecli.create_job(job_body)
        if api_response is None:
            raise Exception("Error creating job")

        job_list.append(job_body["metadata"]["name"])
    return job_list


def get_pod_interface(
    node: str,
    ip: str,
    pod_template,
    br_name,
    kubecli: KrknKubernetes,
    workload_image: str,
    taints: list[str],
    service_account: str,
) -> Optional[str]:
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
        workload_image (str)
            - scenario workload_image
        taints (List[str])
            - workload taints
        service_account (str)
            - workload service account


        Returns the pod interface name
    """

    tolerations = taints_to_tolerations(taints)
    pod_name=f"krkn-tools-{get_random_string(5)}"
    pod_body = yaml.safe_load(
        pod_template.render(
            pod_name=pod_name,
            nodename=node,
            workload_image=workload_image,
            taints=tolerations,
            service_account=service_account,
        )
    )
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
            cmd, pod_name, "default", base_command="chroot"
        )
        if not output:
            cmd = ["/host", "ip", "addr", "show"]
            output = kubecli.exec_cmd_in_pod(
                cmd, pod_name, "default", base_command="chroot"
            )
            for if_str in output.split("\n"):
                if re.search(ip, if_str):
                    inf = if_str.split(" ")[-1]
        else:
            inf = output
    finally:
        logging.info("Deleting pod to query interface on node")
        kubecli.delete_pod(pod_name, "default")
    return inf


def get_egress_cmd(
    execution: str,
    test_interface: str,
    mod: str,
    vallst: dict[str, str],
    duration: int,
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
    tc_set = "{0} tc qdisc replace dev {1} root netem".format(tc_set, test_interface)
    tc_unset = "{0} tc qdisc del dev {1} root ;".format(tc_unset, test_interface)
    tc_ls = "{0} tc qdisc ls dev {1} ;".format(tc_ls, test_interface)
    if execution == "parallel":
        for val in vallst.keys():
            tc_set += " {0} {1} ".format(param_map[val], vallst[val])
        tc_set += ";"
    else:
        tc_set += " {0} {1} ;".format(param_map[mod], vallst[mod])
    exec_cmd = "sleep 30;{0} {1} sleep {2};{3}".format(
        tc_set, tc_ls, duration, tc_unset
    )

    return exec_cmd


def apply_ingress_policy(
    mod: str,
    node: str,
    ips: list[str],
    job_template,
    pod_template,
    network_params: dict[str, str],
    duration: int,
    bridge_name: str,
    kubecli: KrknKubernetes,
    test_execution: str,
    workload_image: str,
    taints: list[str],
    service_account: str,
) -> list[str]:
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
        workload_image (str)
            - scenario workload image
        taints (list[str])
            - scenario workload taints
        service_account (str)
            - scenario workload service account

    Returns:
        The name of the job created that executes the traffic shaping
        filter
    """

    job_list = []
    yml_list = []

    create_virtual_interfaces(
        kubecli, len(ips), node, pod_template, workload_image, taints, service_account
    )

    for count, pod_ip in enumerate(set(ips)):
        pod_inf = get_pod_interface(
            node,
            pod_ip,
            pod_template,
            bridge_name,
            kubecli,
            workload_image,
            taints,
            service_account,
        )
        exec_cmd = get_ingress_cmd(
            test_execution, pod_inf, mod, count, network_params, duration
        )
        logging.info("Executing %s on pod %s in node %s" % (exec_cmd, pod_ip, node))
        tolerations = taints_to_tolerations(taints)
        job_body = yaml.safe_load(
            job_template.render(
                jobname=f"{mod}-{str(pod_ip)}-{get_random_string(5)}",
                nodename=node,
                cmd=exec_cmd,
                workload_image=workload_image,
                taints=tolerations,
                service_account=service_account,
            )
        )
        yml_list.append(job_body)
        if pod_ip == node:
            break

    for job_body in yml_list:
        api_response = kubecli.create_job(job_body)
        if api_response is None:
            raise Exception("Error creating job")

        job_list.append(job_body["metadata"]["name"])
    return job_list


def create_virtual_interfaces(
    kubecli: KrknKubernetes,
    number: int,
    node: str,
    pod_template,
    workload_image: str,
    taints: list[str],
    service_account: str,
) -> None:
    """
    Function that creates a privileged pod and uses it to create
    virtual interfaces on the node

    Args:
        kubecli (KrknKubernetes)
            - Krkn Kubernetes library
        number (int)
            - number of interfaces created
        node (string)
            - The node on which the virtual interfaces are created

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to create
              virtual interfaces on the node
        workload_image (str)
            - scenario workload image
        taints (list[str])
            - scenario workload taints
        service_account (str)
            - scenario workload service account

    """
    tolerations = taints_to_tolerations(taints)
    pod_name = f"krkn-tools-{get_random_string(5)}"
    pod_body = yaml.safe_load(
        pod_template.render(
            pod_name=pod_name,
            nodename=node,
            workload_image=workload_image,
            taints=tolerations,
            service_account=service_account,
        )
    )
    kubecli.create_pod(pod_body, "default", 300)
    logging.info(
        "Creating {0} virtual interfaces on node {1} using a pod".format(number, node)
    )
    create_ifb(kubecli, number, pod_name)
    logging.info("Deleting pod used to create virtual interfaces")
    kubecli.delete_pod(pod_name, "default")


def create_ifb(kubecli: KrknKubernetes, number: int, pod_name: str):
    """
    Function that creates virtual interfaces in a pod.
    Makes use of modprobe commands
    """

    exec_command = ["/host", "modprobe", "ifb", "numifbs=" + str(number)]
    kubecli.exec_cmd_in_pod(exec_command, pod_name, "default", base_command="chroot")

    for i in range(0, number):
        exec_command = ["/host", "ip", "link", "set", "dev"]
        exec_command += ["ifb" + str(i), "up"]
        kubecli.exec_cmd_in_pod(
            exec_command, pod_name, "default", base_command="chroot"
        )


def get_ingress_cmd(
    execution: str,
    test_interface: str,
    mod: str,
    count: int,
    vallst: dict[str, str],
    duration: int,
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
    ifb_dev = "ifb{0}".format(count)
    tc_unset = tc_ls = ""
    param_map = {"latency": "delay", "loss": "loss", "bandwidth": "rate"}
    tc_set = "tc qdisc add dev {0} ingress ;".format(test_interface)
    tc_set = "{0} tc filter add dev {1} ingress matchall action mirred egress redirect dev {2} ;".format(
        tc_set, test_interface, ifb_dev
    )
    tc_set = "{0} tc qdisc replace dev {1} root netem".format(tc_set, ifb_dev)
    tc_unset = "{0} tc qdisc del dev {1} root ;".format(tc_unset, ifb_dev)
    tc_unset = "{0} tc qdisc del dev {1} ingress".format(tc_unset, test_interface)
    tc_ls = "{0} tc qdisc ls dev {1} ;".format(tc_ls, ifb_dev)
    if execution == "parallel":
        for val in vallst.keys():
            tc_set += " {0} {1} ".format(param_map[val], vallst[val])
        tc_set += ";"
    else:
        tc_set += " {0} {1} ;".format(param_map[mod], vallst[mod])
    exec_cmd = "sleep 30;{0} {1} sleep {2};{3}".format(
        tc_set, tc_ls, duration, tc_unset
    )

    return exec_cmd


def delete_virtual_interfaces(
    kubecli: KrknKubernetes,
    node_list: list[str],
    pod_template,
    workload_image: str,
    taints: list[str],
    service_account: str,
):
    """
    Function that creates a privileged pod and uses it to delete all
    virtual interfaces on the specified nodes

    Args:
        kubecli (KrknKubernetes)
            - Krkn Kubernetes library
        node_list (List of strings)
            - The list of nodes on which the list of virtual interfaces are
              to be deleted
        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to delete
              virtual interfaces on the node
        workload_image (str)
            - the workload image used to perform the scenario
        taints (list[str])
            - scenario workload taints
        service_account (str)
            - scenario workload service account
    """

    tolerations = taints_to_tolerations(taints)
    for node in node_list:
        pod_name = f"krkn-tools-{get_random_string(5)}"
        pod_body = yaml.safe_load(
            pod_template.render(
                pod_name=pod_name,
                nodename=node,
                workload_image=workload_image,
                taints=tolerations,
                service_account=service_account,
            )
        )
        kubecli.create_pod(pod_body, "default", 300)
        logging.info("Deleting all virtual interfaces on node {0}".format(node))
        delete_ifb(kubecli, pod_name)
        kubecli.delete_pod(pod_name, "default")


def delete_ifb(kubecli: KrknKubernetes, pod_name: str):
    """
    Function that deletes all virtual interfaces in a pod.
    Makes use of modprobe command
    """

    exec_command = ["/host", "modprobe", "-r", "ifb"]
    kubecli.exec_cmd_in_pod(exec_command, pod_name, "default", base_command="chroot")
