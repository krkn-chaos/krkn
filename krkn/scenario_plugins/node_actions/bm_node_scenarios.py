import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
import logging
import openshift as oc
import pyipmi
import pyipmi.interfaces
import time
import traceback
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus
from krkn_lib.utils import get_random_string

class BM:
    def __init__(self, bm_info, user, passwd):
        self.user = user
        self.passwd = passwd
        self.bm_info = bm_info

    def get_node_object(self, node_name):
        with oc.project("openshift-machine-api"):
            return oc.selector("node/" + node_name).object()

    def get_bm_disks(self, node_name):
        if (
            self.bm_info is not None
            and node_name in self.bm_info
            and "disks" in self.bm_info[node_name]
        ):
            return self.bm_info[node_name]["disks"]
        else:
            return []


    # Get the ipmi or other BMC address of the baremetal node
    def get_bmc_addr(self, node_name):
        # Addresses in the config get higher priority.
        if (
            self.bm_info is not None
            and node_name in self.bm_info
            and "bmc_addr" in self.bm_info[node_name]
        ):
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
                raise RuntimeError(
                    'BMC addr empty for node "%s". Either fix the BMH object,'
                    " or specify the address in the scenario config" % node_name
                )
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
            raise RuntimeError(
                "Missing IPMI BMI user and/or password for baremetal cloud. "
                "Please specify either a global or per-machine user and pass"
            )

        # Establish connection
        interface = pyipmi.interfaces.create_interface(
            "ipmitool", interface_type="lanplus"
        )

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
    def wait_until_running(self, bmc_addr, node_name, affected_node):
        start_time = time.time()
        while (
            not self.get_ipmi_connection(bmc_addr, node_name)
            .get_chassis_status()
            .power_on
        ):
            time.sleep(1)
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("running", end_time - start_time)

    # Wait until the node instance is stopped
    def wait_until_stopped(self, bmc_addr, node_name, affected_node):
        start_time = time.time()
        while (
            self.get_ipmi_connection(bmc_addr, node_name).get_chassis_status().power_on
        ):
            time.sleep(1)
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("stopped", end_time - start_time)


