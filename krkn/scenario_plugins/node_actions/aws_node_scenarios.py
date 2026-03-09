import sys
import time
import boto3
import logging
import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

class AWS:
    def __init__(self):
        self.boto_client = boto3.client("ec2")
        self.boto_resource = boto3.resource("ec2")
        self.boto_instance = self.boto_resource.Instance("id")

    # Get the instance ID of the node
    def get_instance_id(self, node):
        instance = self.boto_client.describe_instances(Filters=[{"Name": "private-dns-name", "Values": [node]}])
        if len(instance['Reservations']) == 0:
            node = node[3:].replace('-','.')
            instance = self.boto_client.describe_instances(Filters=[{"Name": "private-ip-address", "Values": [node]}])
        return instance[
            "Reservations"
        ][0]["Instances"][0]["InstanceId"]

    # Start the node instance
    def start_instances(self, instance_id):
        try:
            self.boto_client.start_instances(InstanceIds=[instance_id])
            logging.info("EC2 instance: " + str(instance_id) + " started")
        except Exception as e:
            logging.error(
                "Failed to start node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            raise RuntimeError()

    # Stop the node instance
    def stop_instances(self, instance_id):
        try:
            self.boto_client.stop_instances(InstanceIds=[instance_id])
            logging.info("EC2 instance: " + str(instance_id) + " stopped")
        except Exception as e:
            logging.error(
                "Failed to stop node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            raise RuntimeError()

    # Terminate the node instance
    def terminate_instances(self, instance_id):
        try:
            self.boto_client.terminate_instances(InstanceIds=[instance_id])
            logging.info("EC2 instance: " + str(instance_id) + " terminated")
        except Exception as e:
            logging.error(
                "Failed to terminate node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            raise RuntimeError()

    # Reboot the node instance
    def reboot_instances(self, instance_id):
        try:
            self.boto_client.reboot_instances(InstanceIds=[instance_id])
            logging.info("EC2 instance " + str(instance_id) + " rebooted")
        except Exception as e:
            logging.error(
                "Failed to reboot node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )
            raise RuntimeError()

    # Below functions poll EC2.Client.describe_instances() every 15 seconds
    # until a successful state is reached. An error is returned after 40 failed checks
    # Setting timeout for consistency with other cloud functions
    # Wait until the node instance is running
    def wait_until_running(self, instance_id, timeout=600, affected_node=None, poll_interval=15):
        try:
            start_time = time.time()
            if timeout > 0:
                max_attempts = max(1, int(timeout / poll_interval))
            else:
                max_attempts = 40

            self.boto_instance.wait_until_running(
                InstanceIds=[instance_id],
                WaiterConfig={
                    'Delay': poll_interval,
                    'MaxAttempts': max_attempts
                }
            )
            end_time = time.time()
            if affected_node:
                affected_node.set_affected_node_status("running", end_time - start_time)
            return True
        except Exception as e:
            logging.error(
                "Failed to get status waiting for %s to be running %s"
                % (instance_id, e)
            )
            return False

    # Wait until the node instance is stopped
    def wait_until_stopped(self, instance_id, timeout=600, affected_node= None, poll_interval=15):
        try:
            start_time = time.time()
            if timeout > 0:
                max_attempts = max(1, int(timeout / poll_interval))
            else:
                max_attempts = 40

            self.boto_instance.wait_until_stopped(
                InstanceIds=[instance_id],
                WaiterConfig={
                    'Delay': poll_interval,
                    'MaxAttempts': max_attempts
                }
            )
            end_time = time.time()
            if affected_node:
                affected_node.set_affected_node_status("stopped", end_time - start_time)
            return True
        except Exception as e:
            logging.error(
                "Failed to get status waiting for %s to be stopped %s"
                % (instance_id, e)
            )
            return False

    # Wait until the node instance is terminated
    def wait_until_terminated(self, instance_id, timeout=600, affected_node= None, poll_interval=15):
        try:
            start_time = time.time()
            if timeout > 0:
                max_attempts = max(1, int(timeout / poll_interval))
            else:
                max_attempts = 40

            self.boto_instance.wait_until_terminated(
                InstanceIds=[instance_id],
                WaiterConfig={
                    'Delay': poll_interval,
                    'MaxAttempts': max_attempts
                }
            )
            end_time = time.time()
            if affected_node:
                affected_node.set_affected_node_status("terminated", end_time - start_time)
            return True
        except Exception as e:
            logging.error(
                "Failed to get status waiting for %s to be terminated %s"
                % (instance_id, e)
            )
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
                "Make sure you have aws cli configured on the host and set for the region of your vpc/subnet"
                % (e)
            )

            raise RuntimeError()
        return acl_id

    # Replace network acl association
    def replace_network_acl_association(self, association_id, acl_id):
        try:
            logging.info("Replacing the network acl associated with the subnet")
            status = self.boto_client.replace_network_acl_association(
                AssociationId=association_id, NetworkAclId=acl_id
            )
            logging.info(status)
            new_association_id = status["NewAssociationId"]
        except Exception as e:
            logging.error("Failed to replace network acl association: %s" % (e))

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
                "Make sure you have aws cli configured on the host and set for the region of your vpc/subnet"
                % (e)
            )

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

            raise RuntimeError()

    # Detach volume
    def detach_volumes(self, volumes_ids: list):
        for volume in volumes_ids:
            try:
                self.boto_client.detach_volume(VolumeId=volume, Force=True)
            except Exception as e:
                logging.error(
                    "Detaching volume %s failed with exception: %s"
                    % (volume, e)
                )

    # Attach volume
    def attach_volume(self, attachment: dict):
        try:
            if self.get_volume_state(attachment["VolumeId"]) == "in-use":
                logging.info(
                    "Volume %s is already in use." % attachment["VolumeId"]
                )
                return
            logging.info(
                "Attaching the %s volumes to instance %s."
                % (attachment["VolumeId"], attachment["InstanceId"])
            )
            self.boto_client.attach_volume(
                InstanceId=attachment["InstanceId"],
                Device=attachment["Device"],
                VolumeId=attachment["VolumeId"]
            )
        except Exception as e:
            logging.error(
                "Failed attaching disk %s to the %s instance. "
                "Encountered following exception: %s"
                % (attachment['VolumeId'], attachment['InstanceId'], e)
            )
            raise RuntimeError()

    # Get IDs of node volumes
    def get_volumes_ids(self, instance_id: list):
        response = self.boto_client.describe_instances(InstanceIds=instance_id)
        instance_attachment_details = response["Reservations"][0]["Instances"][0]["BlockDeviceMappings"]
        root_volume_device_name = self.get_root_volume_id(instance_id)
        volume_ids = []
        for device in instance_attachment_details:
            if device["DeviceName"] != root_volume_device_name:
                volume_id = device["Ebs"]["VolumeId"]
                volume_ids.append(volume_id)
        return volume_ids

    # Get volumes attachment details
    def get_volume_attachment_details(self, volume_ids: list):
        response = self.boto_client.describe_volumes(VolumeIds=volume_ids)
        volumes_details = response["Volumes"]
        return volumes_details

    # Get root volume
    def get_root_volume_id(self, instance_id):
        instance_id = instance_id[0]
        instance = self.boto_resource.Instance(instance_id)
        root_volume_id = instance.root_device_name
        return root_volume_id

    # Get volume state
    def get_volume_state(self, volume_id: str):
        volume = self.boto_resource.Volume(volume_id)
        state = volume.state
        return state

# krkn_lib
class aws_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes, node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.aws = AWS()
        self.node_action_kube_check = node_action_kube_check

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_start_scenario injection")
                instance_id = self.aws.get_instance_id(node)
                affected_node.node_id = instance_id
                logging.info(
                    "Starting the node %s with instance ID: %s " % (node, instance_id)
                )
                self.aws.start_instances(instance_id)
                self.aws.wait_until_running(instance_id, timeout=timeout, affected_node=affected_node, poll_interval=poll_interval)
                if self.node_action_kube_check: 
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(
                    "Node with instance ID: %s is in running state" % (instance_id)
                )
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
                instance_id = self.aws.get_instance_id(node)
                affected_node.node_id = instance_id
                logging.info(
                    "Stopping the node %s with instance ID: %s " % (node, instance_id)
                )
                self.aws.stop_instances(instance_id)
                self.aws.wait_until_stopped(instance_id, timeout=timeout, affected_node=affected_node, poll_interval=poll_interval)
                logging.info(
                    "Node with instance ID: %s is in stopped state" % (instance_id)
                )
                if self.node_action_kube_check: 
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node=affected_node)
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed" % (e)
                )
                logging.error("node_stop_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_termination_scenario injection")
                instance_id = self.aws.get_instance_id(node)
                affected_node.node_id = instance_id
                logging.info(
                    "Terminating the node %s with instance ID: %s "
                    % (node, instance_id)
                )
                self.aws.terminate_instances(instance_id)
                self.aws.wait_until_terminated(instance_id, timeout=timeout, affected_node=affected_node, poll_interval=poll_interval)
                for _ in range(timeout):
                    if node not in self.kubecli.list_nodes():
                        break
                    time.sleep(1)
                if node in self.kubecli.list_nodes():
                    raise Exception("Node could not be terminated")
                logging.info(
                    "Node with instance ID: %s has been terminated" % (instance_id)
                )
                logging.info("node_termination_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to terminate node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_termination_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout, soft_reboot=False):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_reboot_scenario injection" + str(node))
                instance_id = self.aws.get_instance_id(node)
                affected_node.node_id = instance_id
                logging.info(
                    "Rebooting the node %s with instance ID: %s " % (node, instance_id)
                )
                self.aws.reboot_instances(instance_id)
                if self.node_action_kube_check: 
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(
                    "Node with instance ID: %s has been rebooted" % (instance_id)
                )
                logging.info("node_reboot_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Get volume attachment info
    def get_disk_attachment_info(self, instance_kill_count, node):
        for _ in range(instance_kill_count):
            try:
                logging.info("Obtaining disk attachment information")
                instance_id = (self.aws.get_instance_id(node)).split()
                volumes_ids = self.aws.get_volumes_ids(instance_id)
                if volumes_ids:
                    vol_attachment_details = self.aws.get_volume_attachment_details(
                        volumes_ids
                    )
                    return vol_attachment_details
                return
            except Exception as e:
                logging.error(
                    "Failed to obtain disk attachment information of %s node. "
                    "Encounteres following exception: %s." % (node, e)
                )
                raise RuntimeError()

    # Node scenario to detach the volume
    def disk_detach_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting disk_detach_scenario injection")
                instance_id = (self.aws.get_instance_id(node)).split()
                volumes_ids = self.aws.get_volumes_ids(instance_id)
                logging.info(
                    "Detaching the %s volumes from instance %s "
                    % (volumes_ids, node)
                )
                self.aws.detach_volumes(volumes_ids)
            except Exception as e:
                logging.error(
                    "Failed to detach disk from %s node. Encountered following"
                    "exception: %s." % (node, e)
                )
                logging.debug("")
                raise RuntimeError()

    # Node scenario to attach the volume
    def disk_attach_scenario(self, instance_kill_count, attachment_details, timeout):
        for _ in range(instance_kill_count):
            for attachment in attachment_details:
                self.aws.attach_volume(attachment["Attachments"][0])
