#!/usr/bin/env python
import logging
import os
import random
import sys
import time
import urllib3

from krkn_lib.k8s import KrknKubernetes
import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
from dataclasses import dataclass
from os import environ
import requests
from com.vmware.vapi.std.errors_client import (
    AlreadyInDesiredState,
    NotAllowedInCurrentState,
)
from com.vmware.vcenter.vm_client import Power
from com.vmware.vcenter_client import VM, ResourcePool
from vmware.vapi.vsphere.client import create_vsphere_client

from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

class vSphere:
    def __init__(self, verify=True):
        """
        Initialize the vSphere client by using the the env variables:
            'VSPHERE_IP', 'VSPHERE_USERNAME', 'VSPHERE_PASSWORD'
        """
        self.server = environ.get("VSPHERE_IP")
        self.username = environ.get("VSPHERE_USERNAME")
        self.password = environ.get("VSPHERE_PASSWORD")
        session = self.get_unverified_session()
        self.credentials_present = (
            True if self.server and self.username and self.password else False
        )
        if not self.credentials_present:
            raise Exception(
                "Environmental variables "
                "'VSPHERE_IP', 'VSPHERE_USERNAME', "
                "'VSPHERE_PASSWORD' are not set"
            )
        self.client = create_vsphere_client(
            server=self.server,
            username=self.username,
            password=self.password,
            session=session,
        )

    def get_unverified_session(self):
        """
        Returns an unverified session object
        """
        
        session = requests.session()
        # Set the proxy settings for the session
        session.verify = False
            
        urllib3.disable_warnings()

        return session

    def get_vm(self, instance_id):
        """
        Returns the VM ID corresponding to the VM Name (instance_id)
        If there are multiple matches, this only returns the first one
        """

        names = set([instance_id])
        vms = self.client.vcenter.VM.list(VM.FilterSpec(names=names))

        if len(vms) == 0:
            logging.info("VM with name ({}) not found", instance_id)
            return None
        vm = vms[0].vm

        return vm

    def release_instances(self, instance_id):
        """
        Deletes the VM whose name is given by 'instance_id'
        """

        vm = self.get_vm(instance_id)
        if not vm:
            raise Exception(
                "VM with the name ({}) does not exist."
                "Please create the vm first.".format(instance_id)
            )
        state = self.client.vcenter.vm.Power.get(vm)
        if state == Power.Info(state=Power.State.POWERED_ON):
            self.client.vcenter.vm.Power.stop(vm)
        elif state == Power.Info(state=Power.State.SUSPENDED):
            self.client.vcenter.vm.Power.start(vm)
            self.client.vcenter.vm.Power.stop(vm)
        self.client.vcenter.VM.delete(vm)
        logging.info("Deleted VM -- '{}-({})'", instance_id, vm)

    def reboot_instances(self, instance_id):
        """
        Reboots the VM whose name is given by 'instance_id'.
        @Returns: True if successful, or False if the VM is not powered on
        """

        vm = self.get_vm(instance_id)
        try:
            self.client.vcenter.vm.Power.reset(vm)
            logging.info("Reset VM -- '{}-({})'", instance_id, vm)
            return True
        except NotAllowedInCurrentState:
            logging.info(
                "VM '{}'-'({})' is not Powered On. Cannot reset it", instance_id, vm
            )
            return False

    def stop_instances(self, instance_id):
        """
        Stops the VM whose name is given by 'instance_id'.
        @Returns: True if successful, or False if the VM is already powered off
        """

        vm = self.get_vm(instance_id)
        try:
            self.client.vcenter.vm.Power.stop(vm)
            logging.info(f"Stopped VM -- '{instance_id}-({vm})'")
            return True
        except AlreadyInDesiredState:
            logging.info(f"VM '{instance_id}'-'({vm})' is already Powered Off")
            return False

    def start_instances(self, instance_id):
        """
        Stops the VM whose name is given by 'instance_id'.
        @Returns: True if successful, or False if the VM is already powered on
        """

        vm = self.get_vm(instance_id)
        try:
            self.client.vcenter.vm.Power.start(vm)
            logging.info(f"Started VM -- '{instance_id}-({vm})'")
            return True
        except AlreadyInDesiredState:
            logging.info(f"VM '{instance_id}'-'({vm})' is already Powered On")
            return False

    def list_instances(self, datacenter):
        """
        @Returns: a list of VMs present in the datacenter
        """

        datacenter_filter = self.client.vcenter.Datacenter.FilterSpec(
            names=set([datacenter])
        )
        datacenter_summaries = self.client.vcenter.Datacenter.list(datacenter_filter)
        try:
            datacenter_id = datacenter_summaries[0].datacenter
        except IndexError:
            logging.error("Datacenter '{}' doesn't exist", datacenter)
            sys.exit(1)

        vm_filter = self.client.vcenter.VM.FilterSpec(datacenters={datacenter_id})
        vm_summaries = self.client.vcenter.VM.list(vm_filter)
        vm_names = []
        for vm in vm_summaries:
            vm_names.append({"vm_name": vm.name, "vm_id": vm.vm})
        return vm_names

    def get_datacenter_list(self):
        """
        Returns a dictionary containing all the datacenter names and IDs
        """

        datacenter_summaries = self.client.vcenter.Datacenter.list()
        datacenter_names = [
            {"datacenter_id": datacenter.datacenter, "datacenter_name": datacenter.name}
            for datacenter in datacenter_summaries
        ]
        return datacenter_names

    def get_datastore_list(self, datacenter=None):
        """
        @Returns: a dictionary containing all the datastore names and
                  IDs belonging to a specific datacenter
        """

        datastore_filter = self.client.vcenter.Datastore.FilterSpec(
            datacenters={datacenter}
        )
        datastore_summaries = self.client.vcenter.Datastore.list(datastore_filter)
        datastore_names = []
        for datastore in datastore_summaries:
            datastore_names.append(
                {"datastore_name": datastore.name, "datastore_id": datastore.datastore}
            )
        return datastore_names

    def get_folder_list(self, datacenter=None):
        """
        @Returns: a dictionary containing all the folder names and
                  IDs belonging to a specific datacenter
        """

        folder_filter = self.client.vcenter.Folder.FilterSpec(datacenters={datacenter})
        folder_summaries = self.client.vcenter.Folder.list(folder_filter)
        folder_names = []
        for folder in folder_summaries:
            folder_names.append(
                {"folder_name": folder.name, "folder_id": folder.folder}
            )
        return folder_names

    def get_resource_pool(self, datacenter, resource_pool_name=None):
        """
        Returns the identifier of the resource pool with the given name or the
        first resource pool in the datacenter if the name is not provided.
        """

        names = set([resource_pool_name]) if resource_pool_name else None
        filter_spec = ResourcePool.FilterSpec(
            datacenters=set([datacenter]), names=names
        )
        resource_pool_summaries = self.client.vcenter.ResourcePool.list(filter_spec)
        if len(resource_pool_summaries) > 0:
            resource_pool = resource_pool_summaries[0].resource_pool
            return resource_pool
        else:
            logging.error("ResourcePool not found in Datacenter '{}'", datacenter)
            return None

    def create_default_vm(self, guest_os="RHEL_7_64", max_attempts=10):
        """
        Creates a default VM with 2 GB memory, 1 CPU and 16 GB disk space in a
        random datacenter. Accepts the guest OS as a parameter. Since the VM
        placement is random, it might fail due to resource constraints.
        So, this function tries for upto 'max_attempts' to create the VM
        """

        def create_vm(vm_name, resource_pool, folder, datastore, guest_os):
            """
            Creates a VM and returns its ID and name. Requires the VM name,
            resource pool name, folder name, datastore and the guest OS
            """

            placement_spec = VM.PlacementSpec(
                folder=folder, resource_pool=resource_pool, datastore=datastore
            )
            vm_create_spec = VM.CreateSpec(
                name=vm_name, guest_os=guest_os, placement=placement_spec
            )

            vm_id = self.client.vcenter.VM.create(vm_create_spec)
            return vm_id

        for _ in range(max_attempts):
            try:
                datacenter_list = self.get_datacenter_list()
                # random  generator not used for
                # security/cryptographic purposes in this loop
                datacenter = random.choice(datacenter_list)  # nosec
                resource_pool = self.get_resource_pool(datacenter["datacenter_id"])
                folder = random.choice(  # nosec
                    self.get_folder_list(datacenter["datacenter_id"])
                )["folder_id"]
                datastore = random.choice(  # nosec
                    self.get_datastore_list(datacenter["datacenter_id"])
                )["datastore_id"]
                vm_name = "Test-" + str(time.time_ns())
                return (
                    create_vm(vm_name, resource_pool, folder, datastore, guest_os),
                    vm_name,
                )
            except Exception as e:
                logging.error(
                    "Default VM could not be created, retrying. " "Error was: %s",
                    str(e),
                )
        logging.error(
            "Default VM could not be created in %s attempts. "
            "Check your VMware resources",
            max_attempts,
        )
        return None, None

    def get_vm_status(self, instance_id):
        """
        Returns the status of the VM whose name is given by 'instance_id'
        """

        try:
            vm = self.get_vm(instance_id)
            state = self.client.vcenter.vm.Power.get(vm).state
            logging.info(f"Check instance {instance_id} status")
            return state
        except Exception as e:
            logging.error(
                f"Failed to get node instance status {instance_id}. Encountered following "
                f"exception: {str(e)}. "
            )
            return None

    def wait_until_released(self, instance_id, timeout, affected_node):
        """
        Waits until the VM is deleted or until the timeout. Returns True if
        the VM is successfully deleted, else returns False
        """

        time_counter = 0
        start_time = time.time()
        vm = self.get_vm(instance_id)
        exit_status = True
        while vm is not None:
            vm = self.get_vm(instance_id)
            logging.info(
                f"VM {instance_id} is still being deleted, " f"sleeping for 5 seconds"
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(f"VM {instance_id} is still not deleted in allotted time")
                exit_status = False
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("terminated", end_time - start_time)
                
        return exit_status

    def wait_until_running(self, instance_id, timeout, affected_node):
        """
        Waits until the VM switches to POWERED_ON state or until the timeout.
        Returns True if the VM switches to POWERED_ON, else returns False
        """

        time_counter = 0
        start_time = time.time()
        exit_status = True
        status = self.get_vm_status(instance_id)
        while status != Power.State.POWERED_ON:
            status = self.get_vm_status(instance_id)
            logging.info(
                "VM %s is still not running, " "sleeping for 5 seconds", instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(f"VM {instance_id} is still not ready in allotted time")
                exit_status = False
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("running", end_time - start_time)
                

        return exit_status

    def wait_until_stopped(self, instance_id, timeout, affected_node):
        """
        Waits until the VM switches to POWERED_OFF state or until the timeout.
        Returns True if the VM switches to POWERED_OFF, else returns False
        """

        time_counter = 0
        start_time = time.time()
        exit_status = True
        status = self.get_vm_status(instance_id)
        while status != Power.State.POWERED_OFF:
            status = self.get_vm_status(instance_id)
            logging.info(
                f"VM {instance_id} is still not running, " f"sleeping for 5 seconds"
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(f"VM {instance_id} is still not ready in allotted time")
                exit_status = False
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("stopped", end_time - start_time)
                

        return exit_status


@dataclass
class vmware_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes, node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.vsphere = vSphere()
        self.node_action_kube_check = node_action_kube_check

    def node_start_scenario(self, instance_kill_count, node, timeout):
        try:
            for _ in range(instance_kill_count):
                affected_node = AffectedNode(node)
                logging.info("Starting node_start_scenario injection")
                logging.info(f"Starting the node {node} ")
                vm_started = self.vsphere.start_instances(node)
                if vm_started:
                    self.vsphere.wait_until_running(node, timeout, affected_node)
                    if self.node_action_kube_check:
                        nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(f"Node with instance ID: {node} is in running state")
                logging.info("node_start_scenario has been successfully injected!")
                self.affected_nodes_status.affected_nodes.append(affected_node)
        except Exception as e:
            logging.error("Failed to start node instance. Test Failed")
            logging.error(
                f"node_start_scenario injection failed! " f"Error was: {str(e)}"
            )

    def node_stop_scenario(self, instance_kill_count, node, timeout):
        try:
            for _ in range(instance_kill_count):
                affected_node = AffectedNode(node)
                logging.info("Starting node_stop_scenario injection")
                logging.info(f"Stopping the node {node} ")
                vm_stopped = self.vsphere.stop_instances(node)
                if vm_stopped:
                    self.vsphere.wait_until_stopped(node, timeout, affected_node)
                    if self.node_action_kube_check:
                        nodeaction.wait_for_ready_status(
                            node, timeout, self.kubecli, affected_node
                        )
                logging.info(f"Node with instance ID: {node} is in stopped state")
                logging.info("node_stop_scenario has been successfully injected!")
                self.affected_nodes_status.affected_nodes.append(affected_node)
        except Exception as e:
            logging.error("Failed to stop node instance. Test Failed")
            logging.error(
                f"node_stop_scenario injection failed! " f"Error was: {str(e)}"
            )
                

    def node_reboot_scenario(self, instance_kill_count, node, timeout):
        try:
            for _ in range(instance_kill_count):
                affected_node = AffectedNode(node)
                logging.info("Starting node_reboot_scenario injection")
                logging.info(f"Rebooting the node {node} ")
                self.vsphere.reboot_instances(node)
                if self.node_action_kube_check:
                    nodeaction.wait_for_unknown_status(
                        node, timeout, self.kubecli, affected_node
                    )
                   
                logging.info(
                    f"Node with instance ID: {node} has rebooted " "successfully"
                )
                logging.info("node_reboot_scenario has been successfully injected!")
                self.affected_nodes_status.affected_nodes.append(affected_node)
        except Exception as e:
            logging.error("Failed to reboot node instance. Test Failed")
            logging.error(
                f"node_reboot_scenario injection failed! " f"Error was: {str(e)}"
            )


    def node_terminate_scenario(self, instance_kill_count, node, timeout):
        try:
            for _ in range(instance_kill_count):
                affected_node = AffectedNode(node)
                logging.info(
                    "Starting node_termination_scenario injection "
                    "by first stopping the node"
                )
                self.vsphere.stop_instances(node)
                self.vsphere.wait_until_stopped(node, timeout, affected_node)
                logging.info(f"Releasing the node with instance ID: {node} ")
                self.vsphere.release_instances(node)
                self.vsphere.wait_until_released(node, timeout, affected_node)
                logging.info(f"Node with instance ID: {node} has been released")
                logging.info(
                    "node_terminate_scenario has been " "successfully injected!"
                )
                self.affected_nodes_status.affected_nodes.append(affected_node)
        except Exception as e:
            logging.error("Failed to terminate node instance. Test Failed")
            logging.error(
                f"node_terminate_scenario injection failed! " f"Error was: {str(e)}"
            )
