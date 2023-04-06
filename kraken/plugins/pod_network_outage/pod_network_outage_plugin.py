#!/usr/bin/env python3
import sys
import os
import typing
import yaml
import logging
import time
import random
from dataclasses import dataclass, field
from traceback import format_exc
from jinja2 import Environment, FileSystemLoader
from arcaflow_plugin_sdk import plugin, validation
from kubernetes import client
from kubernetes.client.api.core_v1_api import CoreV1Api
from kubernetes.client.api.batch_v1_api import BatchV1Api
from kubernetes.client.api.apiextensions_v1_api import ApiextensionsV1Api
from kubernetes.client.api.custom_objects_api import CustomObjectsApi
from . import kubernetes_functions as kube_helper
from . import cerberus


def get_test_pods(
    pod_name: str,
    pod_label: str,
    namespace: str,
    cli: CoreV1Api
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

        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

    Returns:
        pod names (string) in the namespace
    """
    pods_list = []
    pods_list = kube_helper.list_pods(
        cli,
        label_selector=pod_label,
        namespace=namespace
    )
    if pod_name and pod_name not in pods_list:
        raise Exception(
            "pod name not found in namespace "
        )
    elif pod_name and pod_name in pods_list:
        pods_list.clear()
        pods_list.append(pod_name)
        return pods_list
    else:
        return pods_list


def get_job_pods(cli: CoreV1Api, api_response):
    """
    Function that gets the pod corresponding to the job

    Args:
        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

        api_response
            - The API response for the job status

    Returns
        Pod corresponding to the job
    """

    controllerUid = api_response.metadata.labels["controller-uid"]
    pod_label_selector = "controller-uid=" + controllerUid
    pods_list = kube_helper.list_pods(
        cli,
        label_selector=pod_label_selector,
        namespace="default"
    )

    return pods_list[0]


def delete_jobs(
    cli: CoreV1Api,
    batch_cli: BatchV1Api,
    job_list: typing.List[str]
):
    """
    Function that deletes jobs

    Args:
        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

        batch_cli (BatchV1Api)
            - Object to interact with Kubernetes Python client's BatchV1 API

        job_list (List of strings)
            - The list of jobs to delete
    """

    for job_name in job_list:
        try:
            api_response = kube_helper.get_job_status(
                batch_cli,
                job_name,
                namespace="default"
            )
            if api_response.status.failed is not None:
                pod_name = get_job_pods(cli, api_response)
                pod_stat = kube_helper.read_pod(
                    cli,
                    name=pod_name,
                    namespace="default"
                )
                logging.error(pod_stat.status.container_statuses)
                pod_log_response = kube_helper.get_pod_log(
                    cli,
                    name=pod_name,
                    namespace="default"
                )
                pod_log = pod_log_response.data.decode("utf-8")
                logging.error(pod_log)
        except Exception as e:
            logging.warn("Exception in getting job status: %s" % str(e))
        api_response = kube_helper.delete_job(
            batch_cli,
            name=job_name,
            namespace="default"
        )


def wait_for_job(
    batch_cli: BatchV1Api,
    job_list: typing.List[str],
    timeout: int = 300
) -> None:
    """
    Function that waits for a list of jobs to finish within a time period

    Args:
        batch_cli (BatchV1Api)
            - Object to interact with Kubernetes Python client's BatchV1 API

        job_list (List of strings)
            - The list of jobs to check for completion

        timeout (int)
            - Max duration to wait for checking whether the jobs are completed
    """

    wait_time = time.time() + timeout
    count = 0
    job_len = len(job_list)
    while count != job_len:
        for job_name in job_list:
            try:
                api_response = kube_helper.get_job_status(
                    batch_cli,
                    job_name,
                    namespace="default"
                )
                if (
                    api_response.status.succeeded is not None or
                    api_response.status.failed is not None
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


def get_bridge_name(
    cli: ApiextensionsV1Api,
    custom_obj: CustomObjectsApi
) -> str:
    """
    Function that gets the pod corresponding to the job

    Args:
        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

        api_response
            - The API response for the job status

    Returns
        Pod corresponding to the job
    """

    current_crds = [x['metadata']['name'].lower()
                    for x in cli.list_custom_resource_definition().to_dict()['items']]
    if 'networks.config.openshift.io' not in current_crds:
        raise Exception(
            "OpenShiftSDN or OVNKubernetes not found in cluster "
        )
    else:
        resource = custom_obj.get_cluster_custom_object(
            group="config.openshift.io", version="v1", name="cluster", plural="networks")
        network_type = resource["spec"]["networkType"]
        if network_type == 'OpenShiftSDN':
            bridge = 'br0'
        elif network_type == 'OVNKubernetes':
            bridge = 'br-int'
        else:
            raise Exception(
                f'OpenShiftSDN or OVNKubernetes not found in cluster {network_type}'
            )
    return bridge


def apply_net_policy(
    node_dict: typing.Dict[str, str],
    ports: typing.List[str],
    job_template,
    pod_template,
    direction: str,
    duration: str,
    bridge_name: str,
    cli: CoreV1Api,
    batch_cli: BatchV1Api
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
    net_direction = {'egress': 'nw_src', 'ingress': 'nw_dst'}
    br = 'br0'
    table = 0
    if bridge_name == 'br-int':
        br = 'br-int'
        table = 8
    for node, ips in node_dict.items():
        while len(check_cookie(node, pod_template, br, cookie, cli)) > 2:
            cookie = random.randint(100, 10000)
        exec_cmd = ''
        for ip in ips:
            for port in ports:
                target_port = port
                exec_cmd = f'{exec_cmd}ovs-ofctl -O  OpenFlow13 add-flow {br} cookie={cookie},table={table},priority=65535,tcp,{net_direction[direction]}={ip},tp_dst={target_port},actions=drop;'
                exec_cmd = f'{exec_cmd}ovs-ofctl -O  OpenFlow13 add-flow {br} cookie={cookie},table={table},priority=65535,udp,{net_direction[direction]}={ip},tp_dst={target_port},actions=drop;'
            if not ports:
                exec_cmd = f'{exec_cmd}ovs-ofctl -O  OpenFlow13 add-flow {br} cookie={cookie},table={table},priority=65535,ip,{net_direction[direction]}={ip},actions=drop;'
        exec_cmd = f'{exec_cmd}sleep {duration};ovs-ofctl -O  OpenFlow13  del-flows {br} cookie={cookie}/-1'
        logging.info("Executing %s on node %s" % (exec_cmd, node))
        job_body = yaml.safe_load(
            job_template.render(
                jobname=str(hash(node))[:5] + str(random.randint(0, 10000)),
                nodename=node,
                cmd=exec_cmd
            )
        )
        api_response = kube_helper.create_job(batch_cli, job_body)
        if api_response is None:
            raise Exception("Error creating job")

        job_list.append(job_body["metadata"]["name"])
    return job_list


def list_bridges(
    node: str,
    pod_template,
    cli: CoreV1Api
) -> typing.List[str]:
    """
    Function that returns a list of bridges on the node

    Args:
        node (string)
            - Node from which the list of bridges is to be returned

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interface

        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

    Returns:
        List of bridges on the node.
    """

    pod_body = yaml.safe_load(pod_template.render(nodename=node))
    logging.info("Creating pod to query bridge on node %s" % node)
    kube_helper.create_pod(cli, pod_body, "default", 300)

    try:
        cmd = ["chroot", "/host", "ovs-vsctl", "list-br"]
        output = kube_helper.exec_cmd_in_pod(cli, cmd, "modtools", "default")

        if not output:
            logging.error("Exception occurred while executing command in pod")
            sys.exit(1)

        bridges = output.split('\n')

    finally:
        logging.info("Deleting pod to query interface on node")
        kube_helper.delete_pod(cli, "modtools", "default")

    return bridges


def check_cookie(
    node: str,
    pod_template,
    br_name,
    cookie,
    cli: CoreV1Api
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
            - flows matching the cookie are listed

        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

    Returns
        Returns the matching flow rules
    """

    pod_body = yaml.safe_load(pod_template.render(nodename=node))
    logging.info("Creating pod to query duplicate rules on node %s" % node)
    kube_helper.create_pod(cli, pod_body, "default", 300)

    try:
        cmd = ["chroot", "/host", "ovs-ofctl", "-O", "OpenFlow13",
               "dump-flows", br_name, f'cookie={cookie}/-1']
        output = kube_helper.exec_cmd_in_pod(cli, cmd, "modtools", "default")

        if not output:
            logging.error("Exception occurred while executing command in pod")
            sys.exit(1)

        flow_list = output.split('\n')

    finally:
        logging.info("Deleting pod to query interface on node")
        kube_helper.delete_pod(cli, "modtools", "default")

    return flow_list


def check_bridge_interface(
    node_name: str,
    pod_template,
    bridge_name: str,
    cli: CoreV1Api
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

        cli (CoreV1Api)
            - Object to interact with Kubernetes Python client's CoreV1 API

    Returns:
        Returns True if the bridge is found in the  node.
    """
    nodes = kube_helper.get_node(node_name, None, 1, cli)
    node_bridge = []
    for node in nodes:
        node_bridge = list_bridges(
            node,
            pod_template,
            cli
        )
    if bridge_name not in node_bridge:
        raise Exception(
            f'OVS bridge {bridge_name} not found on the node '
        )

    return True


@dataclass
class InputParams:
    """
    This is the data structure for the input parameters of the step defined below.
    """
    namespace: typing.Annotated[str, validation.min(1)] = field(
        metadata={
            "name": "Namespace",
            "description":
                "Namespace of the pod to which filter need to be applied"
                "for details."
        }
    )

    direction: typing.List[str] = field(
        default_factory=lambda: ['ingress', 'egress'],
        metadata={
            "name": "Direction",
            "description":
                "List of directions to apply filters"
                "Default both egress and ingress."
        }
    )

    ingress_ports: typing.List[int] = field(
        default_factory=list,
        metadata={
            "name": "Ingress ports",
            "description":
                "List of ports to block traffic on"
                "Default [], i.e. all ports"
        }
    )

    egress_ports: typing.List[int] = field(
        default_factory=list,
        metadata={
            "name": "Egress ports",
            "description":
                "List of ports to block traffic on"
                "Default [], i.e. all ports"
        }
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
        typing.Optional[str], validation.required_if_not("label_selector"),
    ] = field(
        default=None,
        metadata={
            "name": "Pod name",
            "description":
                "When label_selector is not specified, pod matching the name will be"
                "selected for the chaos scenario"
        }
    )

    label_selector: typing.Annotated[
        typing.Optional[str], validation.required_if_not("pod_name")
    ] = field(
        default=None,
        metadata={
            "name": "Label selector",
            "description":
                "Kubernetes label selector for the target pod. "
                "When pod_name is not specified, pod with matching label_selector is selected for chaos scenario"
        }
    )

    kraken_config: typing.Optional[str] = field(
        default=None,
        metadata={
            "name": "Kraken Config",
            "description":
                "Path to the config file of Kraken. "
                "Set this field if you wish to publish status onto Cerberus"
        }
    )

    test_duration: typing.Annotated[
        typing.Optional[int],
        validation.min(1)
    ] = field(
        default=120,
        metadata={
            "name": "Test duration",
            "description":
                "Duration for which each step of the ingress chaos testing "
                "is to be performed.",
        },
    )

    wait_duration: typing.Annotated[
        typing.Optional[int],
        validation.min(1)
    ] = field(
        default=300,
        metadata={
            "name": "Wait Duration",
            "description":
                "Wait duration for finishing a test and its cleanup."
                "Ensure that it is significantly greater than wait_duration"
        }
    )

    instance_count: typing.Annotated[
        typing.Optional[int],
        validation.min(1)
    ] = field(
        default=1,
        metadata={
            "name": "Instance Count",
            "description":
                "Number of pods to perform action/select that match "
                "the label selector.",
        }
    )


@dataclass
class PodOutageSuccessOutput:
    """
    This is the output data structure for the success case.
    """

    test_pods: typing.List[str] = field(
        metadata={
            "name": "Test pods",
            "description":
                "List of test pods where the selected for chaos scenario"
        }
    )

    direction: typing.List[str] = field(
        metadata={
            "name": "Direction",
            "description":
                "List of directions to which the filters were applied."
        }
    )

    ingress_ports: typing.List[int] = field(
        metadata={
            "name": "Ingress ports",
            "description":
                "List of ports to block traffic on"
        }
    )

    egress_ports: typing.List[int] = field(
        metadata={
            "name": "Egress ports",
            "description": "List of ports to block traffic on"
        }
    )


@dataclass
class PodOutageErrorOutput:
    error: str = field(
        metadata={
            "name": "Error",
            "description":
                "Error message when there is a run-time error during "
                "the execution of the scenario"
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
    on the provided configuration

    Args:
        params (InputParams,)
            - The object containing the configuration for the scenario

    Returns
        A 'success' or 'error' message along with their details
    """
    direction = ['ingress', 'egress']
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
            logging.error(
                "Error reading Kraken config from %s" % params.kraken_config
            )
            return "error", PodOutageErrorOutput(
                format_exc()
            )
        publish = True

    for i in params.direction:
        filter_dict[i] = eval(f"params.{i}_ports")
    try:
        ip_set = set()
        node_dict = {}
        label_set = set()

        api = kube_helper.setup_kubernetes(params.kubeconfig_path)
        cli = client.CoreV1Api(api)
        batch_cli = client.BatchV1Api(api)
        api_ext = client.ApiextensionsV1Api(api)
        custom_obj = client.CustomObjectsApi(api)

        br_name = get_bridge_name(api_ext, custom_obj)
        pods_list = get_test_pods(
            test_pod_name, test_label_selector, test_namespace, cli)

        while not len(pods_list) <= params.instance_count:
            pods_list.pop(random.randint(0, len(pods_list) - 1))

        for pod_name in pods_list:
            pod_stat = kube_helper.read_pod(cli, pod_name, test_namespace)
            ip_set.add(pod_stat.status.pod_ip)
            node_dict.setdefault(pod_stat.spec.node_name, [])
            node_dict[pod_stat.spec.node_name].append(pod_stat.status.pod_ip)
            for key, value in pod_stat.metadata.labels.items():
                label_set.add("%s=%s" % (key, value))

        check_bridge_interface(list(node_dict.keys())[
                               0], pod_module_template, br_name, cli)

        for direction, ports in filter_dict.items():
            job_list.extend(apply_net_policy(node_dict, ports, job_template, pod_module_template,
                                             direction, params.test_duration, br_name, cli, batch_cli))

        start_time = int(time.time())
        logging.info("Waiting for job to finish")
        wait_for_job(batch_cli, job_list[:], params.wait_duration + 20)
        end_time = int(time.time())
        if publish:
            cerberus.publish_kraken_status(
                config,
                failed_post_scenarios,
                start_time,
                end_time
            )

        return "success", PodOutageSuccessOutput(
            test_pods=pods_list,
            direction=params.direction,
            ingress_ports=params.ingress_ports,
            egress_ports=params.egress_ports
        )
    except Exception as e:
        logging.error("Pod network outage scenario exiting due to Exception - %s" % e)
        return "error", PodOutageErrorOutput(
            format_exc()
        )
    finally:
        logging.info("Deleting jobs(if any)")
        delete_jobs(cli, batch_cli, job_list[:])
