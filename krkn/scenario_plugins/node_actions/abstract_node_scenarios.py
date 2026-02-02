import sys
import logging
import time
import krkn.invoke.command as runcommand
import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

# krkn_lib
class abstract_node_scenarios:
    kubecli: KrknKubernetes
    affected_nodes_status: AffectedNodeStatus
    node_action_kube_check: bool

    def __init__(self, kubecli: KrknKubernetes, node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus):
        self.kubecli = kubecli
        self.affected_nodes_status = affected_nodes_status
        self.node_action_kube_check = node_action_kube_check

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        pass

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout, poll_interval):
        pass

    # Node scenario to stop and then start the node
    def node_stop_start_scenario(self, instance_kill_count, node, timeout, duration, poll_interval):
        logging.info("Starting node_stop_start_scenario injection")
        self.node_stop_scenario(instance_kill_count, node, timeout, poll_interval)
        logging.info("Waiting for %s seconds before starting the node" % (duration))
        time.sleep(duration)
        self.node_start_scenario(instance_kill_count, node, timeout, poll_interval)
        self.affected_nodes_status.merge_affected_nodes()
        logging.info("node_stop_start_scenario has been successfully injected!")

    def helper_node_stop_start_scenario(self, instance_kill_count, node, timeout):
        logging.info("Starting helper_node_stop_start_scenario injection")
        self.helper_node_stop_scenario(instance_kill_count, node, timeout)
        self.helper_node_start_scenario(instance_kill_count, node, timeout)
        logging.info("helper_node_stop_start_scenario has been successfully injected!")

    # Node scenario to detach and attach the disk
    def node_disk_detach_attach_scenario(self, instance_kill_count, node, timeout, duration):
        logging.info("Starting disk_detach_attach_scenario injection")
        disk_attachment_details = self.get_disk_attachment_info(instance_kill_count, node)
        if disk_attachment_details:
            self.disk_detach_scenario(instance_kill_count, node, timeout)
            logging.info("Waiting for %s seconds before attaching the disk" % (duration))
            time.sleep(duration)
            self.disk_attach_scenario(instance_kill_count, disk_attachment_details, timeout)
            logging.info("node_disk_detach_attach_scenario has been successfully injected!")
        else:
            logging.error("Node %s has only root disk attached" % (node))
            logging.error("node_disk_detach_attach_scenario failed!")

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout, poll_interval):
        pass

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout, soft_reboot=False):
        pass

    # Node scenario to stop the kubelet
    def stop_kubelet_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting stop_kubelet_scenario injection")
                logging.info("Stopping the kubelet of the node %s" % (node))
                runcommand.run(
                    "oc debug node/" + node + " -- chroot /host systemctl stop kubelet"
                )
                nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
                
                logging.info("The kubelet of the node %s has been stopped" % (node))
                logging.info("stop_kubelet_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to stop the kubelet of the node. Encountered following "
                    "exception: %s. Test Failed" % (e)
                )
                logging.error("stop_kubelet_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to stop and start the kubelet
    def stop_start_kubelet_scenario(self, instance_kill_count, node, timeout):
        logging.info("Starting stop_start_kubelet_scenario injection")
        self.stop_kubelet_scenario(instance_kill_count, node, timeout)
        self.node_reboot_scenario(instance_kill_count, node, timeout)
        self.affected_nodes_status.merge_affected_nodes()
        logging.info("stop_start_kubelet_scenario has been successfully injected!")

    # Node scenario to restart the kubelet
    def restart_kubelet_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting restart_kubelet_scenario injection")
                logging.info("Restarting the kubelet of the node %s" % (node))
                runcommand.run(
                    "oc debug node/"
                    + node
                    + " -- chroot /host systemctl restart kubelet &"
                )
                nodeaction.wait_for_ready_status(node, timeout, self.kubecli,affected_node)
                logging.info("The kubelet of the node %s has been restarted" % (node))
                logging.info("restart_kubelet_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to restart the kubelet of the node. Encountered following "
                    "exception: %s. Test Failed" % (e)
                )
                logging.error("restart_kubelet_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to crash the node
    def node_crash_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_crash_scenario injection")
                logging.info("Crashing the node %s" % (node))
                runcommand.run(
                    "oc debug node/" + node + " -- chroot /host "
                    "dd if=/dev/urandom of=/proc/sysrq-trigger"
                )
                logging.info("node_crash_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to crash the node. Encountered following exception: %s. "
                    "Test Failed" % (e)
                )
                logging.error("node_crash_scenario injection failed!")
                return 1

    # Node scenario to check service status on helper node
    def node_service_status(self, node, service, ssh_private_key, timeout):
        pass

    # Node Scenario to block all inbound and outbound traffic to a specific node
    # Currently only configured for azure
    def node_block_scenario(self, instance_kill_count, node, timeout, duration):
        pass