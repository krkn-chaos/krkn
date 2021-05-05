import sys
import time
import logging
import kraken.invoke.command as runcommand
import kraken.node_actions.common_node_functions as nodeaction
from kraken.node_actions.abstract_node_scenarios import abstract_node_scenarios


class OPENSTACKCLOUD:
    def __init__(self):
        self.Wait = 30

    # Start the node instance
    def start_instances(self, node):
        runcommand.invoke("openstack server start %s" % (node))
        logging.info("OPENSTACK CLI INFO: Completed instance start action for node %s" % (node))

    # Stop the node instance
    def stop_instances(self, node):
        runcommand.invoke("openstack server stop %s" % (node))
        logging.info("OPENSTACK CLI INFO: Completed instance stop action for node %s" % (node))
        # return action_output

    # Reboot the node instance
    def reboot_instances(self, node):
        runcommand.invoke("openstack server reboot --soft %s" % (node))
        logging.info("OPENSTACK CLI INFO: Completed instance reboot action for node %s" % (node))

    # Wait until the node instance is running
    def wait_until_running(self, node):
        self.get_instance_status(node, "ACTIVE", self.Wait)

    # Wait until the node instance is stopped
    def wait_until_stopped(self, node):
        self.get_instance_status(node, "SHUTOFF", self.Wait)

    # Get instance status
    def get_instance_status(self, node, expected_status, timeout):
        i = 0
        sleeper = 1
        while i <= timeout:
            instStatus = runcommand.invoke(
                "openstack server show %s | tr -d ' ' |" "grep '^|status' |" "cut -d '|' -f3 | tr -d '\n'" % (node)
            )
            logging.info("instance status is %s" % (instStatus))
            logging.info("expected status is %s" % (expected_status))
            if instStatus.strip() == expected_status:
                logging.info("instance status has reached desired status %s" % (instStatus))
                return True
            time.sleep(sleeper)
            i += sleeper

    # Get the openstack instance name
    def get_openstack_nodename(self, os_node_ip):
        server_list = runcommand.invoke("openstack server list | grep %s" % (os_node_ip))
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


class openstack_node_scenarios(abstract_node_scenarios):
    def __init__(self):
        self.openstackcloud = OPENSTACKCLOUD()

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_start_scenario injection")
                logging.info("Starting the node %s" % (node))
                openstack_node_ip = nodeaction.get_node_ip(node)
                openstack_node_name = self.openstackcloud.get_openstack_nodename(openstack_node_ip)
                self.openstackcloud.start_instances(openstack_node_name)
                self.openstackcloud.wait_until_running(openstack_node_name)
                nodeaction.wait_for_ready_status(node, timeout)
                logging.info("Node with instance ID: %s is in running state" % (node))
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following " "exception: %s. Test Failed" % (e)
                )
                logging.error("node_start_scenario injection failed!")
                sys.exit(1)

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_stop_scenario injection")
                logging.info("Stopping the node %s " % (node))
                openstack_node_ip = nodeaction.get_node_ip(node)
                openstack_node_name = self.openstackcloud.get_openstack_nodename(openstack_node_ip)
                self.openstackcloud.stop_instances(openstack_node_name)
                self.openstackcloud.wait_until_stopped(openstack_node_name)
                logging.info("Node with instance name: %s is in stopped state" % (node))
                nodeaction.wait_for_ready_status(node, timeout)
            except Exception as e:
                logging.error("Failed to stop node instance. Encountered following exception: %s. " "Test Failed" % (e))
                logging.error("node_stop_scenario injection failed!")
                sys.exit(1)

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_reboot_scenario injection")
                logging.info("Rebooting the node %s" % (node))
                openstack_node_ip = nodeaction.get_node_ip(node)
                openstack_node_name = self.openstackcloud.get_openstack_nodename(openstack_node_ip)
                self.openstackcloud.reboot_instances(openstack_node_name)
                nodeaction.wait_for_unknown_status(node, timeout)
                nodeaction.wait_for_ready_status(node, timeout)
                logging.info("Node with instance name: %s has been rebooted" % (node))
                logging.info("node_reboot_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:" " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")
                sys.exit(1)

    # Node scenario to start the node
    def helper_node_start_scenario(self, instance_kill_count, node_ip, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting helper_node_start_scenario injection")
                openstack_node_name = self.openstackcloud.get_openstack_nodename(node_ip.strip())
                logging.info("Starting the helper node %s" % (openstack_node_name))
                self.openstackcloud.start_instances(openstack_node_name)
                self.openstackcloud.wait_until_running(openstack_node_name)
                logging.info("Helper node with IP: %s is in running state" % (node_ip))
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following " "exception: %s. Test Failed" % (e)
                )
                logging.error("helper_node_start_scenario injection failed!")
                sys.exit(1)

    # Node scenario to stop the node
    def helper_node_stop_scenario(self, instance_kill_count, node_ip, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting helper_node_stop_scenario injection")
                openstack_node_name = self.openstackcloud.get_openstack_nodename(node_ip.strip())
                logging.info("Stopping the helper node %s " % (openstack_node_name))
                self.openstackcloud.stop_instances(openstack_node_name)
                self.openstackcloud.wait_until_stopped(openstack_node_name)
                logging.info("Helper node with IP: %s is in stopped state" % (node_ip))
            except Exception as e:
                logging.error("Failed to stop node instance. Encountered following exception: %s. " "Test Failed" % (e))
                logging.error("helper_node_stop_scenario injection failed!")
                sys.exit(1)

    def helper_node_service_status(self, node_ip, service, ssh_private_key, timeout):
        try:
            logging.info("Checking service status on the helper node")
            nodeaction.check_service_status(node_ip.strip(), service, ssh_private_key, timeout)
            logging.info("Service status checked on %s" % (node_ip))
            logging.info("Check service status is successfuly injected!")
        except Exception as e:
            logging.error("Failed to check service status. Encountered following exception:" " %s. Test Failed" % (e))
            logging.error("helper_node_service_status injection failed!")
            sys.exit(1)
