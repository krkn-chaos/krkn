import sys
import time
import logging
import krkn.invoke.command as runcommand
import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

class OPENSTACKCLOUD:
    def __init__(self):
        self.Wait = 30

    # Get the instance ID of the node
    def get_instance_id(self, openstack_node_ip):
        openstack_node_name = self.get_openstack_nodename(openstack_node_ip)
        return openstack_node_name

    # Start the node instance
    def start_instances(self, node):
        try:
            runcommand.invoke("openstack server start %s" % (node))
            logging.info("Instance: " + str(node) + " started")
        except Exception as e:
            logging.error(
                "Failed to start node instance %s. Encountered following "
                "exception: %s." % (node, e)
            )
            raise RuntimeError()

    # Stop the node instance
    def stop_instances(self, node):
        try:
            runcommand.invoke("openstack server stop %s" % (node))
            logging.info("Instance: " + str(node) + " stopped")
        except Exception as e:
            logging.error(
                "Failed to stop node instance %s. Encountered following "
                "exception: %s." % (node, e)
            )
            raise RuntimeError()

    # Reboot the node instance
    def reboot_instances(self, node):
        try:
            runcommand.invoke("openstack server reboot --soft %s" % (node))
            logging.info("Instance: " + str(node) + " rebooted")
        except Exception as e:
            logging.error(
                "Failed to reboot node instance %s. Encountered following "
                "exception: %s." % (node, e)
            )
            raise RuntimeError()

    # Wait until the node instance is running
    def wait_until_running(self, node, timeout, affected_node):
        start_time = time.time()
        instance_status= self.get_instance_status(node, "ACTIVE", timeout)
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("running", end_time - start_time)
        return instance_status

    # Wait until the node instance is stopped
    def wait_until_stopped(self, node, timeout, affected_node):
        start_time = time.time()
        instance_status = self.get_instance_status(node, "SHUTOFF", timeout)
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("stopped", end_time - start_time)
        return instance_status

    # Get instance status
    def get_instance_status(self, node, expected_status, timeout):
        i = 0
        sleeper = 1
        while i <= timeout:
            instStatus = runcommand.invoke(
                "openstack server show %s | tr -d ' ' |"
                "grep '^|status' |"
                "cut -d '|' -f3 | tr -d '\n'" % (node)
            )
            logging.info("instance status is %s" % (instStatus))
            logging.info("expected status is %s" % (expected_status))
            if instStatus.strip() == expected_status:
                logging.info(
                    "instance status has reached desired status %s" % (instStatus)
                )
                return True
            time.sleep(sleeper)
            i += sleeper
        return False

    # Get the openstack instance name
    def get_openstack_nodename(self, os_node_ip):
        server_list = runcommand.invoke(
            "openstack server list | grep %s" % (os_node_ip)
        )
        list_of_servers = server_list.split("\n")
        for item in list_of_servers:
            items = item.split("|")
            counter = 0
            for i in items:
                if i.strip() != "" and counter == 2:
                    node_name = i.strip()
                    logging.info("Openstack node name is %s " % (node_name))
                    counter += 1
                    continue
                item_list = i.split("=")
                if len(item_list) == 2 and item_list[-1].strip() == os_node_ip:
                    return node_name
                counter += 1


# krkn_lib
class openstack_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes,node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus ):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.openstackcloud = OPENSTACKCLOUD()
        self.node_action_kube_check = node_action_kube_check
    
    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_start_scenario injection")
                logging.info("Starting the node %s" % (node))
                openstack_node_ip = self.kubecli.get_node_ip(node)
                openstack_node_name = self.openstackcloud.get_instance_id(openstack_node_ip)
                self.openstackcloud.start_instances(openstack_node_name)
                self.openstackcloud.wait_until_running(openstack_node_name, timeout, affected_node)
                if self.node_action_kube_check:
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info("Node with instance ID: %s is in running state" % (node))
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following "
                    "exception: %s. Test Failed" % (e)
                )
                logging.error("node_start_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_stop_scenario injection")
                logging.info("Stopping the node %s " % (node))
                openstack_node_ip = self.kubecli.get_node_ip(node)
                openstack_node_name = self.openstackcloud.get_instance_id(openstack_node_ip)
                self.openstackcloud.stop_instances(openstack_node_name)
                self.openstackcloud.wait_until_stopped(openstack_node_name, timeout, affected_node)
                logging.info("Node with instance name: %s is in stopped state" % (node))
                if self.node_action_kube_check:
                    nodeaction.wait_for_not_ready_status(node, timeout, self.kubecli, affected_node)
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed" % (e)
                )
                logging.error("node_stop_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout, soft_reboot=False):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_reboot_scenario injection")
                logging.info("Rebooting the node %s" % (node))
                openstack_node_ip = self.kubecli.get_node_ip(node)
                openstack_node_name = self.openstackcloud.get_instance_id(openstack_node_ip)
                self.openstackcloud.reboot_instances(openstack_node_name)
                if self.node_action_kube_check:
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info("Node with instance name: %s has been rebooted" % (node))
                logging.info("node_reboot_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to start the node
    def helper_node_start_scenario(self, instance_kill_count, node_ip, timeout):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node_ip)
            try:
                logging.info("Starting helper_node_start_scenario injection")
                openstack_node_name = self.openstackcloud.get_openstack_nodename(
                    node_ip.strip()
                )
                logging.info("Starting the helper node %s" % (openstack_node_name))
                self.openstackcloud.start_instances(openstack_node_name)
                self.openstackcloud.wait_until_running(openstack_node_name, timeout, affected_node)
                logging.info("Helper node with IP: %s is in running state" % (node_ip))
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following "
                    "exception: %s. Test Failed" % (e)
                )
                logging.error("helper_node_start_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to stop the node
    def helper_node_stop_scenario(self, instance_kill_count, node_ip, timeout):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node_ip)
            try:
                logging.info("Starting helper_node_stop_scenario injection")
                openstack_node_name = self.openstackcloud.get_openstack_nodename(
                    node_ip.strip()
                )
                logging.info("Stopping the helper node %s " % (openstack_node_name))
                self.openstackcloud.stop_instances(openstack_node_name)
                self.openstackcloud.wait_until_stopped(openstack_node_name, timeout, affected_node)
                logging.info("Helper node with IP: %s is in stopped state" % (node_ip))
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed" % (e)
                )
                logging.error("helper_node_stop_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    def helper_node_service_status(self, node_ip, service, ssh_private_key, timeout):
        try:
            logging.info("Checking service status on the helper node")
            nodeaction.check_service_status(
                node_ip.strip(), service, ssh_private_key, timeout
            )
            logging.info("Service status checked on %s" % (node_ip))
            logging.info("Check service status is successfully injected!")
        except Exception as e:
            logging.error(
                "Failed to check service status. Encountered following exception:"
                " %s. Test Failed" % (e)
            )
            logging.error("helper_node_service_status injection failed!")

            raise RuntimeError()
