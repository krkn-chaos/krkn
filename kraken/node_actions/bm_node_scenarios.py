import sys
import time
import openshift as oc
import logging
import kraken.kubernetes.client as kubecli
import kraken.node_actions.common_node_functions as nodeaction
from kraken.node_actions.abstract_node_scenarios import abstract_node_scenarios


class BM:
    def __init__(self, user, passwd):
        this.user = user
        this.passwd = passwd


    # Get the ipmi or other BMC address of the baremetal node
    def get_bmc_addr(self, node_name):
        node = kubecli.get_node_object(node_name)
        provider_id = node..spec.provider_id
        startOfUid = provider_id.rfind('/') # The / before the uid
        startOfName = provider_id.rfind('/', 0, startOfUid) + 1
        bmh_name = provider_id[startOfName:startOfUid]
        bmh_resource_name = 'baremetalhost.metal3.io/' + bmh_name
        bmh_object = oc.selector(bmh_resource_name).object()
        return bmh_object.as_dict()["spec"]["bmc"]["address"]

    def get_ipmi_connection(self, bmc_addr):
        type_position = bmc_addr.find("://")
        if type_position == -1:
            host = bmc_addr
       else:
            host = bmc_addr[type_position + 3:]
        port_position = host.find(":")
        if port_position == -1:
            port = 623
        else:
            port = int(host[port_position + 1:])
            host = host[0:port_position]

        #establish connection
        interface = pyipmi.interfaces.create_interface('ipmitool', interface_type='lan')

        connection = pyipmi.create_connection(interface)

        connection.target = pyipmi.Target(ipmb_address=0x20)
        #connection.target = pyipmi.Target(ipmb_address=0x82, routing=[(0x81,0x20,0),(0x20,0x82,7)])
        connection.session.set_session_type_rmcp(host, port=623)
        connection.session.set_auth_type_user(user, pass)
        connection.session.establish()
        return connection


    # Start the node instance
    def start_instances(self, bmc_addr):
        self.get_ipmi_connection(bmc_addr).chassis_control_power_up()

    # Stop the node instance
    def stop_instances(self, bmc_addr):
        self.get_ipmi_connection(bmc_addr).chassis_control_power_down()

    # Reboot the node instance
    def reboot_instances(self, bmc_addr):
        self.get_ipmi_connection(bmc_addr).chassis_control_power_cycle()

    # Wait until the node instance is running
    def wait_until_running(self, bmc_addr):
        while (self.get_ipmi_connection(bmc_addr).get_chassis_status().power_on == False):
            time.sleep(1)

    # Wait until the node instance is stopped
    def wait_until_stopped(self, bmc_addr):
        while (self.get_ipmi_connection(bmc_addr).get_chassis_status().power_on == True):
            time.sleep(1)


class bm_node_scenarios(abstract_node_scenarios):
    def __init__(self, user, passwd):
        self.bm = BM(user, passwd)

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node_name, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_start_scenario injection")
                bmc_addr = self.bm.get_bmc_addr(node)
                logging.info("Starting the node %s with bmc address: %s " % (node, bmc_addr))
                self.bm.start_instances(bmc_addr)
                self.bm.wait_until_running(bmc_addr)
                nodeaction.wait_for_ready_status(node, timeout)
                logging.info("Node with bmc address: %s is in running state" % (bmc_addr))
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error("Failed to start node instance. Encountered following "
                              "exception: %s. Test Failed" % (e))
                logging.error("node_start_scenario injection failed!")
                sys.exit(1)

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_stop_scenario injection")
                bmc_addr = self.bm.get_bmc_addr(node)
                logging.info("Stopping the node %s with bmc address: %s " % (node, bmc_addr))
                self.bm.stop_instances(bmc_addr)
                self.bm.wait_until_stopped(bmc_addr)
                logging.info("Node with bmc address: %s is in stopped state" % (bmc_addr))
                nodeaction.wait_for_unknown_status(node, timeout)
            except Exception as e:
                logging.error("Failed to stop node instance. Encountered following exception: %s. "
                              "Test Failed" % (e))
                logging.error("node_stop_scenario injection failed!")
                sys.exit(1)

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout):
        logging.info("Node termination scenario is not supported on baremetal")

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_reboot_scenario injection")
                bmc_addr = self.bm.get_bmc_addr(node)
                logging.info("Rebooting the node %s with bmc address: %s " % (node, bmc_addr))
                self.bm.reboot_instances(bmc_addr)
                nodeaction.wait_for_unknown_status(node, timeout)
                nodeaction.wait_for_ready_status(node, timeout)
                logging.info("Node with bmc address: %s has been rebooted" % (bmc_addr))
                logging.info("node_reboot_scenario has been successfuly injected!")
            except Exception as e:
                logging.error("Failed to reboot node instance. Encountered following exception:"
                              " %s. Test Failed" % (e))
                logging.error("node_reboot_scenario injection failed!")
                sys.exit(1)
