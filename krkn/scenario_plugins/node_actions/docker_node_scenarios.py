import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
import logging
import docker
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

class Docker:
    def __init__(self):
        self.client = docker.from_env()

    def get_container_id(self, node_name):
        container = self.client.containers.get(node_name)
        return container.id

    # Start the node instance
    def start_instances(self, node_name):
        container = self.client.containers.get(node_name)
        container.start()

    # Stop the node instance
    def stop_instances(self, node_name):
        container = self.client.containers.get(node_name)
        container.stop()

    # Reboot the node instance
    def reboot_instances(self, node_name):
        container = self.client.containers.get(node_name)
        container.restart()

    # Terminate the node instance
    def terminate_instances(self, node_name):
        container = self.client.containers.get(node_name)
        container.stop()
        container.remove()


class docker_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes, affected_nodes_status: AffectedNodeStatus):
        super().__init__(kubecli, affected_nodes_status)
        self.docker = Docker()

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_start_scenario injection")
                container_id = self.docker.get_container_id(node)
                logging.info(
                    "Starting the node %s with container ID: %s " % (node, container_id)
                )
                self.docker.start_instances(node)
                nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(
                    "Node with container ID: %s is in running state" % (container_id)
                )
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
    def node_stop_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_stop_scenario injection")
                container_id = self.docker.get_container_id(node)
                logging.info(
                    "Stopping the node %s with container ID: %s " % (node, container_id)
                )
                self.docker.stop_instances(node)
                logging.info(
                    "Node with container ID: %s is in stopped state" % (container_id)
                )
                nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed" % (e)
                )
                logging.error("node_stop_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_termination_scenario injection")
                container_id = self.docker.get_container_id(node)
                logging.info(
                    "Terminating the node %s with container ID: %s "
                    % (node, container_id)
                )
                self.docker.terminate_instances(node)
                logging.info(
                    "Node with container ID: %s has been terminated" % (container_id)
                )
                logging.info("node_termination_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to terminate node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_termination_scenario injection failed!")
                raise e

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_reboot_scenario injection")
                container_id = self.docker.get_container_id(node)
                logging.info(
                    "Rebooting the node %s with container ID: %s "
                    % (node, container_id)
                )
                self.docker.reboot_instances(node)
                nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
                nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(
                    "Node with container ID: %s has been rebooted" % (container_id)
                )
                logging.info("node_reboot_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)