# krkn_lib
class bm_node_scenarios(abstract_node_scenarios):
    def __init__(self, bm_info, user, passwd, kubecli: KrknKubernetes,node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.bm = BM(bm_info, user, passwd)
        self.node_action_kube_check = node_action_kube_check

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_start_scenario injection")
                bmc_addr = self.bm.get_bmc_addr(node)
                affected_node.node_id = bmc_addr
                logging.info(
                    "Starting the node %s with bmc address: %s " % (node, bmc_addr)
                )
                self.bm.start_instances(bmc_addr, node)
                self.bm.wait_until_running(bmc_addr, node, affected_node)
                if self.node_action_kube_check: 
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(
                    "Node with bmc address: %s is in running state" % (bmc_addr)
                )
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following "
                    "exception: %s. Test Failed. Most errors are caused by "
                    "an incorrect ipmi address or login" % (e)
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
                bmc_addr = self.bm.get_bmc_addr(node)
                affected_node.node_id = bmc_addr
                logging.info(
                    "Stopping the node %s with bmc address: %s " % (node, bmc_addr)
                )
                self.bm.stop_instances(bmc_addr, node)
                self.bm.wait_until_stopped(bmc_addr, node, affected_node)
                logging.info(
                    "Node with bmc address: %s is in stopped state" % (bmc_addr)
                )
                if self.node_action_kube_check: 
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed. Most errors are caused by "
                    "an incorrect ipmi address or login" % (e)
                )
                logging.error("node_stop_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout, poll_interval):
        logging.info("Node termination scenario is not supported on baremetal")

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout, soft_reboot=False):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_reboot_scenario injection")
                bmc_addr = self.bm.get_bmc_addr(node)
                logging.info("BMC Addr: %s" % (bmc_addr))
                logging.info(
                    "Rebooting the node %s with bmc address: %s " % (node, bmc_addr)
                )
                self.bm.reboot_instances(bmc_addr, node)
                if self.node_action_kube_check: 
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info("Node with bmc address: %s has been rebooted" % (bmc_addr))
                logging.info("node_reboot_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:"
                    " %s. Test Failed. Most errors are caused by "
                    "an incorrect ipmi address or login" % (e)
                )
                traceback.print_exc()
                logging.error("node_reboot_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    def node_disk_detach_attach_scenario(self, instance_kill_count, node, timeout, duration):
        logging.info("Starting disk_detach_attach_scenario injection")
        disk_attachment_details = self.get_disk_attachment_info(instance_kill_count, node)
        if disk_attachment_details:
            self.disk_detach_scenario(instance_kill_count, node, disk_attachment_details, timeout)
            logging.info("Waiting for %s seconds before attaching the disk" % (duration))
            time.sleep(duration)
            self.disk_attach_scenario(instance_kill_count, node, disk_attachment_details)
            logging.info("node_disk_detach_attach_scenario has been successfully injected!")
        else:
            logging.error("Node %s has only root disk attached" % (node))
            logging.error("node_disk_detach_attach_scenario failed!")


    # Get volume attachment info
    def get_disk_attachment_info(self, instance_kill_count, node):
        for _ in range(instance_kill_count):
            try:
                logging.info("Obtaining disk attachment information")
                user_disks= self.bm.get_bm_disks(node)
                disk_pod_name = f"disk-pod-{get_random_string(5)}"
                cmd = '''bootdev=$(lsblk -no PKNAME $(findmnt -no SOURCE /boot)); 
for path in /sys/block/*/device/state; do 
    dev=$(basename $(dirname $(dirname "$path"))); 
    [[ "$dev" != "$bootdev" ]] && echo "$dev"; 
done'''
                pod_command = ["chroot /host /bin/sh -c '" + cmd + "'"]
                disk_response = self.kubecli.exec_command_on_node(
                    node, pod_command, disk_pod_name, "default"
                )
                logging.info("Disk response: %s" % (disk_response))
                node_disks = [disk for disk in disk_response.split("\n") if disk]
                logging.info("Node disks: %s" % (node_disks))
                offline_disks = [disk for disk in user_disks if disk in node_disks]
                return offline_disks if offline_disks else node_disks
            except Exception as e:
                logging.error(
                    "Failed to obtain disk attachment information of %s node. "
                    "Encounteres following exception: %s." % (node, e)
                )
                raise RuntimeError()
            finally:
                self.kubecli.delete_pod(disk_pod_name, "default")

    # Node scenario to detach the volume
    def disk_detach_scenario(self, instance_kill_count, node, disk_attachment_details, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting disk_detach_scenario injection")
                logging.info(
                    "Detaching the %s disks from instance %s "
                    % (disk_attachment_details, node)
                )
                disk_pod_name = f"detach-disk-pod-{get_random_string(5)}"
                detach_disk_command=''
                for disk in disk_attachment_details:
                    detach_disk_command = detach_disk_command + "echo offline > /sys/block/" + disk + "/device/state;"
                pod_command = ["chroot /host /bin/sh -c '" + detach_disk_command + "'"]
                cmd_output = self.kubecli.exec_command_on_node(
                    node, pod_command, disk_pod_name, "default"
                )
                logging.info("Disk command output: %s" % (cmd_output))
                logging.info("Disk %s has been detached from %s node" % (disk_attachment_details, node))
            except Exception as e:
                logging.error(
                    "Failed to detach disk from %s node. Encountered following"
                    "exception: %s." % (node, e)
                )
                logging.debug("")
                raise RuntimeError()
            finally:
                self.kubecli.delete_pod(disk_pod_name, "default")

    # Node scenario to attach the volume
    def disk_attach_scenario(self, instance_kill_count, node, disk_attachment_details):
        for _ in range(instance_kill_count):
            try:
                logging.info(
                    "Attaching the %s disks from instance %s "
                    % (disk_attachment_details, node)
                )
                disk_pod_name = f"attach-disk-pod-{get_random_string(5)}"
                attach_disk_command=''
                for disk in disk_attachment_details:
                    attach_disk_command = attach_disk_command + "echo running > /sys/block/" + disk + "/device/state;"
                pod_command = ["chroot /host /bin/sh -c '" + attach_disk_command + "'"]
                cmd_output = self.kubecli.exec_command_on_node(
                        node, pod_command, disk_pod_name, "default"
                    )
                logging.info("Disk command output: %s" % (cmd_output))
                logging.info("Disk %s has been attached to %s node" % (disk_attachment_details, node))
            except Exception as e:
                logging.error(
                    "Failed to attach disk to %s node. Encountered following"
                    "exception: %s." % (node, e)
                )
                logging.debug("")
                raise RuntimeError()
            finally:
                self.kubecli.delete_pod(disk_pod_name, "default")
