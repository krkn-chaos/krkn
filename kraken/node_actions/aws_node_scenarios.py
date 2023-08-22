import sys
import time
import boto3
import logging
import kraken.node_actions.common_node_functions as nodeaction
from kraken.node_actions.abstract_node_scenarios import abstract_node_scenarios
from krkn_lib.k8s import KrknKubernetes

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
        try:
            self.boto_client.start_instances(InstanceIds=[instance_id])
            logging.info("EC2 instance: " + str(instance_id) + " started")
        except Exception as e:
            logging.error(
                "Failed to start node instance %s. Encountered following " "exception: %s." % (instance_id, e)
            )
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()

    # Stop the node instance
    def stop_instances(self, instance_id):
        try:
            self.boto_client.stop_instances(InstanceIds=[instance_id])
            logging.info("EC2 instance: " + str(instance_id) + " stopped")
        except Exception as e:
            logging.error("Failed to stop node instance %s. Encountered following " "exception: %s." % (instance_id, e))
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()

    # Terminate the node instance
    def terminate_instances(self, instance_id):
        try:
            self.boto_client.terminate_instances(InstanceIds=[instance_id])
            logging.info("EC2 instance: " + str(instance_id) + " terminated")
        except Exception as e:
            logging.error(
                "Failed to terminate node instance %s. Encountered following " "exception: %s." % (instance_id, e)
            )
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()

    # Reboot the node instance
    def reboot_instances(self, instance_id):
        try:
            self.boto_client.reboot_instances(InstanceIds=[instance_id])
            logging.info("EC2 instance " + str(instance_id) + " rebooted")
        except Exception as e:
            logging.error(
                "Failed to reboot node instance %s. Encountered following " "exception: %s." % (instance_id, e)
            )
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()

    # Below functions poll EC2.Client.describe_instances() every 15 seconds
    # until a successful state is reached. An error is returned after 40 failed checks
    # Setting timeout for consistency with other cloud functions
    # Wait until the node instance is running
    def wait_until_running(self, instance_id, timeout=600):
        try:
            self.boto_instance.wait_until_running(InstanceIds=[instance_id])
            return True
        except Exception as e:
            logging.error("Failed to get status waiting for %s to be running %s" % (instance_id, e))
            return False

    # Wait until the node instance is stopped
    def wait_until_stopped(self, instance_id, timeout=600):
        try:
            self.boto_instance.wait_until_stopped(InstanceIds=[instance_id])
            return True
        except Exception as e:
            logging.error("Failed to get status waiting for %s to be stopped %s" % (instance_id, e))
            return False

    # Wait until the node instance is terminated
    def wait_until_terminated(self, instance_id, timeout=600):
        try:
            self.boto_instance.wait_until_terminated(InstanceIds=[instance_id])
            return True
        except Exception as e:
            logging.error("Failed to get status waiting for %s to be terminated %s" % (instance_id, e))
            return False

    # Creates a deny network acl and returns the id
    def create_default_network_acl(self, vpc_id):
        try:
            logging.info("Trying to create a default deny network acl")
            response = self.boto_client.create_network_acl(VpcId=vpc_id)
            acl_id = response["NetworkAcl"]["NetworkAclId"]
            logging.info("Created a network acl, id=%s" % acl_id)
        except Exception as e:
            logging.error(
                "Failed to create the default network_acl: %s"
                "Make sure you have aws cli configured on the host and set for the region of your vpc/subnet" % (e)
            )
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()
        return acl_id

    # Replace network acl association
    def replace_network_acl_association(self, association_id, acl_id):
        try:
            logging.info("Replacing the network acl associated with the subnet")
            status = self.boto_client.replace_network_acl_association(AssociationId=association_id, NetworkAclId=acl_id)
            logging.info(status)
            new_association_id = status["NewAssociationId"]
        except Exception as e:
            logging.error("Failed to replace network acl association: %s" % (e))
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()
        return new_association_id

    # Describe network acl
    def describe_network_acls(self, vpc_id, subnet_id):
        try:
            response = self.boto_client.describe_network_acls(
                Filters=[
                    {"Name": "vpc-id", "Values": [vpc_id]},
                    {"Name": "association.subnet-id", "Values": [subnet_id]},
                ]
            )
        except Exception as e:
            logging.error(
                "Failed to describe network acl: %s."
                "Make sure you have aws cli configured on the host and set for the region of your vpc/subnet" % (e)
            )
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()
        associations = response["NetworkAcls"][0]["Associations"]
        # grab the current network_acl in use
        original_acl_id = response["NetworkAcls"][0]["Associations"][0]["NetworkAclId"]
        return associations, original_acl_id

    # Delete network acl
    def delete_network_acl(self, acl_id):
        try:
            logging.info("Deleting the network acl: %s" % (acl_id))
            self.boto_client.delete_network_acl(NetworkAclId=acl_id)
        except Exception as e:
            logging.error(
                "Failed to delete network_acl %s: %s"
                "Make sure you have aws cli configured on the host and set for the region of your vpc/subnet"
                % (acl_id, e)
            )
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()

# krkn_lib
class aws_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes):
        super().__init__(kubecli)
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
                nodeaction.wait_for_ready_status(node, timeout, self.kubecli)
                logging.info("Node with instance ID: %s is in running state" % (instance_id))
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following " "exception: %s. Test Failed" % (e)
                )
                logging.error("node_start_scenario injection failed!")
                # removed_exit
                # sys.exit(1)
                raise RuntimeError()

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
                nodeaction.wait_for_unknown_status(node, timeout, self.kubecli)
            except Exception as e:
                logging.error("Failed to stop node instance. Encountered following exception: %s. " "Test Failed" % (e))
                logging.error("node_stop_scenario injection failed!")
                # removed_exit
                # sys.exit(1)
                raise RuntimeError()

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
                    if node not in self.kubecli.list_nodes():
                        break
                    time.sleep(1)
                if node in self.kubecli.list_nodes():
                    raise Exception("Node could not be terminated")
                logging.info("Node with instance ID: %s has been terminated" % (instance_id))
                logging.info("node_termination_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to terminate node instance. Encountered following exception:" " %s. Test Failed" % (e)
                )
                logging.error("node_termination_scenario injection failed!")
                # removed_exit
                # sys.exit(1)
                raise RuntimeError()

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_reboot_scenario injection" + str(node))
                instance_id = self.aws.get_instance_id(node)
                logging.info("Rebooting the node %s with instance ID: %s " % (node, instance_id))
                self.aws.reboot_instances(instance_id)
                nodeaction.wait_for_unknown_status(node, timeout, self.kubecli)
                nodeaction.wait_for_ready_status(node, timeout, self.kubecli)
                logging.info("Node with instance ID: %s has been rebooted" % (instance_id))
                logging.info("node_reboot_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:" " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")
                # removed_exit
                # sys.exit(1)
                raise RuntimeError()
