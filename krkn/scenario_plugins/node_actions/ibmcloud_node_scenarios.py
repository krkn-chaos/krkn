#!/usr/bin/env python
import time
import typing
from os import environ
from dataclasses import dataclass, field
from traceback import format_exc
import logging

from krkn_lib.k8s import KrknKubernetes
import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
from kubernetes import client, watch
from ibm_vpc import VpcV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
import sys

from krkn_lib.models.k8s import AffectedNodeStatus, AffectedNode


class IbmCloud:
    def __init__(self):
        """
        Initialize the ibm cloud client by using the the env variables:
            'IBMC_APIKEY' 'IBMC_URL'
        """
        apiKey = environ.get("IBMC_APIKEY")
        service_url = environ.get("IBMC_URL")
        if not apiKey:
            raise Exception("Environmental variable 'IBMC_APIKEY' is not set")
        if not service_url:
            raise Exception("Environmental variable 'IBMC_URL' is not set")
        try:
            authenticator = IAMAuthenticator(apiKey)
            self.service = VpcV1(authenticator=authenticator)

            self.service.set_service_url(service_url)
            
        except Exception as e:
            logging.error("error authenticating" + str(e))

    def configure_ssl_verification(self, disable_ssl_verification):
        """
        Configure SSL verification for IBM Cloud VPC service.
        
        Args:
            disable_ssl_verification: If True, disables SSL verification.
        """
        logging.info(f"Configuring SSL verification: disable_ssl_verification={disable_ssl_verification}")
        if disable_ssl_verification:
            self.service.set_disable_ssl_verification(True)
            logging.info("SSL verification disabled for IBM Cloud VPC service")
        else:
            self.service.set_disable_ssl_verification(False)
            logging.info("SSL verification enabled for IBM Cloud VPC service")
            
    # Get the instance ID of the node
    def get_instance_id(self, node_name):
        node_list = self.list_instances()
        for node in node_list:
            if node_name == node["vpc_name"]:
                return node["vpc_id"]
        logging.error("Couldn't find node with name " + str(node_name) + ", you could try another region")
        sys.exit(1)

    def delete_instance(self, instance_id):
        """
        Deletes the Instance whose name is given by 'instance_id'
        """
        try:
            self.service.delete_instance(instance_id)
            logging.info("Deleted Instance -- '{}'".format(instance_id))
        except Exception as e:
            logging.info("Instance '{}' could not be deleted. ".format(instance_id))
            return False

    def reboot_instances(self, instance_id):
        """
        Reboots the Instance whose name is given by 'instance_id'. Returns True if successful, or
        returns False if the Instance is not powered on
        """

        try:
            self.service.create_instance_action(
                instance_id,
                type="reboot",
            )
            logging.info("Reset Instance -- '{}'".format(instance_id))
            return True
        except Exception as e:
            logging.info("Instance '{}' could not be rebooted".format(instance_id))
            return False

    def stop_instances(self, instance_id):
        """
        Stops the Instance whose name is given by 'instance_id'. Returns True if successful, or
        returns False if the Instance is already stopped
        """

        try:
            self.service.create_instance_action(
                instance_id,
                type="stop",
            )
            logging.info("Stopped Instance -- '{}'".format(instance_id))
            return True
        except Exception as e:
            logging.info("Instance '{}' could not be stopped".format(instance_id))
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
                type="start",
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
            instances_list = instances_result["instances"]
            for vpc in instances_list:
                instance_names.append({"vpc_name": vpc["name"], "vpc_id": vpc["id"]})
            starting_count = instances_result["total_count"]
            while instances_result["total_count"] == instances_result["limit"]:
                instances_result = self.service.list_instances(
                    start=starting_count
                ).get_result()
                instances_list = instances_result["instances"]
                starting_count += instances_result["total_count"]
                for vpc in instances_list:
                    instance_names.append({"vpc_name": vpc.name, "vpc_id": vpc.id})
        except Exception as e:
            logging.error("Error listing out instances: " + str(e))
            sys.exit(1)
        return instance_names

    def find_id_in_list(self, name, vpc_list):
        for vpc in vpc_list:
            if vpc["vpc_name"] == name:
                return vpc["vpc_id"]

    def get_instance_status(self, instance_id):
        """
        Returns the status of the Instance whose name is given by 'instance_id'
        """

        try:
            instance = self.service.get_instance(instance_id).get_result()
            state = instance["status"]
            return state
        except Exception as e:
            logging.error(
                "Failed to get node instance status %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            return None

    def wait_until_deleted(self, instance_id, timeout, affected_node=None):
        """
        Waits until the instance is deleted or until the timeout. Returns True if
        the instance is successfully deleted, else returns False
        """
        start_time = time.time()
        time_counter = 0
        vpc = self.get_instance_status(instance_id)
        while vpc is not None:
            vpc = self.get_instance_status(instance_id)
            logging.info(
                "Instance %s is still being deleted, sleeping for 5 seconds"
                % instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(
                    "Instance %s is still not deleted in allotted time" % instance_id
                )
                return False
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("terminated", end_time - start_time)
        return True

    def wait_until_running(self, instance_id, timeout, affected_node=None):
        """
        Waits until the Instance switches to running state or until the timeout.
        Returns True if the Instance switches to running, else returns False
        """
        start_time = time.time()
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
                logging.info(
                    "Instance %s is still not ready in allotted time" % instance_id
                )
                return False
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("running", end_time - start_time)
        return True

    def wait_until_stopped(self, instance_id, timeout, affected_node):
        """
        Waits until the Instance switches to stopped state or until the timeout.
        Returns True if the Instance switches to stopped, else returns False
        """
        start_time = time.time()
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
                logging.info(
                    "Instance %s is still not stopped in allotted time" % instance_id
                )
                return False
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("stopped", end_time - start_time)
        return True


    def wait_until_rebooted(self, instance_id, timeout, affected_node):
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
                logging.info(
                    "Instance %s is still restarting after allotted time" % instance_id
                )
                return False
        self.wait_until_running(instance_id, timeout, affected_node)
        return True


@dataclass
class ibm_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes, node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus, disable_ssl_verification: bool):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.ibmcloud = IbmCloud()
        
        # Configure SSL verification
        self.ibmcloud.configure_ssl_verification(disable_ssl_verification)
        
        self.node_action_kube_check = node_action_kube_check

    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        try:
            instance_id = self.ibmcloud.get_instance_id( node)
            affected_node = AffectedNode(node, node_id=instance_id)
            for _ in range(instance_kill_count):
                logging.info("Starting node_start_scenario injection")
                logging.info("Starting the node %s " % (node))
                
                if instance_id:
                    vm_started = self.ibmcloud.start_instances(instance_id)
                    if vm_started:
                        self.ibmcloud.wait_until_running(instance_id, timeout, affected_node)
                        if self.node_action_kube_check: 
                            nodeaction.wait_for_ready_status(
                                node, timeout, self.kubecli, affected_node
                            )
                    logging.info(
                        "Node with instance ID: %s is in running state" % node
                    )
                    logging.info(
                        "node_start_scenario has been successfully injected!"
                    )
                else:
                    logging.error(
                        "Failed to find node that matched instances on ibm cloud in region"
                    )

        except Exception as e:
            logging.error("Failed to start node instance. Test Failed")
            logging.error("node_start_scenario injection failed!")
        self.affected_nodes_status.affected_nodes.append(affected_node)


    def node_stop_scenario(self, instance_kill_count, node, timeout, poll_interval):
        try:
            instance_id = self.ibmcloud.get_instance_id(node)
            for _ in range(instance_kill_count):
                affected_node = AffectedNode(node, instance_id)
                logging.info("Starting node_stop_scenario injection")
                logging.info("Stopping the node %s " % (node))
                vm_stopped = self.ibmcloud.stop_instances(instance_id)
                if vm_stopped:
                    self.ibmcloud.wait_until_stopped(instance_id, timeout, affected_node)
                    logging.info(
                        "Node with instance ID: %s is in stopped state" % node
                    )
                    logging.info(
                        "node_stop_scenario has been successfully injected!"
                    )
                else:
                    logging.error(
                        "Failed to stop node instance %s. Stop command failed." % instance_id
                    )
                    raise Exception("Stop command failed for instance %s" % instance_id)
                self.affected_nodes_status.affected_nodes.append(affected_node)
        except Exception as e:
            logging.error("Failed to stop node instance. Test Failed: %s" % str(e))
            logging.error("node_stop_scenario injection failed!")


    def node_reboot_scenario(self, instance_kill_count, node, timeout, soft_reboot=False):
        try:
            instance_id = self.ibmcloud.get_instance_id(node)
            for _ in range(instance_kill_count):
                affected_node = AffectedNode(node, node_id=instance_id)
                logging.info("Starting node_reboot_scenario injection")
                logging.info("Rebooting the node %s " % (node))
                vm_rebooted = self.ibmcloud.reboot_instances(instance_id)
                if vm_rebooted:
                    self.ibmcloud.wait_until_rebooted(instance_id, timeout, affected_node)
                    if self.node_action_kube_check:
                        nodeaction.wait_for_unknown_status(
                            node, timeout, self.kubecli, affected_node
                        )
                        nodeaction.wait_for_ready_status(
                            node, timeout, self.kubecli, affected_node
                        )
                    logging.info(
                        "Node with instance ID: %s has rebooted successfully" % node
                    )
                    logging.info(
                        "node_reboot_scenario has been successfully injected!"
                    )
                else:
                    logging.error(
                        "Failed to reboot node instance %s. Reboot command failed." % instance_id
                    )
                    raise Exception("Reboot command failed for instance %s" % instance_id)
                self.affected_nodes_status.affected_nodes.append(affected_node)

        except Exception as e:
            logging.error("Failed to reboot node instance. Test Failed: %s" % str(e))
            logging.error("node_reboot_scenario injection failed!")


    def node_terminate_scenario(self, instance_kill_count, node, timeout, poll_interval):
        try:
            instance_id = self.ibmcloud.get_instance_id(node)
            for _ in range(instance_kill_count):
                affected_node = AffectedNode(node, node_id=instance_id)
                logging.info(
                    "Starting node_termination_scenario injection by first stopping the node"
                )
                logging.info("Deleting the node with instance ID: %s " % (node))
                self.ibmcloud.delete_instance(instance_id)
                self.ibmcloud.wait_until_deleted(node, timeout, affected_node)
                logging.info(
                    "Node with instance ID: %s has been released" % node
                )
                logging.info(
                    "node_terminate_scenario has been successfully injected!"
                )
                self.affected_nodes_status.affected_nodes.append(affected_node)
        except Exception as e:
            logging.error("Failed to terminate node instance. Test Failed: %s" % str(e))
            logging.error("node_terminate_scenario injection failed!")

