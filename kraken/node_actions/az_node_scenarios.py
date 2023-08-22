
import time
import yaml
import kraken.invoke.command as runcommand
import logging
import kraken.node_actions.common_node_functions as nodeaction
from kraken.node_actions.abstract_node_scenarios import abstract_node_scenarios
from azure.mgmt.compute import ComputeManagementClient
from azure.identity import DefaultAzureCredential
from krkn_lib.k8s import KrknKubernetes



class Azure:
    def __init__(self):
        logging.info("azure " + str(self))
        # Acquire a credential object using CLI-based authentication.
        credentials = DefaultAzureCredential()
        logging.info("credential " + str(credentials))
        az_account = runcommand.invoke("az account list -o yaml")
        az_account_yaml = yaml.safe_load(az_account, Loader=yaml.FullLoader)
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
                return vm_name, resource_group
        logging.error("Couldn't find vm with name " + str(node_name))

    # Start the node instance
    def start_instances(self, group_name, vm_name):
        try:
            self.compute_client.virtual_machines.begin_start(group_name, vm_name)
            logging.info("vm name " + str(vm_name) + " started")
        except Exception as e:
            logging.error("Failed to start node instance %s. Encountered following " "exception: %s." % (vm_name, e))
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()

    # Stop the node instance
    def stop_instances(self, group_name, vm_name):
        try:
            self.compute_client.virtual_machines.begin_power_off(group_name, vm_name)
            logging.info("vm name " + str(vm_name) + " stopped")
        except Exception as e:
            logging.error("Failed to stop node instance %s. Encountered following " "exception: %s." % (vm_name, e))
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()

    # Terminate the node instance
    def terminate_instances(self, group_name, vm_name):
        try:
            self.compute_client.virtual_machines.begin_delete(group_name, vm_name)
            logging.info("vm name " + str(vm_name) + " terminated")
        except Exception as e:
            logging.error(
                "Failed to terminate node instance %s. Encountered following " "exception: %s." % (vm_name, e)
            )
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()

    # Reboot the node instance
    def reboot_instances(self, group_name, vm_name):
        try:
            self.compute_client.virtual_machines.begin_restart(group_name, vm_name)
            logging.info("vm name " + str(vm_name) + " rebooted")
        except Exception as e:
            logging.error("Failed to reboot node instance %s. Encountered following " "exception: %s." % (vm_name, e))
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()

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
                return False
        return True

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
                return False
        return True

    # Wait until the node instance is terminated
    def wait_until_terminated(self, resource_group, vm_name, timeout):
        statuses = self.compute_client.virtual_machines.instance_view(resource_group, vm_name).statuses[0]
        logging.info("vm status " + str(statuses))
        time_counter = 0
        while statuses.code == "ProvisioningState/deleting":
            try:
                statuses = self.compute_client.virtual_machines.instance_view(resource_group, vm_name).statuses[0]
                logging.info("Vm %s is still deleting, waiting 10 seconds" % vm_name)
                time.sleep(10)
                time_counter += 10
                if time_counter >= timeout:
                    logging.info("Vm %s was not terminated in allotted time" % vm_name)
                    return False
            except Exception:
                logging.info("Vm %s is terminated" % vm_name)
                return True

# krkn_lib
class azure_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes):
        super().__init__(kubecli)
        logging.info("init in azure")
        self.azure = Azure()

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_start_scenario injection")
                vm_name, resource_group = self.azure.get_instance_id(node)
                logging.info("Starting the node %s with instance ID: %s " % (vm_name, resource_group))
                self.azure.start_instances(resource_group, vm_name)
                self.azure.wait_until_running(resource_group, vm_name, timeout)
                nodeaction.wait_for_ready_status(vm_name, timeout,self.kubecli)
                logging.info("Node with instance ID: %s is in running state" % node)
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
                vm_name, resource_group = self.azure.get_instance_id(node)
                logging.info("Stopping the node %s with instance ID: %s " % (vm_name, resource_group))
                self.azure.stop_instances(resource_group, vm_name)
                self.azure.wait_until_stopped(resource_group, vm_name, timeout)
                logging.info("Node with instance ID: %s is in stopped state" % vm_name)
                nodeaction.wait_for_unknown_status(vm_name, timeout, self.kubecli)
            except Exception as e:
                logging.error("Failed to stop node instance. Encountered following exception: %s. " "Test Failed" % e)
                logging.error("node_stop_scenario injection failed!")
                # removed_exit
                # sys.exit(1)
                raise RuntimeError()

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_termination_scenario injection")
                vm_name, resource_group = self.azure.get_instance_id(node)
                logging.info("Terminating the node %s with instance ID: %s " % (vm_name, resource_group))
                self.azure.terminate_instances(resource_group, vm_name)
                self.azure.wait_until_terminated(resource_group, vm_name, timeout)
                for _ in range(timeout):
                    if vm_name not in self.kubecli.list_nodes():
                        break
                    time.sleep(1)
                if vm_name in self.kubecli.list_nodes():
                    raise Exception("Node could not be terminated")
                logging.info("Node with instance ID: %s has been terminated" % node)
                logging.info("node_termination_scenario has been successfully injected!")
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
                logging.info("Starting node_reboot_scenario injection")
                vm_name, resource_group = self.azure.get_instance_id(node)
                logging.info("Rebooting the node %s with instance ID: %s " % (vm_name, resource_group))
                self.azure.reboot_instances(resource_group, vm_name)
                nodeaction.wait_for_unknown_status(vm_name, timeout, self.kubecli)
                nodeaction.wait_for_ready_status(vm_name, timeout, self.kubecli)
                logging.info("Node with instance ID: %s has been rebooted" % (vm_name))
                logging.info("node_reboot_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:" " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")
                # removed_exit
                # sys.exit(1)
                raise RuntimeError()