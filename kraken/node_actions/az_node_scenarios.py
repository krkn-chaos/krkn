import sys
import time
from azure.mgmt.compute import ComputeManagementClient
from azure.identity import DefaultAzureCredential
import logging
import kraken.kubernetes.client as kubecli
import kraken.node_actions.common_node_functions as nodeaction
from kraken.node_actions.abstract_node_scenarios import abstract_node_scenarios
import kraken.invoke.command as runcommand
import yaml


class Azure:
    def __init__(self):
        logging.info("azure " + str(self))
        # Acquire a credential object using CLI-based authentication.
        credentials = DefaultAzureCredential()
        logging.info("credential " + str(credentials))
        az_account = runcommand.invoke("az account list -o yaml")
        az_account_yaml = yaml.load(az_account, Loader=yaml.FullLoader)
        subscription_id = az_account_yaml[0]["id"]
        self.compute_client = ComputeManagementClient(credentials, subscription_id)

    # Get the instance ID of the node
    def get_instance_id(self, node_name):
        vm_list = self.compute_client.virtual_machines.list_all()
        for vm in vm_list:
            array = vm.id.split("/")
            resource_group = array[4]
            vm_name = array[-1]
            if node_name == vm_name:
                return resource_group
        logging.error("Couldn't find vm with name " + str(node_name))

    # Start the node instance
    def start_instances(self, group_name, vm_name):
        self.compute_client.virtual_machines.begin_start(group_name, vm_name)

    # Stop the node instance
    def stop_instances(self, group_name, vm_name):
        self.compute_client.virtual_machines.begin_power_off(group_name, vm_name)

    # Terminate the node instance
    def terminate_instances(self, group_name, vm_name):
        self.compute_client.virtual_machines.begin_delete(group_name, vm_name)

    # Reboot the node instance
    def reboot_instances(self, group_name, vm_name):
        self.compute_client.virtual_machines.begin_restart(group_name, vm_name)

    def get_vm_status(self, resource_group, vm_name):
        statuses = self.compute_client.virtual_machines.instance_view(resource_group, vm_name).statuses
        status = len(statuses) >= 2 and statuses[1]
        return status

    # Wait until the node instance is running
    def wait_until_running(self, resource_group, vm_name, timeout):
        time_counter = 0
        status = self.get_vm_status(resource_group, vm_name)
        while status and status.code != "PowerState/running":
            status = self.get_vm_status(resource_group, vm_name)
            logging.info("Vm %s is still not running, sleeping for 5 seconds" % vm_name)
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info("Vm %s is still not ready in allotted time" % vm_name)
                break

    # Wait until the node instance is stopped
    def wait_until_stopped(self, resource_group, vm_name, timeout):
        time_counter = 0
        status = self.get_vm_status(resource_group, vm_name)
        while status and status.code != "PowerState/stopped":
            status = self.get_vm_status(resource_group, vm_name)
            logging.info("Vm %s is still stopping, sleeping for 5 seconds" % vm_name)
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info("Vm %s is still not stopped in allotted time" % vm_name)
                break

    # Wait until the node instance is terminated
    def wait_until_terminated(self, resource_group, vm_name):
        statuses = self.compute_client.virtual_machines.instance_view(resource_group, vm_name).statuses[0]
        logging.info("vm status " + str(statuses))
        while statuses.code == "ProvisioningState/deleting":
            try:
                statuses = self.compute_client.virtual_machines.instance_view(resource_group, vm_name).statuses[0]
                logging.info("Vm %s is still deleting, waiting 10 seconds" % vm_name)
                time.sleep(10)
            except Exception:
                logging.info("Vm %s is terminated" % vm_name)
                break


class azure_node_scenarios(abstract_node_scenarios):
    def __init__(self):
        logging.info("init in azure")
        self.azure = Azure()

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_start_scenario injection")
                resource_group = self.azure.get_instance_id(node)
                logging.info("Starting the node %s with instance ID: %s " % (node, resource_group))
                self.azure.start_instances(resource_group, node)
                self.azure.wait_until_running(resource_group, node, timeout)
                nodeaction.wait_for_ready_status(node, timeout)
                logging.info("Node with instance ID: %s is in running state" % node)
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
                resource_group = self.azure.get_instance_id(node)
                logging.info("Stopping the node %s with instance ID: %s " % (node, resource_group))
                self.azure.stop_instances(resource_group, node)
                self.azure.wait_until_stopped(resource_group, node, timeout)
                logging.info("Node with instance ID: %s is in stopped state" % node)
                nodeaction.wait_for_unknown_status(node, timeout)
            except Exception as e:
                logging.error("Failed to stop node instance. Encountered following exception: %s. " "Test Failed" % e)
                logging.error("node_stop_scenario injection failed!")
                sys.exit(1)

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_termination_scenario injection")
                resource_group = self.azure.get_instance_id(node)
                logging.info("Terminating the node %s with instance ID: %s " % (node, resource_group))
                self.azure.terminate_instances(resource_group, node)
                self.azure.wait_until_terminated(resource_group, node)
                for _ in range(timeout):
                    if node not in kubecli.list_nodes():
                        break
                    time.sleep(1)
                if node in kubecli.list_nodes():
                    raise Exception("Node could not be terminated")
                logging.info("Node with instance ID: %s has been terminated" % node)
                logging.info("node_termination_scenario has been successfully injected!")
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
                resource_group = self.azure.get_instance_id(node)
                logging.info("Rebooting the node %s with instance ID: %s " % (node, resource_group))
                self.azure.reboot_instances(resource_group, node)
                nodeaction.wait_for_unknown_status(node, timeout)
                nodeaction.wait_for_ready_status(node, timeout)
                logging.info("Node with instance ID: %s has been rebooted" % (node))
                logging.info("node_reboot_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:" " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")
                sys.exit(1)
