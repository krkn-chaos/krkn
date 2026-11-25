# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from dataclasses import dataclass, field
import yaml
import logging
import time
import sys
import os
import re
import random
from traceback import format_exc
from jinja2 import Environment, FileSystemLoader
from krkn_lib.k8s import KrknKubernetes
import typing
from arcaflow_plugin_sdk import validation, plugin


@dataclass
class NetworkScenarioConfig:

    node_interface_name: typing.Dict[str, typing.List[str]] = field(
        default=None,
        metadata={
            "name": "Node Interface Name",
            "description": "Dictionary with node names as key and values as a list of "
            "their test interfaces. "
            "Required if label_selector is not set.",
        },
    )

    image: typing.Annotated[str, validation.min(1)]= field(
        default="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools",
        metadata={
            "name": "Image",
            "description": "Image of krkn tools to run"
        }
    )

    label_selector: typing.Annotated[
        typing.Optional[str], validation.required_if_not("node_interface_name")
    ] = field(
        default=None,
        metadata={
            "name": "Label selector",
            "description": "Kubernetes label selector for the target nodes. "
            "Required if node_interface_name is not set.\n"
            "See https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/ "  # noqa
            "for details.",
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
        default=30,
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
            "description": "Number of nodes to perform action/select that match "
            "the label selector.",
        },
    )

    kubeconfig_path: typing.Optional[str] = field(
        default=None,
        metadata={
            "name": "Kubeconfig path",
            "description": "Path to your Kubeconfig file. Defaults to ~/.kube/config.\n"
            "See https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/ "  # noqa
            "for details.",
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

    network_params: typing.Dict[str, str] = field(
        default=None,
        metadata={
            "name": "Network Parameters",
            "description":
                "The network filters that are applied on the interface. "
                "The currently supported filters are latency, "
                "loss and bandwidth"
        }
    )

@dataclass
class NetworkScenarioSuccessOutput:
    filter_direction: str = field(
        metadata={
            "name": "Filter Direction",
            "description": "Direction in which the traffic control filters are applied "
            "on the test interfaces",
        }
    )

    test_interfaces: typing.Dict[str, typing.List[str]] = field(
        metadata={
            "name": "Test Interfaces",
            "description": "Dictionary of nodes and their interfaces on which "
            "the chaos experiment was performed",
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
class NetworkScenarioErrorOutput:
    error: str = field(
        metadata={
            "name": "Error",
            "description": "Error message when there is a run-time error during "
            "the execution of the scenario",
        }
    )


def get_default_interface(node: str, pod_template, kubecli: KrknKubernetes, image: str) -> str:
    """
    Function that returns a random interface from a node

    Args:
        node (string)
            - Node from which the interface is to be returned

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interface

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

    Returns:
        Default interface (string) belonging to the node
    """
    pod_name_regex = str(random.randint(0, 10000))
    pod_body = yaml.safe_load(pod_template.render(regex_name=pod_name_regex, nodename=node, image=image))
    logging.info("Creating pod to query interface on node %s" % node)
    kubecli.create_pod(pod_body, "default", 300)
    pod_name = f"fedtools-{pod_name_regex}"
    try:
        cmd = ["ip r"]
        output = kubecli.exec_cmd_in_pod(cmd, pod_name, "default")

        if not output:
            logging.error("Exception occurred while executing command in pod")
            sys.exit(1)

        routes = output.split("\n")
        for route in routes:
            if "default" in route:
                default_route = route
                break

        interfaces = [default_route.split()[4]]

    finally:
        logging.info("Deleting pod to query interface on node")
        kubecli.delete_pod(pod_name, "default")

    return interfaces


def verify_interface(
    input_interface_list: typing.List[str], node: str, pod_template, kubecli: KrknKubernetes, image: str
) -> typing.List[str]:
    """
    Function that verifies whether a list of interfaces is present in the node.
    If the list is empty, it fetches the interface of the default route

    Args:
        input_interface_list (List of strings)
            - The interfaces to be checked on the node

        node (string):
            - Node on which input_interface_list is to be verified

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interfaces

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

    Returns:
        The interface list for the node
    """
    pod_name_regex = str(random.randint(0, 10000))
    pod_body = yaml.safe_load(pod_template.render(regex_name=pod_name_regex, nodename=node, image=image))
    logging.info("Creating pod to query interface on node %s" % node)
    kubecli.create_pod(pod_body, "default", 300)
    pod_name = f"fedtools-{pod_name_regex}"
    try:
        if input_interface_list == []:
            cmd = ["ip r"]
            output = kubecli.exec_cmd_in_pod(cmd, pod_name, "default")

            if not output:
                logging.error("Exception occurred while executing command in pod")
                sys.exit(1)

            routes = output.split("\n")
            for route in routes:
                if "default" in route:
                    default_route = route
                    break

            input_interface_list = [default_route.split()[4]]

        else:
            cmd = ["ip -br addr show"]
            output = kubecli.exec_cmd_in_pod(cmd, pod_name, "default")

            if not output:
                logging.error("Exception occurred while executing command in pod")
                sys.exit(1)

            # Keep accepting the textual form previously used by this check,
            # which can include peer-index annotations such as eth0@if15.
            displayed_interfaces = {
                line.split()[0] for line in output.splitlines() if line.split()
            }

            missing_interfaces = set(input_interface_list) - displayed_interfaces
            actual_interfaces = set()
            if missing_interfaces:
                # Brief output may annotate a peer link as eth0@if15 although
                # its actual ifname is eth0. Read exact names from sysfs:
                # this also preserves real ifnames containing '@' and avoids
                # depending on the workload image's ip -j implementation.
                cmd = ["ls -1 /sys/class/net"]
                actual_output = kubecli.exec_cmd_in_pod(cmd, pod_name, "default")
                if not actual_output:
                    raise Exception("Unable to list node interfaces from /sys/class/net")
                actual_interfaces = {
                    line.strip() for line in actual_output.splitlines() if line.strip()
                }

                resolved_interfaces = missing_interfaces & actual_interfaces
                if resolved_interfaces:
                    logging.info(
                        "Interface(s) %s on node %s validated using /sys/class/net names",
                        sorted(resolved_interfaces),
                        node,
                    )

            node_interface_list = sorted(displayed_interfaces | actual_interfaces)

            for interface in input_interface_list:
                if interface not in node_interface_list:
                    logging.error(
                        "Interface %s not found in node %s interface list %s"
                        % (interface, node, node_interface_list)
                    )
                    raise Exception(
                        "Interface %s not found in node %s interface list %s"
                        % (interface, node, node_interface_list)
                    )
    finally:
        logging.info("Deleting pod to query interface on node")
        kubecli.delete_pod(pod_name, "default")

    return input_interface_list


def get_node_interfaces(
    node_interface_dict: typing.Dict[str, typing.List[str]],
    label_selector: str,
    instance_count: int,
    pod_template,
    kubecli: KrknKubernetes,
    image: str
) -> typing.Dict[str, typing.List[str]]:
    """
    Function that is used to process the input dictionary with the nodes and
    its test interfaces.

    If the dictionary is empty, the label selector is used to select the nodes,
    and then a random interface on each node is chosen as a test interface.

    If the dictionary is not empty, it is filtered to include the nodes which
    are active and then their interfaces are verified to be present

    Args:
        node_interface_dict (Dictionary with keys as node name and value as
        a list of interface names)
            - Nodes and their interfaces for the scenario

        label_selector (string):
            - Label selector to get nodes if node_interface_dict is empty

        instance_count (int):
            - Number of nodes to fetch in case node_interface_dict is empty

        pod_template (jinja2.environment.Template)
            - The YAML template used to instantiate a pod to query
              the node's interfaces

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

    Returns:
        Filtered dictionary containing the test nodes and their test interfaces
    """
    if not node_interface_dict:
        if not label_selector:
            raise Exception(
                "If node names and interfaces aren't provided, "
                "then the label selector must be provided"
            )
        nodes = kubecli.get_node(None, label_selector, instance_count)
        node_interface_dict = {}
        for node in nodes:
            node_interface_dict[node] = get_default_interface(node, pod_template, kubecli, image)
    else:
        node_name_list = node_interface_dict.keys()
        filtered_node_list = []

        for node in node_name_list:
            filtered_node_list.extend(
                kubecli.get_node(node, label_selector, instance_count)
            )

        for node in filtered_node_list:
            node_interface_dict[node] = verify_interface(
                node_interface_dict[node], node, pod_template, kubecli, image
            )

    check_node_ingress_qdiscs(node_interface_dict, pod_template, kubecli, image)
    return node_interface_dict


def check_node_ingress_qdiscs(node_interface_dict, pod_template, kubecli, image):
    """Refuse to replace an existing node ingress qdisc before creating any jobs.

    The probe pod uses the node's network namespace. An inconclusive probe is
    treated as an error so ingress shaping cannot proceed on an unknown state.
    """
    for node, interfaces in node_interface_dict.items():
        pod_name_regex = str(random.randint(0, 10000))
        pod_name = f"fedtools-{pod_name_regex}"
        pod_body = yaml.safe_load(
            pod_template.render(regex_name=pod_name_regex, nodename=node, image=image)
        )
        kubecli.create_pod(pod_body, "default", 300)
        try:
            for interface in interfaces:
                if not re.fullmatch(r"[a-z0-9@_-]+", interface):
                    raise ValueError(f"Invalid interface name {interface!r} on node {node}")

                marker = "KRKN_QDISC_PROBE_OK"
                output = kubecli.exec_cmd_in_pod(
                    [f"tc qdisc show dev {interface} && echo {marker}"],
                    pod_name,
                    "default",
                )
                lines = [line.strip() for line in (output or "").splitlines()]
                if marker not in lines:
                    raise RuntimeError(
                        f"Could not inspect qdiscs on node {node}, interface {interface}: {output}"
                    )

                for line in lines:
                    fields = line.split()
                    if len(fields) >= 2 and fields[0] == "qdisc" and fields[1] in {"ingress", "clsact"}:
                        raise RuntimeError(
                            f"Node {node}, interface {interface} already has an ingress qdisc "
                            f"({fields[1]}); "
                            "ingress shaping cannot replace it safely"
                        )
        finally:
            kubecli.delete_pod(pod_name, "default")


def apply_ingress_filter(
    cfg: NetworkScenarioConfig,
    interface_list: typing.List[str],
    node: str,
    pod_template,
    job_template,
    kubecli: KrknKubernetes,
    create_interfaces: bool = True,
    param_selector: str = "all",
    image: str = "quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools",
    created_nodes: typing.Optional[typing.Set[str]] = None,
) -> str:
    """
    Function that applies the filters to shape incoming traffic to
    the provided node's interfaces.
    This is done by adding a virtual interface before each physical interface
    and then performing egress traffic control on the virtual interface

    Args:
        cfg (NetworkScenarioConfig)
            - Configurations used in this scenario

        interface_list (List of strings)
            - The interfaces on the node on which the filter is applied

        node (string):
            - Node on which the interfaces in interface_list are present

        pod_template (jinja2.environment.Template))
            - The YAML template used to instantiate a pod to create
              virtual interfaces on the node

        job_template (jinja2.environment.Template))
            - The YAML template used to instantiate a job to apply and remove
              the filters on the interfaces

        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

        param_selector (string)
            - Used to specify what kind of filter to apply. Useful during
              serial execution mode. Default value is 'all'

    Returns:
        The name of the job created that executes the commands on a node
        for ingress chaos scenario
    """

    network_params = cfg.network_params
    if param_selector != "all":
        network_params = {param_selector: cfg.network_params[param_selector]}

    if create_interfaces:
        create_virtual_interfaces(kubecli, interface_list, node, pod_template, image)
        if created_nodes is not None:
            created_nodes.add(node)

    exec_cmd = get_ingress_cmd(
        interface_list, network_params, duration=cfg.test_duration
    )
    logging.info("Executing %s on node %s" % (exec_cmd, node))
    job_body = yaml.safe_load(
        job_template.render(jobname=str(hash(node))[:5], nodename=node, image=image, cmd=exec_cmd)
    )
    api_response = kubecli.create_job(job_body)

    if api_response is None:
        raise Exception("Error creating job")

    return job_body["metadata"]["name"]


def create_virtual_interfaces(
    kubecli: KrknKubernetes, interface_list: typing.List[str], node: str, pod_template, image: str
) -> None:
    """
    Function that creates a privileged pod and uses it to create
    virtual interfaces on the node

    Args:
        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

        interface_list (List of strings)
            - The list of interfaces on the node for which virtual interfaces
              are to be created

        node (string)
            - The node on which the virtual interfaces are created

        pod_template (jinja2.environment.Template))
            - The YAML template used to instantiate a pod to create
              virtual interfaces on the node
    """
    pod_name_regex = str(random.randint(0, 10000))
    pod_body = yaml.safe_load(pod_template.render(regex_name=pod_name_regex, nodename=node, image=image))
    kubecli.create_pod(pod_body, "default", 300)
    logging.info(
        "Creating {0} virtual interfaces on node {1} using a pod".format(
            len(interface_list), node
        )
    )
    pod_name = f"modtools-{pod_name_regex}"
    try:
        create_ifb(kubecli, len(interface_list), pod_name)
    finally:
        logging.info("Deleting pod used to create virtual interfaces")
        kubecli.delete_pod(pod_name, "default")


def delete_virtual_interfaces(
    kubecli: KrknKubernetes,
    node_list: typing.Iterable[str],
    pod_template,
    image: str,
    interface_counts: typing.Optional[typing.Dict[str, int]] = None,
):
    """
    Function that creates a privileged pod and uses it to delete all
    virtual interfaces on the specified nodes

    Args:
        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

        node_list (Iterable of strings)
            - Nodes whose virtual interfaces are to be deleted

        interface_counts (Dictionary, optional)
            - Number of IFBs created on each node. When supplied, delete only
              those devices; omitted for compatibility with earlier callers

        pod_template (jinja2.environment.Template))
            - The YAML template used to instantiate a pod to delete
              virtual interfaces on the node
    """

    for node in node_list:
        pod_name_regex = str(random.randint(0, 10000))
        pod_body = yaml.safe_load(pod_template.render(regex_name=pod_name_regex, nodename=node, image=image))
        kubecli.create_pod(pod_body, "default", 300)
        logging.info("Deleting all virtual interfaces on node {0}".format(node))
        pod_name = f"modtools-{pod_name_regex}"
        try:
            count = interface_counts[node] if interface_counts is not None else None
            delete_ifb(kubecli, pod_name, number=count)
        finally:
            kubecli.delete_pod(pod_name, "default")


def create_ifb(kubecli: KrknKubernetes, number: int, pod_name: str):
    """Create IFB devices in the node network namespace of the host-networked pod."""
    created = []
    try:
        for i in range(number):
            name = f"ifb{i}"
            output = kubecli.exec_cmd_in_pod(
                [f"ip link add dev {name} type ifb && echo IFB_CREATED && "
                 f"ip link set dev {name} up && echo IFB_READY"],
                pod_name,
                "default",
            )
            lines = (output or "").splitlines()
            if "IFB_CREATED" in lines:
                created.append(name)
            if "IFB_READY" not in lines:
                raise RuntimeError(f"Could not create {name} on node: {output}")
    except Exception:
        for name in reversed(created):
            kubecli.exec_cmd_in_pod([f"ip link del dev {name}"], pod_name, "default")
        raise


def delete_ifb(kubecli: KrknKubernetes, pod_name: str, number: typing.Optional[int] = None):
    """Remove owned IFBs, retaining the legacy two-argument call for callers."""
    if number is None:
        kubecli.exec_cmd_in_pod(
            ["/host", "modprobe", "-r", "ifb"], pod_name, "default",
            base_command="chroot",
        )
        return
    for i in range(number):
        name = f"ifb{i}"
        output = kubecli.exec_cmd_in_pod(
            [f"ip link del dev {name} && echo IFB_DELETED"], pod_name, "default"
        )
        if not output or "IFB_DELETED" not in output.splitlines():
            logging.warning("Could not delete %s on node: %s", name, output)


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


def wait_for_job(
    kubecli: KrknKubernetes, job_list: typing.List[str], timeout: int = 300
) -> None:
    """
    Function that waits for a list of jobs to finish within a time period

    Args:
        kubecli (KrknKubernetes)
            - Object to interact with Kubernetes Python client

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
                api_response = kubecli.get_job_status(job_name, namespace="default")
            except Exception:
                logging.warning("Exception in getting job status")
            else:
                if api_response.status.failed:
                    raise RuntimeError(f"Ingress job {job_name} failed")
                if api_response.status.succeeded:
                    count += 1
                    job_list.remove(job_name)
            if time.time() > wait_time:
                raise Exception(
                    "Jobs did not complete within "
                    "the {0}s timeout period".format(timeout)
                )
            time.sleep(5)


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
        kubecli.delete_job(name=job_name, namespace="default")


def get_ingress_cmd(
    interface_list: typing.List[str],
    network_parameters: typing.Dict[str, str],
    duration: int = 300,
):
    """
    Function that returns the commands to the ingress traffic shaping on
    the node.
    First, the virtual interfaces created are linked to the test interfaces
    such that there is a one-to-one mapping between a virtual interface and
    a test interface.
    Then, incoming  traffic to each test interface is forced to first pass
    through the corresponding virtual interface.
    Linux's tc commands are then used to performing egress traffic control
    on the virtual interface. Since the outbound traffic from
    the virtual interface passes through the test interface, this is
    effectively ingress traffic control.
    After a certain time interval, the traffic is restored to normal

    Args:
        interface_list (List of strings)
            - Test interface list

        network_parameters (Dictionary with key and value as string)
            - Loss/Delay/Bandwidth and their corresponding values

        duration (int)
            - Duration for which the traffic control is to be done

    Returns:
        The traffic shaping commands as a string
    """

    tc_set = tc_unset = tc_ls = ""
    ownership_flags = []
    emergency_cleanup = ""
    param_map = {"latency": "delay", "loss": "loss", "bandwidth": "rate"}

    interface_pattern = re.compile(r"^[a-z0-9\-\@\_]+$")
    ifb_pattern = re.compile(r"^ifb[0-9]+$")

    for i, interface in enumerate(interface_list):
        if not interface_pattern.match(interface):
            logging.error("Interface name can only consist of alphanumeric characters")
            raise Exception(
                "Interface '{0}' does not match the required regex pattern :"
                r" ^[a-z0-9\-\@\_]+$".format(interface)
            )

        ifb_name = "ifb{0}".format(i)
        ingress_flag = f"krkn_ingress_{i}"
        ifb_flag = f"krkn_ifb_{i}"
        ownership_flags.extend((f"{ingress_flag}=0", f"{ifb_flag}=0"))
        if not ifb_pattern.match(ifb_name):
            logging.error("Invalid IFB name")
            raise Exception(
                "Interface '{0}' is an invalid IFB name. IFB name should "
                "follow the regex pattern ^ifb[0-9]+$".format(ifb_name)
            )

        tc_set += "tc qdisc add dev {0} handle ffff: ingress;{1}=1;".format(
            interface, ingress_flag
        )
        tc_set += "tc filter add dev {0} parent ffff: protocol ip u32 match u32 0 0 action mirred egress redirect dev {1};".format(  # noqa
            interface, ifb_name
        )
        tc_set = "{0} tc qdisc add dev {1} root netem".format(tc_set, ifb_name)
        tc_unset += f"tc qdisc del dev {ifb_name} root;{ifb_flag}=0;"
        tc_unset += f"tc qdisc del dev {interface} handle ffff: ingress;{ingress_flag}=0;"
        emergency_cleanup = (
            f'[ "${ifb_flag}" = 1 ] && tc qdisc del dev {ifb_name} root >/dev/null 2>&1 || true;'
            f'[ "${ingress_flag}" = 1 ] && tc qdisc del dev {interface} handle ffff: ingress '
            f'>/dev/null 2>&1 || true;{emergency_cleanup}'
        )
        tc_ls = "{0} tc qdisc ls dev {1} ;".format(tc_ls, ifb_name)

        for parameter in network_parameters.keys():
            tc_set += " {0} {1} ".format(
                param_map[parameter], network_parameters[parameter]
            )
        tc_set += f";{ifb_flag}=1;"

    exec_cmd = "set -e;{0};trap '{1}' EXIT; sleep 30;{2} {3} sleep {4};{5} sleep 20;{6}".format(
        ";".join(ownership_flags), emergency_cleanup, tc_set, tc_ls,
        duration, tc_unset, tc_ls
    )

    return exec_cmd


@plugin.step(
    id="network_chaos",
    name="Network Ingress",
    description="Applies filters to ihe ingress side of node(s) interfaces",
    outputs={
        "success": NetworkScenarioSuccessOutput,
        "error": NetworkScenarioErrorOutput,
    },
)
def network_chaos(
    cfg: NetworkScenarioConfig,
) -> typing.Tuple[
    str, typing.Union[NetworkScenarioSuccessOutput, NetworkScenarioErrorOutput]
]:
    """
    Function that performs the ingress network chaos scenario based
    on the provided configuration

    Args:
        cfg (NetworkScenarioConfig)
            - The object containing the configuration for the scenario

    Returns
        A 'success' or 'error' message along with their details
    """

    file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
    env = Environment(loader=file_loader)
    job_template = env.get_template("job.j2")
    pod_interface_template = env.get_template("pod_interface.j2")
    pod_module_template = env.get_template("pod_module.j2")
    kubecli = getattr(cfg, "kubecli", None) or KrknKubernetes(
        kubeconfig_path=cfg.kubeconfig_path
    )
    test_image = cfg.image
    logging.info("Starting Ingress Network Chaos")
    try:
        node_interface_dict = get_node_interfaces(
            cfg.node_interface_name,
            cfg.label_selector,
            cfg.instance_count,
            pod_interface_template,
            kubecli,
            test_image
        )
    except Exception:
        return "error", NetworkScenarioErrorOutput(format_exc())
    job_list = []
    created_nodes = set()

    try:
        if cfg.execution_type == "parallel":
            for node in node_interface_dict:
                job_list.append(
                    apply_ingress_filter(
                        cfg,
                        node_interface_dict[node],
                        node,
                        pod_module_template,
                        job_template,
                        kubecli,
                        image=test_image,
                        created_nodes=created_nodes,
                    )
                )
            logging.info("Waiting for parallel job to finish")
            wait_for_job(kubecli, job_list[:], cfg.test_duration + 100)

        elif cfg.execution_type == "serial":
            create_interfaces = True
            for param in cfg.network_params:
                for node in node_interface_dict:
                    job_list.append(
                        apply_ingress_filter(
                            cfg,
                            node_interface_dict[node],
                            node,
                            pod_module_template,
                            job_template,
                            kubecli,
                            create_interfaces=create_interfaces,
                            param_selector=param,
                            image=test_image,
                            created_nodes=created_nodes,
                        )
                    )
                logging.info("Waiting for serial job to finish")
                wait_for_job(kubecli, job_list[:], cfg.test_duration + 100)
                logging.info("Deleting jobs")
                delete_jobs(kubecli, job_list[:])
                job_list = []

                create_interfaces = False
        else:
            return "error", NetworkScenarioErrorOutput(
                "Invalid execution type - serial and parallel are "
                "the only accepted types"
            )
        return "success", NetworkScenarioSuccessOutput(
            filter_direction="ingress",
            test_interfaces=node_interface_dict,
            network_parameters=cfg.network_params,
            execution_type=cfg.execution_type,
        )
    except Exception as e:
        logging.error("Ingress Network Chaos exiting due to Exception - %s" % e)
        return "error", NetworkScenarioErrorOutput(format_exc())
    finally:
        interface_counts = {
            node: len(node_interface_dict[node]) for node in created_nodes
        }
        delete_virtual_interfaces(
            kubecli, created_nodes, pod_module_template, test_image,
            interface_counts=interface_counts,
        )
        logging.info("Deleting jobs(if any)")
        delete_jobs(kubecli, job_list[:])
