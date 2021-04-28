import sys
import time
import boto3
import logging
import kraken.kubernetes.client as kubecli
import kraken.node_actions.common_node_functions as nodeaction
from kraken.node_actions.abstract_node_scenarios import abstract_node_scenarios


class AWS:
    def __init__(self):
        self.boto_client = boto3.client("ec2")
        self.boto_instance = boto3.resource("ec2").Instance("id")

    # Get the instance ID of the node
    def get_instance_id(self, node):
        return self.boto_client.describe_instances(Filters=[{"Name": "private-dns-name", "Values": [node]}])[
            "Reservations"
        ][0]["Instances"][0]["InstanceId"]

    # Start the node instance
    def start_instances(self, instance_id):
        self.boto_client.start_instances(InstanceIds=[instance_id])

    # Stop the node instance
    def stop_instances(self, instance_id):
        self.boto_client.stop_instances(InstanceIds=[instance_id])

    # Terminate the node instance
    def terminate_instances(self, instance_id):
        self.boto_client.terminate_instances(InstanceIds=[instance_id])

    # Reboot the node instance
    def reboot_instances(self, instance_id):
        self.boto_client.reboot_instances(InstanceIds=[instance_id])

    # Wait until the node instance is running
    def wait_until_running(self, instance_id):
        self.boto_instance.wait_until_running(InstanceIds=[instance_id])

    # Wait until the node instance is stopped
    def wait_until_stopped(self, instance_id):
        self.boto_instance.wait_until_stopped(InstanceIds=[instance_id])

    # Wait until the node instance is terminated
    def wait_until_terminated(self, instance_id):
        self.boto_instance.wait_until_terminated(InstanceIds=[instance_id])


class aws_node_scenarios(abstract_node_scenarios):
    def __init__(self):
        self.aws = AWS()

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_start_scenario injection")
                instance_id = self.aws.get_instance_id(node)
                logging.info("Starting the node %s with instance ID: %s " % (node, instance_id))
                self.aws.start_instances(instance_id)
                self.aws.wait_until_running(instance_id)
                nodeaction.wait_for_ready_status(node, timeout)
                logging.info("Node with instance ID: %s is in running state" % (instance_id))
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
                instance_id = self.aws.get_instance_id(node)
                logging.info("Stopping the node %s with instance ID: %s " % (node, instance_id))
                self.aws.stop_instances(instance_id)
                self.aws.wait_until_stopped(instance_id)
                logging.info("Node with instance ID: %s is in stopped state" % (instance_id))
                nodeaction.wait_for_unknown_status(node, timeout)
            except Exception as e:
                logging.error("Failed to stop node instance. Encountered following exception: %s. " "Test Failed" % (e))
                logging.error("node_stop_scenario injection failed!")
                sys.exit(1)

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_termination_scenario injection")
                instance_id = self.aws.get_instance_id(node)
                logging.info("Terminating the node %s with instance ID: %s " % (node, instance_id))
                self.aws.terminate_instances(instance_id)
                self.aws.wait_until_terminated(instance_id)
                for _ in range(timeout):
                    if node not in kubecli.list_nodes():
                        break
                    time.sleep(1)
                if node in kubecli.list_nodes():
                    raise Exception("Node could not be terminated")
                logging.info("Node with instance ID: %s has been terminated" % (instance_id))
                logging.info("node_termination_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to terminate node instance. Encountered following exception:" " %s. Test Failed" % (e)
                )
                logging.error("node_termination_scenario injection failed!")
                sys.exit(1)

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_reboot_scenario injection")
                instance_id = self.aws.get_instance_id(node)
                logging.info("Rebooting the node %s with instance ID: %s " % (node, instance_id))
                self.aws.reboot_instances(instance_id)
                nodeaction.wait_for_unknown_status(node, timeout)
                nodeaction.wait_for_ready_status(node, timeout)
                logging.info("Node with instance ID: %s has been rebooted" % (instance_id))
                logging.info("node_reboot_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:" " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")
                sys.exit(1)
