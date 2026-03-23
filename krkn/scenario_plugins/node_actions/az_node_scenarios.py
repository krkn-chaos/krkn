import time
import os
import logging
import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network.models import SecurityRule, Subnet

from azure.identity import DefaultAzureCredential
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

class Azure:
    def __init__(self):
        logging.info("azure " + str(self))
        # Acquire a credential object using CLI-based authentication.
        credentials = DefaultAzureCredential()
        logger = logging.getLogger("azure")
        logger.setLevel(logging.WARNING)
        subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        self.compute_client = ComputeManagementClient(credentials, subscription_id,logging=logger)
        self.network_client = NetworkManagementClient(credentials, subscription_id,logging=logger)

    # Get the instance ID of the node
    def get_instance_id(self, node_name):
        vm_list = self.compute_client.virtual_machines.list_all()
        for vm in vm_list:
            array = vm.id.split("/")
            if node_name == vm.name:
                resource_group = array[4]
                return vm.name, resource_group
        logging.error("Couldn't find vm with name " + str(node_name))

    # Get the instance ID of the node
    def get_network_interface(self, node_name, resource_group):

        vm = self.compute_client.virtual_machines.get(resource_group, node_name,expand='instanceView')

        for nic in vm.network_profile.network_interfaces:
            nic_name = nic.id.split("/")[-1]
            nic = self.network_client.network_interfaces.get(resource_group, nic_name)
            location = nic.location
            subnet_list = nic.ip_configurations[0].subnet.id.split('/')
            subnet = subnet_list[-1]
            virtual_network = subnet_list[-3]
            network_resource_group = subnet_list[-7]

            private_ip = nic.ip_configurations[0].private_ip_address
            return subnet, virtual_network, private_ip, network_resource_group, location

    # Start the node instance
    def start_instances(self, group_name, vm_name):
        try:
            self.compute_client.virtual_machines.begin_start(group_name, vm_name)
            logging.info("vm name " + str(vm_name) + " started")
        except Exception as e:
            logging.error(
                "Failed to start node instance %s. Encountered following "
                "exception: %s." % (vm_name, e)
            )
            raise RuntimeError()

    # Stop the node instance
    def stop_instances(self, group_name, vm_name):
        try:
            self.compute_client.virtual_machines.begin_power_off(group_name, vm_name)
            logging.info("vm name " + str(vm_name) + " stopped")
        except Exception as e:
            logging.error(
                "Failed to stop node instance %s. Encountered following "
                "exception: %s." % (vm_name, e)
            )
            raise RuntimeError()

    # Terminate the node instance
    def terminate_instances(self, group_name, vm_name):
        try:
            self.compute_client.virtual_machines.begin_delete(group_name, vm_name)
            logging.info("vm name " + str(vm_name) + " terminated")
        except Exception as e:
            logging.error(
                "Failed to terminate node instance %s. Encountered following "
                "exception: %s." % (vm_name, e)
            )

            raise RuntimeError()

    # Reboot the node instance
    def reboot_instances(self, group_name, vm_name):
        try:
            self.compute_client.virtual_machines.begin_restart(group_name, vm_name)
            logging.info("vm name " + str(vm_name) + " rebooted")
        except Exception as e:
            logging.error(
                "Failed to reboot node instance %s. Encountered following "
                "exception: %s." % (vm_name, e)
            )

            raise RuntimeError()

    def get_vm_status(self, resource_group, vm_name):
        statuses = self.compute_client.virtual_machines.instance_view(
            resource_group, vm_name
        ).statuses
        status = len(statuses) >= 2 and statuses[1]
        return status

    # Wait until the node instance is running
    def wait_until_running(self, resource_group, vm_name, timeout, affected_node):
        time_counter = 0
        start_time = time.time()
        status = self.get_vm_status(resource_group, vm_name)
        while status and status.code != "PowerState/running":
            status = self.get_vm_status(resource_group, vm_name)
            logging.info("Vm %s is still not running, sleeping for 5 seconds" % vm_name)
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info("Vm %s is still not ready in allotted time" % vm_name)
                return False
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("running", end_time - start_time)
        return True

    # Wait until the node instance is stopped
    def wait_until_stopped(self, resource_group, vm_name, timeout, affected_node):
        time_counter = 0
        start_time = time.time()
        status = self.get_vm_status(resource_group, vm_name)
        while status and status.code != "PowerState/stopped":
            status = self.get_vm_status(resource_group, vm_name)
            logging.info("Vm %s is still stopping, sleeping for 5 seconds" % vm_name)
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info("Vm %s is still not stopped in allotted time" % vm_name)
                return False
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("stopped", end_time - start_time)
        return True

    # Wait until the node instance is terminated
    def wait_until_terminated(self, resource_group, vm_name, timeout, affected_node):
        start_time = time.time()
        statuses = self.compute_client.virtual_machines.instance_view(
            resource_group, vm_name
        ).statuses[0]
        logging.info("vm status " + str(statuses))
        time_counter = 0
        while statuses.code == "ProvisioningState/deleting":
            try:
                statuses = self.compute_client.virtual_machines.instance_view(
                    resource_group, vm_name
                ).statuses[0]
                logging.info("Vm %s is still deleting, waiting 10 seconds" % vm_name)
                time.sleep(10)
                time_counter += 10
                if time_counter >= timeout:
                    logging.info("Vm %s was not terminated in allotted time" % vm_name)
                    return False
            except Exception:
                logging.info("Vm %s is terminated" % vm_name)
                end_time = time.time()
                if affected_node:
                    affected_node.set_affected_node_status("terminated", end_time - start_time)
                return True


    def create_security_group(self, resource_group, name, region, ip_address): 

        inbound_rule = SecurityRule(name="denyInbound", source_address_prefix="0.0.0.0/0", source_port_range="*", destination_address_prefix=ip_address, destination_port_range="*", priority=100, protocol="*",
                                    access="Deny", direction="Inbound")
        outbound_rule = SecurityRule(name="denyOutbound",  source_port_range="*", source_address_prefix=ip_address,destination_address_prefix="0.0.0.0/0", destination_port_range="*", priority=100, protocol="*",
                                    access="Deny", direction="Outbound")

        # create network resource group with deny in and out rules
        nsg = self.network_client.network_security_groups.begin_create_or_update(resource_group, name, parameters={"location": region, "security_rules": [inbound_rule,outbound_rule]})
        return nsg.result().id
    
    def delete_security_group(self, resource_group, name): 

        # find and delete network security group
        nsg = self.network_client.network_security_groups.begin_delete(resource_group,name)
        if nsg.result() is not None:
            print(nsg.result().as_dict())

    def update_subnet(self, network_group_id, resource_group, subnet_name, vnet_name): 
        
        subnet  = self.network_client.subnets.get(
            resource_group_name=resource_group,
            virtual_network_name=vnet_name,
            subnet_name=subnet_name)
        old_network_group = subnet.network_security_group.id
        subnet.network_security_group.id = network_group_id
        # update subnet
 
        self.network_client.subnets.begin_create_or_update(
                resource_group_name=resource_group,
                virtual_network_name=vnet_name,
                subnet_name=subnet_name,
                subnet_parameters=subnet)
        return old_network_group

