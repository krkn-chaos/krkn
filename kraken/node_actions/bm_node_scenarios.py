import kraken.node_actions.common_node_functions as nodeaction
from kraken.node_actions.abstract_node_scenarios import abstract_node_scenarios
import logging
import openshift as oc
import pyipmi
import pyipmi.interfaces
import sys
import time
import traceback
from krkn_lib.k8s import KrknKubernetes

class BM:
    def __init__(self, bm_info, user, passwd):
        self.user = user
        self.passwd = passwd
        self.bm_info = bm_info

    def get_node_object(self, node_name):
        with oc.project("openshift-machine-api"):
            return oc.selector("node/" + node_name).object()

    # Get the ipmi or other BMC address of the baremetal node
    def get_bmc_addr(self, node_name):
        # Addresses in the config get higher priority.
        if self.bm_info is not None and node_name in self.bm_info and "bmc_addr" in self.bm_info[node_name]:
            return self.bm_info[node_name]["bmc_addr"]

        # Get the bmc addr from the BareMetalHost object.
        with oc.project("openshift-machine-api"):
            logging.info("Getting node with name: %s" % (node_name))
            node = self.get_node_object(node_name)
            provider_id = node.model.spec.providerID
            startOfUid = provider_id.rfind("/")  # The / before the uid
            startOfName = provider_id.rfind("/", 0, startOfUid) + 1
            bmh_name = provider_id[startOfName:startOfUid]
            bmh_resource_name = "baremetalhost.metal3.io/" + bmh_name
            bmh_object = oc.selector(bmh_resource_name).object()
            if len(bmh_object.model.spec.bmc.addr) == 0:
                logging.error(
                    'BMC addr empty for node "%s". Either fix the BMH object,'
                    " or specify the address in the scenario config" % node_name
                )
                sys.exit(1)
            return bmh_object.model.spec.bmc.address

    def get_ipmi_connection(self, bmc_addr, node_name):
        type_position = bmc_addr.find("://")
        if type_position == -1:
            host = bmc_addr
        else:
            host = bmc_addr[type_position + 3 :]
        port_position = host.find(":")
        if port_position == -1:
            port = 623
        else:
            port = int(host[port_position + 1 :])
            host = host[0:port_position]

        # Determine correct username and password
        # If specified, uses device-specific user/pass. Else uses the global one.
        if self.bm_info is not None and node_name in self.bm_info:
            user = self.bm_info[node_name].get("bmc_user", self.user)
            passwd = self.bm_info[node_name].get("bmc_password", self.passwd)
        else:
            user = self.user
            passwd = self.passwd
        if user is None or passwd is None:
            logging.error(
                "Missing IPMI BMI user and/or password for baremetal cloud. "
                "Please specify either a global or per-machine user and pass"
            )
            sys.exit(1)

        # Establish connection
        interface = pyipmi.interfaces.create_interface("ipmitool", interface_type="lanplus")

        connection = pyipmi.create_connection(interface)

        connection.target = pyipmi.Target(ipmb_address=0x20)
        connection.session.set_session_type_rmcp(host, port)
        connection.session.set_auth_type_user(user, passwd)
        connection.session.establish()
        return connection

    # Start the node instance
    def start_instances(self, bmc_addr, node_name):
        self.get_ipmi_connection(bmc_addr, node_name).chassis_control_power_up()

    # Stop the node instance
    def stop_instances(self, bmc_addr, node_name):
        self.get_ipmi_connection(bmc_addr, node_name).chassis_control_power_down()

    # Reboot the node instance
    def reboot_instances(self, bmc_addr, node_name):
        self.get_ipmi_connection(bmc_addr, node_name).chassis_control_power_cycle()

    # Wait until the node instance is running
    def wait_until_running(self, bmc_addr, node_name):
        while not self.get_ipmi_connection(bmc_addr, node_name).get_chassis_status().power_on:
            time.sleep(1)

    # Wait until the node instance is stopped
    def wait_until_stopped(self, bmc_addr, node_name):
        while self.get_ipmi_connection(bmc_addr, node_name).get_chassis_status().power_on:
            time.sleep(1)

# krkn_lib
class bm_node_scenarios(abstract_node_scenarios):
    def __init__(self, bm_info, user, passwd, kubecli: KrknKubernetes):
        super().__init__(kubecli)
        self.bm = BM(bm_info, user, passwd)

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_start_scenario injection")
                bmc_addr = self.bm.get_bmc_addr(node)
                logging.info("Starting the node %s with bmc address: %s " % (node, bmc_addr))
                self.bm.start_instances(bmc_addr, node)
                self.bm.wait_until_running(bmc_addr, node)
                nodeaction.wait_for_ready_status(node, timeout, self.kubecli)
                logging.info("Node with bmc address: %s is in running state" % (bmc_addr))
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following "
                    "exception: %s. Test Failed. Most errors are caused by "
                    "an incorrect ipmi address or login" % (e)
                )
                logging.error("node_start_scenario injection failed!")
                sys.exit(1)

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_stop_scenario injection")
                bmc_addr = self.bm.get_bmc_addr(node)
                logging.info("Stopping the node %s with bmc address: %s " % (node, bmc_addr))
                self.bm.stop_instances(bmc_addr, node)
                self.bm.wait_until_stopped(bmc_addr, node)
                logging.info("Node with bmc address: %s is in stopped state" % (bmc_addr))
                nodeaction.wait_for_unknown_status(node, timeout, self.kubecli)
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed. Most errors are caused by "
                    "an incorrect ipmi address or login" % (e)
                )
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
                logging.info("BMC Addr: %s" % (bmc_addr))
                logging.info("Rebooting the node %s with bmc address: %s " % (node, bmc_addr))
                self.bm.reboot_instances(bmc_addr, node)
                nodeaction.wait_for_unknown_status(node, timeout, self.kubecli)
                nodeaction.wait_for_ready_status(node, timeout, self.kubecli)
                logging.info("Node with bmc address: %s has been rebooted" % (bmc_addr))
                logging.info("node_reboot_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:"
                    " %s. Test Failed. Most errors are caused by "
                    "an incorrect ipmi address or login" % (e)
                )
                traceback.print_exc()
                logging.error("node_reboot_scenario injection failed!")
                sys.exit(1)
