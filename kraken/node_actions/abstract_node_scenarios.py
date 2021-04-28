import sys
import logging
import kraken.invoke.command as runcommand
import kraken.node_actions.common_node_functions as nodeaction


class abstract_node_scenarios:

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout):
        pass

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout):
        pass

    # Node scenario to stop and then start the node
    def node_stop_start_scenario(self, instance_kill_count, node, timeout):
        logging.info("Starting node_stop_start_scenario injection")
        self.node_stop_scenario(instance_kill_count, node, timeout)
        self.node_start_scenario(instance_kill_count, node, timeout)
        logging.info("node_stop_start_scenario has been successfully injected!")

    def helper_node_stop_start_scenario(self, instance_kill_count, node, timeout):
        logging.info("Starting helper_node_stop_start_scenario injection")
        self.helper_node_stop_scenario(instance_kill_count, node, timeout)
        self.helper_node_start_scenario(instance_kill_count, node, timeout)
        logging.info("helper_node_stop_start_scenario has been successfully injected!")

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout):
        pass

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout):
        pass

    # Node scenario to stop the kubelet
    def stop_kubelet_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting stop_kubelet_scenario injection")
                logging.info("Stopping the kubelet of the node %s" % (node))
                runcommand.run("oc debug node/" + node + " -- chroot /host systemctl stop kubelet")
                nodeaction.wait_for_unknown_status(node, timeout)
                logging.info("The kubelet of the node %s has been stopped" % (node))
                logging.info("stop_kubelet_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to stop the kubelet of the node. Encountered following " "exception: %s. Test Failed" % (e)
                )
                logging.error("stop_kubelet_scenario injection failed!")
                sys.exit(1)

    # Node scenario to stop and start the kubelet
    def stop_start_kubelet_scenario(self, instance_kill_count, node, timeout):
        logging.info("Starting stop_start_kubelet_scenario injection")
        self.stop_kubelet_scenario(instance_kill_count, node, timeout)
        self.node_reboot_scenario(instance_kill_count, node, timeout)
        logging.info("stop_start_kubelet_scenario has been successfully injected!")

    # Node scenario to crash the node
    def node_crash_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_crash_scenario injection")
                logging.info("Crashing the node %s" % (node))
                runcommand.invoke(
                    "oc debug node/" + node + " -- chroot /host " "dd if=/dev/urandom of=/proc/sysrq-trigger"
                )
                logging.info("node_crash_scenario has been successfuly injected!")
            except Exception as e:
                logging.error("Failed to crash the node. Encountered following exception: %s. " "Test Failed" % (e))
                logging.error("node_crash_scenario injection failed!")
                sys.exit(1)

    # Node scenario to check service status on helper node
    def node_service_status(self, node, service, ssh_private_key, timeout):
        pass
