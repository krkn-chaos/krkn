import sys
import time
import logging
import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
import os
import json
from aliyunsdkcore.client import AcsClient
from aliyunsdkecs.request.v20140526 import (
    DescribeInstancesRequest,
    DeleteInstanceRequest,
)
from aliyunsdkecs.request.v20140526 import (
    StopInstanceRequest,
    StartInstanceRequest,
    RebootInstanceRequest,
)
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

class Alibaba:
    def __init__(self):
        try:
            # Acquire a credential object using CLI-based authentication.
            key_id = os.getenv("ALIBABA_ID")
            key_secret = os.getenv("ALIBABA_SECRET")
            region_id = os.getenv("ALIBABA_REGION_ID")
            self.compute_client = AcsClient(key_id, key_secret, region_id)
        except Exception as e:
            logging.error("ERROR: Initializing alibaba, " + str(e))

    # send open api request
    def _send_request(self, request):
        request.set_accept_format("json")
        try:
            response_str = self.compute_client.do_action(request)
            response_detail = json.loads(response_str)
            return response_detail
        except Exception as e:
            logging.error("ERROR sending request %s with message %s", request, e)

    # output the instance owned in current region.
    def list_instances(self):
        try:
            request = DescribeInstancesRequest.DescribeInstancesRequest()
            response = self._send_request(request)
            if response is not None:
                if response.get("Instances"):
                    instance_list = response.get("Instances").get("Instance")
                else:
                    logging.error(
                        "ERROR couldn't get list of instances; validate your environment "
                        "variables/credentials are correct"
                    )
                    logging.error(response)
                    raise RuntimeError(response)
                return instance_list
            return []
        except Exception as e:
            logging.error("ERROR while trying to get list of instances " + str(e))
            raise e

    # Get the instance ID of the node
    def get_instance_id(self, node_name):
        vm_list = self.list_instances()
        for vm in vm_list:
            if node_name == vm["InstanceName"]:
                return vm["InstanceId"]
        logging.error(
            "Couldn't find vm with name "
            + str(node_name)
            + ", you could try another region"
        )
        raise RuntimeError(
            "Couldn't find vm with name "
            + str(node_name)
            + ", you could try another region"
        )

    # Start the node instance
    def start_instances(self, instance_id):
        try:
            request = StartInstanceRequest.StartInstanceRequest()
            request.set_InstanceId(instance_id)
            self._send_request(request)
            logging.info("Start %s command submit successfully.", instance_id)
            logging.info("ECS instance with id " + str(instance_id) + " started")
        except Exception as e:
            logging.error(
                "Failed to start node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            raise e

    # https://partners-intl.aliyun.com/help/en/doc-detail/93110.html
    # Stop the node instance
    def stop_instances(self, instance_id, force_stop=True):
        try:
            request = StopInstanceRequest.StopInstanceRequest()
            request.set_InstanceId(instance_id)
            request.set_ForceStop(force_stop)
            self._send_request(request)
            logging.info("Stop %s command submit successfully.", instance_id)
        except Exception as e:
            logging.error(
                "Failed to stop node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            raise e

    # Terminate the node instance
    def release_instance(self, instance_id, force_release=True):
        try:
            request = DeleteInstanceRequest.DeleteInstanceRequest()
            request.set_InstanceId(instance_id)
            request.set_Force(force_release)
            self._send_request(request)
            logging.info("ECS Instance " + str(instance_id) + " released")
        except Exception as e:
            logging.error(
                "Failed to terminate node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            raise e

    # Reboot the node instance
    def reboot_instances(self, instance_id, force_reboot=True):
        try:
            request = RebootInstanceRequest.RebootInstanceRequest()
            request.set_InstanceId(instance_id)
            request.set_ForceStop(force_reboot)
            self._send_request(request)
            logging.info("ECS Instance " + str(instance_id) + " rebooted")
        except Exception as e:
            logging.error(
                "Failed to reboot node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            raise e

    def get_vm_status(self, instance_id):

        try:
            logging.info("Check instance %s status", instance_id)
            request = DescribeInstancesRequest.DescribeInstancesRequest()
            request.set_InstanceIds(json.dumps([instance_id]))
            response = self._send_request(request)
            if response is not None:
                instance_list = response.get("Instances").get("Instance")
                if len(instance_list) > 0:
                    return instance_list[0]["Status"]
                return None
            return "Unknown"
        except Exception as e:
            logging.error(
                "Failed to get node instance status %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            return None

    # Wait until the node instance is running
    def wait_until_running(self, instance_id, timeout, affected_node):
        time_counter = 0
        start_time = time.time()
        status = self.get_vm_status(instance_id)
        while status != "Running":
            status = self.get_vm_status(instance_id)
            logging.info(
                "ECS %s is still not running, sleeping for 5 seconds" % instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info("ECS %s is still not ready in allotted time" % instance_id)
                return False
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("running", end_time - start_time)
        return True

    # Wait until the node instance is stopped
    def wait_until_stopped(self, instance_id, timeout, affected_node):
        time_counter = 0
        start_time = time.time()
        status = self.get_vm_status(instance_id)
        while status != "Stopped":
            status = self.get_vm_status(instance_id)
            logging.info(
                "Vm %s is still stopping, sleeping for 5 seconds" % instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(
                    "Vm %s is still not stopped in allotted time" % instance_id
                )
                return False
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("stopped", end_time - start_time)
        return True

    # Wait until the node instance is terminated
    def wait_until_released(self, instance_id, timeout, affected_node):
        start_time = time.time()
        statuses = self.get_vm_status(instance_id)
        time_counter = 0
        while statuses and statuses != "Released":
            statuses = self.get_vm_status(instance_id)
            logging.info(
                "ECS %s is still being released, waiting 10 seconds" % instance_id
            )
            time.sleep(10)
            time_counter += 10
            if time_counter >= timeout:
                logging.info("ECS %s was not released in allotted time" % instance_id)
                return False

        logging.info("ECS %s is released" % instance_id)
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("terminated", end_time - start_time)
        return True


# krkn_lib
class alibaba_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes, node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.alibaba = Alibaba()
        self.node_action_kube_check = node_action_kube_check
        

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_start_scenario injection")
                vm_id = self.alibaba.get_instance_id(node)
                affected_node.node_id = vm_id
                logging.info(
                    "Starting the node %s with instance ID: %s " % (node, vm_id)
                )
                self.alibaba.start_instances(vm_id)
                self.alibaba.wait_until_running(vm_id, timeout, affected_node)
                if self.node_action_kube_check:
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info("Node with instance ID: %s is in running state" % node)
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following "
                    "exception: %s. Test Failed" % (e)
                )
                logging.error("node_start_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_stop_scenario injection")
                vm_id = self.alibaba.get_instance_id(node)
                affected_node.node_id = vm_id
                logging.info(
                    "Stopping the node %s with instance ID: %s " % (node, vm_id)
                )
                self.alibaba.stop_instances(vm_id)
                self.alibaba.wait_until_stopped(vm_id, timeout, affected_node)
                logging.info("Node with instance ID: %s is in stopped state" % vm_id)
                if self.node_action_kube_check:
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed" % e
                )
                logging.error("node_stop_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Might need to stop and then release the instance
    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info(
                    "Starting node_termination_scenario injection by first stopping instance"
                )
                vm_id = self.alibaba.get_instance_id(node)
                affected_node.node_id = vm_id
                self.alibaba.stop_instances(vm_id)
                self.alibaba.wait_until_stopped(vm_id, timeout, affected_node)
                logging.info(
                    "Releasing the node %s with instance ID: %s " % (node, vm_id)
                )
                self.alibaba.release_instance(vm_id)
                self.alibaba.wait_until_released(vm_id, timeout, affected_node)
                logging.info("Node with instance ID: %s has been released" % node)
                logging.info(
                    "node_termination_scenario has been successfully injected!"
                )
            except Exception as e:
                logging.error(
                    "Failed to release node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_termination_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout, soft_reboot=False):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_reboot_scenario injection")
                instance_id = self.alibaba.get_instance_id(node)
                affected_node.node_id = instance_id
                logging.info("Rebooting the node with instance ID: %s ", instance_id)
                self.alibaba.reboot_instances(instance_id)
                if self.node_action_kube_check:
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(
                    "Node with instance ID: %s has been rebooted" % (instance_id)
                )
                logging.info("node_reboot_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)
