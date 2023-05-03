#!/usr/bin/env python
import sys
import time
import typing
from os import environ
from dataclasses import dataclass, field
import random
from traceback import format_exc
import logging
from kraken.plugins.node_scenarios import kubernetes_functions as kube_helper
from arcaflow_plugin_sdk import validation, plugin
from kubernetes import client, watch
from ibm_vpc import VpcV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_cloud_sdk_core import ApiException
import requests
import sys


class IbmCloud:
    def __init__(self):
        """
        Initialize the ibm cloud client by using the the env variables:
            'IBMC_APIKEY' 'IBMC_URL'
        """
        apiKey = environ.get("IBMC_APIKEY")
        service_url = environ.get("IBMC_URL")
        if not apiKey:
            raise Exception(
                "Environmental variable 'IBMC_APIKEY' is not set"
            )
        if not service_url:
            raise Exception(
                "Environmental variable 'IBMC_URL' is not set"
            )
        try: 
            authenticator = IAMAuthenticator(apiKey)
            self.service = VpcV1(authenticator=authenticator)

            self.service.set_service_url(service_url)
        except Exception as e: 
            logging.error("error authenticating" + str(e))
            sys.exit(1)

    def delete_instance(self, instance_id):
        """
        Deletes the Instance whose name is given by 'instance_id'
        """
        try: 
            self.service.delete_instance(instance_id)
            logging.info("Deleted Instance -- '{}'".format(instance_id))
        except Exception as e:
            logging.info(
                "Instance '{}' could not be deleted. ".format(
                    instance_id
                )
            )
            return False

    def reboot_instances(self, instance_id):
        """
        Reboots the Instance whose name is given by 'instance_id'. Returns True if successful, or
        returns False if the Instance is not powered on
        """

        try:
            self.service.create_instance_action(
                    instance_id,
                    type='reboot',
                )
            logging.info("Reset Instance -- '{}'".format(instance_id))
            return True
        except Exception as e:
            logging.info(
                "Instance '{}' could not be rebooted".format(
                    instance_id
                )
            )
            return False

    def stop_instances(self, instance_id):
        """
        Stops the Instance whose name is given by 'instance_id'. Returns True if successful, or
        returns False if the Instance is already stopped
        """

        try:
            self.service.create_instance_action(
                    instance_id,
                    type='stop',
                )
            logging.info("Stopped Instance -- '{}'".format(instance_id))
            return True
        except Exception as e:
            logging.info(
                "Instance '{}' could not be stopped".format(instance_id)
            )
            logging.info("error" + str(e))
            return False

    def start_instances(self, instance_id):
        """
        Stops the Instance whose name is given by 'instance_id'. Returns True if successful, or
        returns False if the Instance is already running
        """

        try:
            self.service.create_instance_action(
                    instance_id,
                    type='start',
                )
            logging.info("Started Instance -- '{}'".format(instance_id))
            return True
        except Exception as e:
            logging.info("Instance '{}' could not start running".format(instance_id))
            return False

    def list_instances(self):
        """
        Returns a list of Instances present in the datacenter
        """
        instance_names = []
        try: 
            instances_result = self.service.list_instances().get_result()
            instances_list = instances_result['instances']
            for vpc in instances_list:
                instance_names.append({"vpc_name": vpc['name'], "vpc_id": vpc['id']})
            starting_count = instances_result['total_count']
            while instances_result['total_count'] == instances_result['limit']: 
                instances_result = self.service.list_instances(start=starting_count).get_result()
                instances_list = instances_result['instances']
                starting_count += instances_result['total_count']
                for vpc in instances_list:
                    instance_names.append({"vpc_name": vpc.name, "vpc_id": vpc.id})
        except Exception as e: 
            logging.error("Error listing out instances: " + str(e))
            sys.exit(1)
        return instance_names
    
    def find_id_in_list(self, name, vpc_list): 
        for vpc in vpc_list:
            if vpc['vpc_name'] == name: 
                return vpc['vpc_id']

    def get_instance_status(self, instance_id):
        """
        Returns the status of the Instance whose name is given by 'instance_id'
        """

        try:
            instance = self.service.get_instance(instance_id).get_result()
            state = instance['status']
            return state
        except Exception as e:
            logging.error(
                "Failed to get node instance status %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            return None

    def wait_until_deleted(self, instance_id, timeout):
        """
        Waits until the instance is deleted or until the timeout. Returns True if
        the instance is successfully deleted, else returns False
        """

        time_counter = 0
        vpc = self.get_instance_status(instance_id)
        while vpc is not None:
            vpc = self.get_instance_status(instance_id)
            logging.info(
                "Instance %s is still being deleted, sleeping for 5 seconds" % instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(
                    "Instance %s is still not deleted in allotted time" % instance_id
                )
                return False
        return True

    def wait_until_running(self, instance_id, timeout):
        """
        Waits until the Instance switches to running state or until the timeout.
        Returns True if the Instance switches to running, else returns False
        """

        time_counter = 0
        status = self.get_instance_status(instance_id)
        while status != "running":
            status = self.get_instance_status(instance_id)
            logging.info(
                "Instance %s is still not running, sleeping for 5 seconds" % instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info("Instance %s is still not ready in allotted time" % instance_id)
                return False
        return True

    def wait_until_stopped(self, instance_id, timeout):
        """
        Waits until the Instance switches to stopped state or until the timeout.
        Returns True if the Instance switches to stopped, else returns False
        """

        time_counter = 0
        status = self.get_instance_status(instance_id)
        while status != "stopped":
            status = self.get_instance_status(instance_id)
            logging.info(
                "Instance %s is still not stopped, sleeping for 5 seconds" % instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info("Instance %s is still not stopped in allotted time" % instance_id)
                return False
        return True

    def wait_until_rebooted(self, instance_id, timeout):
        """
        Waits until the Instance switches to restarting state and then running state or until the timeout.
        Returns True if the Instance switches back to running, else returns False
        """

        time_counter = 0
        status = self.get_instance_status(instance_id)
        while status == "starting":
            status = self.get_instance_status(instance_id)
            logging.info(
                "Instance %s is still restarting, sleeping for 5 seconds" % instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info("Instance %s is still restarting after allotted time" % instance_id)
                return False
        self.wait_until_running(instance_id, timeout)
        return True


@dataclass
class Node:
    name: str


@dataclass
class NodeScenarioSuccessOutput:

    nodes: typing.Dict[int, Node] = field(
        metadata={
            "name": "Nodes started/stopped/terminated/rebooted",
            "description": """Map between timestamps and the pods started/stopped/terminated/rebooted.
                        The timestamp is provided in nanoseconds""",
        }
    )
    action: kube_helper.Actions = field(
        metadata={
            "name": "The action performed on the node",
            "description": """The action performed or attempted to be performed on the node. Possible values
                        are : Start, Stop, Terminate, Reboot""",
        }
    )


@dataclass
class NodeScenarioErrorOutput:

    error: str
    action: kube_helper.Actions = field(
        metadata={
            "name": "The action performed on the node",
            "description": """The action attempted to be performed on the node. Possible values are : Start
                        Stop, Terminate, Reboot""",
        }
    )


@dataclass
class NodeScenarioConfig:

    name: typing.Annotated[
        typing.Optional[str],
        validation.required_if_not("label_selector"),
        validation.required_if("skip_openshift_checks"),
    ] = field(
        default=None,
        metadata={
            "name": "Name",
            "description": "Name(s) for target nodes. Required if label_selector is not set.",
        },
    )

    runs: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=1,
        metadata={
            "name": "Number of runs per node",
            "description": "Number of times to inject each scenario under actions (will perform on same node each time)",
        },
    )

    label_selector: typing.Annotated[
        typing.Optional[str], 
        validation.min(1),
        validation.required_if_not("name")
    ] = field(
        default=None,
        metadata={
            "name": "Label selector",
            "description": "Kubernetes label selector for the target nodes. Required if name is not set.\n"
            "See https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/ for details.",
        },
    )

    timeout: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=180,
        metadata={
            "name": "Timeout",
            "description": "Timeout to wait for the target pod(s) to be removed in seconds.",
        },
    )

    instance_count: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=1,
        metadata={
            "name": "Instance Count",
            "description": "Number of nodes to perform action/select that match the label selector.",
        },
    )

    skip_openshift_checks: typing.Optional[bool] = field(
        default=False,
        metadata={
            "name": "Skip Openshift Checks",
            "description": "Skip checking the status of the openshift nodes.",
        },
    )

    kubeconfig_path: typing.Optional[str] = field(
        default=None,
        metadata={
            "name": "Kubeconfig path",
            "description": "Path to your Kubeconfig file. Defaults to ~/.kube/config.\n"
            "See https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/ for "
            "details.",
        },
    )


@plugin.step(
    id="ibmcloud-node-start",
    name="Start the node",
    description="Start the node(s) by starting the Ibmcloud Instance on which the node is configured",
    outputs={"success": NodeScenarioSuccessOutput, "error": NodeScenarioErrorOutput},
)
def node_start(
    cfg: NodeScenarioConfig,
) -> typing.Tuple[
    str, typing.Union[NodeScenarioSuccessOutput, NodeScenarioErrorOutput]
]:
    with kube_helper.setup_kubernetes(None) as cli:
        ibmcloud = IbmCloud()
        core_v1 = client.CoreV1Api(cli)
        watch_resource = watch.Watch()
        node_list = kube_helper.get_node_list(cfg, kube_helper.Actions.START, core_v1)
        node_name_id_list = ibmcloud.list_instances()
        nodes_started = {}
        for name in node_list:
            try:
                for _ in range(cfg.runs):
                    logging.info("Starting node_start_scenario injection")
                    logging.info("Starting the node %s " % (name))
                    instance_id = ibmcloud.find_id_in_list(name, node_name_id_list)
                    if instance_id: 
                        vm_started = ibmcloud.start_instances(instance_id)
                        if vm_started:
                            ibmcloud.wait_until_running(instance_id, cfg.timeout)
                            if not cfg.skip_openshift_checks:
                                kube_helper.wait_for_ready_status(
                                    name, cfg.timeout, watch_resource, core_v1
                                )
                            nodes_started[int(time.time_ns())] = Node(name=name)
                        logging.info("Node with instance ID: %s is in running state" % name)
                        logging.info("node_start_scenario has been successfully injected!")
                    else: 
                        logging.error("Failed to find node that matched instances on ibm cloud in region")
                        return "error", NodeScenarioErrorOutput(
                            "No matching vpc with node name " + name, kube_helper.Actions.START
                        )
            except Exception as e:
                logging.error("Failed to start node instance. Test Failed")
                logging.error("node_start_scenario injection failed!")
                return "error", NodeScenarioErrorOutput(
                    format_exc(), kube_helper.Actions.START
                )

    return "success", NodeScenarioSuccessOutput(
        nodes_started, kube_helper.Actions.START
    )


@plugin.step(
    id="ibmcloud-node-stop",
    name="Stop the node",
    description="Stop the node(s) by starting the Ibmcloud Instance on which the node is configured",
    outputs={"success": NodeScenarioSuccessOutput, "error": NodeScenarioErrorOutput},
)
def node_stop(
    cfg: NodeScenarioConfig,
) -> typing.Tuple[
    str, typing.Union[NodeScenarioSuccessOutput, NodeScenarioErrorOutput]
]:
    with kube_helper.setup_kubernetes(None) as cli:
        ibmcloud = IbmCloud()
        core_v1 = client.CoreV1Api(cli)
        watch_resource = watch.Watch()
        logging.info('set up done')
        node_list = kube_helper.get_node_list(cfg, kube_helper.Actions.STOP, core_v1)
        logging.info("set node list" + str(node_list))
        node_name_id_list = ibmcloud.list_instances()
        logging.info('node names' + str(node_name_id_list))
        nodes_stopped = {}
        for name in node_list:
            try:
                for _ in range(cfg.runs):
                    logging.info("Starting node_stop_scenario injection")
                    logging.info("Stopping the node %s " % (name))
                    instance_id = ibmcloud.find_id_in_list(name, node_name_id_list)
                    if instance_id:
                        vm_stopped = ibmcloud.stop_instances(instance_id)
                        if vm_stopped:
                            ibmcloud.wait_until_stopped(instance_id, cfg.timeout)
                            if not cfg.skip_openshift_checks:
                                kube_helper.wait_for_ready_status(
                                    name, cfg.timeout, watch_resource, core_v1
                                )
                            nodes_stopped[int(time.time_ns())] = Node(name=name)
                        logging.info("Node with instance ID: %s is in stopped state" % name)
                        logging.info("node_stop_scenario has been successfully injected!")
                    else: 
                        logging.error("Failed to find node that matched instances on ibm cloud in region")
                        return "error", NodeScenarioErrorOutput(
                            "No matching vpc with node name " + name, kube_helper.Actions.STOP
                        )
            except Exception as e:
                logging.error("Failed to stop node instance. Test Failed")
                logging.error("node_stop_scenario injection failed!")
                return "error", NodeScenarioErrorOutput(
                    format_exc(), kube_helper.Actions.STOP
                )

        return "success", NodeScenarioSuccessOutput(
            nodes_stopped, kube_helper.Actions.STOP
        )


@plugin.step(
    id="ibmcloud-node-reboot",
    name="Reboot Ibmcloud Instance",
    description="Reboot the node(s) by starting the Ibmcloud Instance on which the node is configured",
    outputs={"success": NodeScenarioSuccessOutput, "error": NodeScenarioErrorOutput},
)
def node_reboot(
    cfg: NodeScenarioConfig,
) -> typing.Tuple[
    str, typing.Union[NodeScenarioSuccessOutput, NodeScenarioErrorOutput]
]:
    with kube_helper.setup_kubernetes(None) as cli:
        ibmcloud = IbmCloud()
        core_v1 = client.CoreV1Api(cli)
        watch_resource = watch.Watch()
        node_list = kube_helper.get_node_list(cfg, kube_helper.Actions.REBOOT, core_v1)
        node_name_id_list = ibmcloud.list_instances()
        nodes_rebooted = {}
        for name in node_list:
            try:
                for _ in range(cfg.runs):
                    logging.info("Starting node_reboot_scenario injection")
                    logging.info("Rebooting the node %s " % (name))
                    instance_id = ibmcloud.find_id_in_list(name, node_name_id_list)
                    if instance_id:
                        ibmcloud.reboot_instances(instance_id)
                        ibmcloud.wait_until_rebooted(instance_id, cfg.timeout)
                        if not cfg.skip_openshift_checks:
                            kube_helper.wait_for_unknown_status(
                                name, cfg.timeout, watch_resource, core_v1
                            )
                            kube_helper.wait_for_ready_status(
                                name, cfg.timeout, watch_resource, core_v1
                            )
                        nodes_rebooted[int(time.time_ns())] = Node(name=name)
                        logging.info(
                            "Node with instance ID: %s has rebooted successfully" % name
                        )
                        logging.info("node_reboot_scenario has been successfully injected!")
                    else: 
                        logging.error("Failed to find node that matched instances on ibm cloud in region")
                        return "error", NodeScenarioErrorOutput(
                            "No matching vpc with node name " + name, kube_helper.Actions.REBOOT
                        )
            except Exception as e:
                logging.error("Failed to reboot node instance. Test Failed")
                logging.error("node_reboot_scenario injection failed!")
                return "error", NodeScenarioErrorOutput(
                    format_exc(), kube_helper.Actions.REBOOT
                )

    return "success", NodeScenarioSuccessOutput(
        nodes_rebooted, kube_helper.Actions.REBOOT
    )


@plugin.step(
    id="ibmcloud-node-terminate",
    name="Reboot Ibmcloud Instance",
    description="Wait for node to be deleted",
    outputs={"success": NodeScenarioSuccessOutput, "error": NodeScenarioErrorOutput},
)
def node_terminate(
    cfg: NodeScenarioConfig,
) -> typing.Tuple[
    str, typing.Union[NodeScenarioSuccessOutput, NodeScenarioErrorOutput]
]:
    with kube_helper.setup_kubernetes(None) as cli:
        ibmcloud = IbmCloud()
        core_v1 = client.CoreV1Api(cli)
        node_list = kube_helper.get_node_list(
            cfg, kube_helper.Actions.TERMINATE, core_v1
        )
        node_name_id_list = ibmcloud.list_instances()
        nodes_terminated = {}
        for name in node_list:
            try:
                for _ in range(cfg.runs):
                    logging.info(
                        "Starting node_termination_scenario injection by first stopping the node"
                    )
                    instance_id = ibmcloud.find_id_in_list(name, node_name_id_list)
                    logging.info("Deleting the node with instance ID: %s " % (name))
                    if instance_id: 
                        ibmcloud.delete_instance(instance_id)
                        ibmcloud.wait_until_released(name, cfg.timeout)
                        nodes_terminated[int(time.time_ns())] = Node(name=name)
                        logging.info("Node with instance ID: %s has been released" % name)
                        logging.info("node_terminate_scenario has been successfully injected!")
                    else: 
                        logging.error("Failed to find instances that matched the node specifications on ibm cloud in the set region")
                        return "error", NodeScenarioErrorOutput(
                            "No matching vpc with node name " + name, kube_helper.Actions.TERMINATE
                        )
            except Exception as e:
                logging.error("Failed to terminate node instance. Test Failed")
                logging.error("node_terminate_scenario injection failed!")
                return "error", NodeScenarioErrorOutput(
                    format_exc(), kube_helper.Actions.TERMINATE
                )

    return "success", NodeScenarioSuccessOutput(
        nodes_terminated, kube_helper.Actions.TERMINATE
    )