# krkn_lib
class azure_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes, node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        logging.info("init in azure")
        self.azure = Azure()
        self.node_action_kube_check = node_action_kube_check
        

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_start_scenario injection")
                vm_name, resource_group = self.azure.get_instance_id(node)
                affected_node.node_id = vm_name
                logging.info(
                    "Starting the node %s with instance ID: %s "
                    % (vm_name, resource_group)
                )
                self.azure.start_instances(resource_group, vm_name)
                self.azure.wait_until_running(resource_group, vm_name, timeout, affected_node=affected_node)
                if self.node_action_kube_check:
                    nodeaction.wait_for_ready_status(vm_name, timeout, self.kubecli, affected_node)
                logging.info("Node with instance ID: %s is in running state" % node)
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
                vm_name, resource_group = self.azure.get_instance_id(node)
                affected_node.node_id = vm_name
                logging.info(
                    "Stopping the node %s with instance ID: %s "
                    % (vm_name, resource_group)
                )
                self.azure.stop_instances(resource_group, vm_name)
                self.azure.wait_until_stopped(resource_group, vm_name, timeout, affected_node=affected_node)
                logging.info("Node with instance ID: %s is in stopped state" % vm_name)
                if self.node_action_kube_check:
                    nodeaction.wait_for_unknown_status(vm_name, timeout, self.kubecli, affected_node)
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed" % e
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
                vm_name, resource_group = self.azure.get_instance_id(node)
                affected_node.node_id = vm_name
                logging.info(
                    "Terminating the node %s with instance ID: %s "
                    % (vm_name, resource_group)
                )
                self.azure.terminate_instances(resource_group, vm_name)
                self.azure.wait_until_terminated(resource_group, vm_name, timeout, affected_node)
                for _ in range(timeout):
                    if vm_name not in self.kubecli.list_nodes():
                        break
                    time.sleep(1)
                if vm_name in self.kubecli.list_nodes():
                    raise Exception("Node could not be terminated")
                logging.info("Node with instance ID: %s has been terminated" % node)
                logging.info(
                    "node_termination_scenario has been successfully injected!"
                )
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
                logging.info("Starting node_reboot_scenario injection")
                vm_name, resource_group = self.azure.get_instance_id(node)
                affected_node.node_id = vm_name
                logging.info(
                    "Rebooting the node %s with instance ID: %s "
                    % (vm_name, resource_group)
                )
                
                self.azure.reboot_instances(resource_group, vm_name)
                if self.node_action_kube_check:
                    nodeaction.wait_for_ready_status(vm_name, timeout, self.kubecli, affected_node)

                logging.info("Node with instance ID: %s has been rebooted" % (vm_name))
                logging.info("node_reboot_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to block traffic to the node
    def node_block_scenario(self, instance_kill_count, node, timeout, duration):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_block_scenario injection")
                vm_name, resource_group = self.azure.get_instance_id(node)

                subnet, virtual_network, private_ip, network_resource_group, location = self.azure.get_network_interface(vm_name, resource_group)
                affected_node.node_id = vm_name
 
                logging.info(
                    "block the node %s with instance ID: %s "
                    % (vm_name, network_resource_group)
                )
                network_group_id = self.azure.create_security_group(network_resource_group, "chaos", location, private_ip)
                old_network_group= self.azure.update_subnet(network_group_id, network_resource_group, subnet, virtual_network)
                logging.info("Node with instance ID: %s has been blocked" % (vm_name))
                logging.info("Waiting for %s seconds before resetting the subnet" % (duration))
                time.sleep(duration)

                # replace old network security group
                self.azure.update_subnet(old_network_group, network_resource_group, subnet, virtual_network)
                self.azure.delete_security_group(network_resource_group, "chaos")
                
                logging.info("node_block_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to block node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_block_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)