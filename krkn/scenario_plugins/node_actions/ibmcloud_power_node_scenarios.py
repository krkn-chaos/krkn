#!/usr/bin/env python
import time
from os import environ
from dataclasses import dataclass
import logging

from krkn_lib.k8s import KrknKubernetes
import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
import requests
import sys
import json


#  -o, --operation string   Operation to be done in a PVM server instance. 
# Valid values are: hard-reboot, immediate-shutdown, soft-reboot, reset-state, start, stop.

from krkn_lib.models.k8s import AffectedNodeStatus, AffectedNode


class IbmCloudPower:
    def __init__(self):
        """
        Initialize the ibm cloud client by using the the env variables:
            'IBMC_APIKEY' 'IBMC_URL'
        """
        self.api_key = environ.get("IBMC_APIKEY")
        self.service_url = environ.get("IBMC_POWER_URL")
        self.CRN = environ.get("IBMC_POWER_CRN")
        self.cloud_instance_id = self.CRN.split(":")[-3]
        print(self.cloud_instance_id)
        self.headers = None
        self.token = None
        if not self.api_key:
            raise Exception("Environmental variable 'IBMC_APIKEY' is not set")
        if not self.service_url:
            raise Exception("Environmental variable 'IBMC_POWER_URL' is not set")
        if not self.CRN:
            raise Exception("Environmental variable 'IBMC_POWER_CRN' is not set")
        try:
            self.authenticate()
            
        except Exception as e:
            logging.error("error authenticating" + str(e))
    
    def authenticate(self):
        url = "https://iam.cloud.ibm.com/identity/token"
        iam_auth_headers = {
            "content-type": "application/x-www-form-urlencoded",
            "accept": "application/json",
        }
        data = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": self.api_key,
        }

        response = self._make_request("POST", url, data=data, headers=iam_auth_headers)
        if response.status_code == 200:
            self.token = response.json()
            self.headers = {
                "Authorization": f"Bearer {self.token['access_token']}",
                "Content-Type": "application/json",
                "CRN": self.CRN,
            }
        else:
            logging.error("Authentication Error: %s", response.status_code)
            return None, None
            

    def _make_request(self,method, url, data=None, headers=None):
        try:
            response = requests.request(method, url, data=data, headers=headers)
            response.raise_for_status()
            return response
        except Exception as e:
            raise Exception(f"API Error: {e}")

    # Get the instance ID of the node
    def get_instance_id(self, node_name):

        url = f"{self.service_url}/pcloud/v1/cloud-instances/{self.cloud_instance_id}/pvm-instances/"
        response = self._make_request("GET", url, headers=self.headers)
        for node in response.json()["pvmInstances"]:
            if node_name == node["serverName"]:
                return node["pvmInstanceID"]
        logging.error("Couldn't find node with name %s, you could try another region", str(node_name))
        sys.exit(1)

    def delete_instance(self, instance_id):
        """
        Deletes the Instance whose name is given by 'instance_id'
        """
        try:
            url = f"{self.service_url}/pcloud/v1/cloud-instances/{self.cloud_instance_id}/pvm-instances/{instance_id}/action"
            self._make_request("POST", url, headers=self.headers, data=json.dumps({"action": "immediate-shutdown"}))
            logging.info("Deleted Instance -- '{}'".format(instance_id))
        except Exception as e:
            logging.info("Instance '{}' could not be deleted. ".format(instance_id))
            return False

    def reboot_instances(self, instance_id, soft=False):
        """
        Reboots the Instance whose name is given by 'instance_id'. Returns True if successful, or
        returns False if the Instance is not powered on
        """

        try:
            if soft:
                action = "soft-reboot"
            else:
                action = "hard-reboot"
            url = f"{self.service_url}/pcloud/v1/cloud-instances/{self.cloud_instance_id}/pvm-instances/{instance_id}/action"
            self._make_request("POST", url, headers=self.headers, data=json.dumps({"action": action}))
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
            url = f"{self.service_url}/pcloud/v1/cloud-instances/{self.cloud_instance_id}/pvm-instances/{instance_id}/action"
            self._make_request("POST", url, headers=self.headers, data=json.dumps({"action": "stop"}))
            logging.info("Stopped Instance -- '{}'".format(instance_id))
            return True
        except Exception as e:
            logging.info("Instance '{}' could not be stopped".format(instance_id))
            logging.info("error %s" , str(e))
            return False

    def start_instances(self, instance_id):
        """
        Stops the Instance whose name is given by 'instance_id'. Returns True if successful, or
        returns False if the Instance is already running
        """

        try:
            url = f"{self.service_url}/pcloud/v1/cloud-instances/{self.cloud_instance_id}/pvm-instances/{instance_id}/action"
            self._make_request("POST", url, headers=self.headers, data=json.dumps({"action": "start"}))
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
            url = f"{self.service_url}/pcloud/v1/cloud-instances/{self.cloud_instance_id}/pvm-instances/"
            response = self._make_request("GET", url, headers=self.headers)
            for pvm in response.json()["pvmInstances"]:
                instance_names.append({"serverName": pvm.serverName, "pvmInstanceID": pvm.pvmInstanceID})
        except Exception as e:
            logging.error("Error listing out instances: %s", str(e))
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
            url = f"{self.service_url}/pcloud/v1/cloud-instances/{self.cloud_instance_id}/pvm-instances/{instance_id}"
            response = self._make_request("GET", url, headers=self.headers)
            state = response.json()["status"]
            return state
        except Exception as e:
            logging.error(
                "Failed to get node instance status %s. Encountered following "
                "exception: %s.", instance_id, e
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
                "Instance %s is still being deleted, sleeping for 5 seconds",
                instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(
                    "Instance %s is still not deleted in allotted time", instance_id
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
        while status != "ACTIVE":
            status = self.get_instance_status(instance_id)
            logging.info(
                "Instance %s is still not running, sleeping for 5 seconds", instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(
                    "Instance %s is still not ready in allotted time", instance_id
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
        while status != "STOPPED":
            status = self.get_instance_status(instance_id)
            logging.info(
                "Instance %s is still not stopped, sleeping for 5 seconds", instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(
                    "Instance %s is still not stopped in allotted time", instance_id
                )
                return False
        end_time = time.time()
        print('affected_node' + str(affected_node))
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
        while status == "HARD_REBOOT" or status == "SOFT_REBOOT":
            status = self.get_instance_status(instance_id)
            logging.info(
                "Instance %s is still restarting, sleeping for 5 seconds", instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(
                    "Instance %s is still restarting after allotted time", instance_id
                )
                return False
        self.wait_until_running(instance_id, timeout, affected_node)
        print('affected_node' + str(affected_node))
        return True


@dataclass
class ibmcloud_power_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes, node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus, disable_ssl_verification: bool):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.ibmcloud_power = IbmCloudPower()
        
        self.node_action_kube_check = node_action_kube_check

    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        try:
            instance_id = self.ibmcloud_power.get_instance_id( node)
            affected_node = AffectedNode(node, node_id=instance_id)
            for _ in range(instance_kill_count):
                logging.info("Starting node_start_scenario injection")
                logging.info("Starting the node %s ", node)
                
                if instance_id:
                    vm_started = self.ibmcloud_power.start_instances(instance_id)
                    if vm_started:
                        self.ibmcloud_power.wait_until_running(instance_id, timeout, affected_node)
                        if self.node_action_kube_check: 
                            nodeaction.wait_for_ready_status(
                                node, timeout, self.kubecli, affected_node
                            )
                    logging.info(
                        "Node with instance ID: %s is in running state", node
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
            instance_id = self.ibmcloud_power.get_instance_id(node)
            for _ in range(instance_kill_count):
                affected_node = AffectedNode(node, instance_id)
                logging.info("Starting node_stop_scenario injection")
                logging.info("Stopping the node %s ", node)
                vm_stopped = self.ibmcloud_power.stop_instances(instance_id)
                if vm_stopped:
                    self.ibmcloud_power.wait_until_stopped(instance_id, timeout, affected_node)
                logging.info(
                    "Node with instance ID: %s is in stopped state", node
                )
                logging.info(
                    "node_stop_scenario has been successfully injected!"
                )
        except Exception as e:
            logging.error("Failed to stop node instance. Test Failed")
            logging.error("node_stop_scenario injection failed!")


    def node_reboot_scenario(self, instance_kill_count, node, timeout, soft_reboot=False):
        try:
            instance_id = self.ibmcloud_power.get_instance_id(node)
            for _ in range(instance_kill_count):
                affected_node = AffectedNode(node, node_id=instance_id)
                logging.info("Starting node_reboot_scenario injection")
                logging.info("Rebooting the node %s ", node)
                self.ibmcloud_power.reboot_instances(instance_id, soft_reboot)
                self.ibmcloud_power.wait_until_rebooted(instance_id, timeout, affected_node)
                if self.node_action_kube_check:
                    nodeaction.wait_for_unknown_status(
                        node, timeout, affected_node
                    )
                    nodeaction.wait_for_ready_status(
                        node, timeout, affected_node
                    )
                logging.info(
                        "Node with instance ID: %s has rebooted successfully", node
                )
                logging.info(
                    "node_reboot_scenario has been successfully injected!"
                )

        except Exception as e:
            logging.error("Failed to reboot node instance. Test Failed")
            logging.error("node_reboot_scenario injection failed!")


    def node_terminate_scenario(self, instance_kill_count, node, timeout, poll_interval):
        try:
            instance_id = self.ibmcloud_power.get_instance_id(node)
            for _ in range(instance_kill_count):
                affected_node = AffectedNode(node, node_id=instance_id)
                logging.info(
                    "Starting node_termination_scenario injection by first stopping the node"
                )
                logging.info("Deleting the node with instance ID: %s ", node)
                self.ibmcloud_power.delete_instance(instance_id)
                self.ibmcloud_power.wait_until_deleted(node, timeout, affected_node)
                logging.info(
                        "Node with instance ID: %s has been released", node
                )
                logging.info(
                    "node_terminate_scenario has been successfully injected!"
                )
        except Exception as e:
            logging.error("Failed to terminate node instance. Test Failed")
            logging.error("node_terminate_scenario injection failed!")

