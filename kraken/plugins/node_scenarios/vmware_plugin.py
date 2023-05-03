#!/usr/bin/env python
import logging
import random
import sys
import time
import typing
from dataclasses import dataclass, field
from os import environ
from traceback import format_exc
import requests
from arcaflow_plugin_sdk import plugin, validation
from com.vmware.vapi.std.errors_client import (AlreadyInDesiredState,
                                               NotAllowedInCurrentState)
from com.vmware.vcenter.vm_client import Power
from com.vmware.vcenter_client import VM, ResourcePool
from kubernetes import client, watch
from vmware.vapi.vsphere.client import create_vsphere_client

from kraken.plugins.node_scenarios import kubernetes_functions as kube_helper


class vSphere:
    def __init__(self, verify=True):
        """
        Initialize the vSphere client by using the the env variables:
            'VSPHERE_IP', 'VSPHERE_USERNAME', 'VSPHERE_PASSWORD'
        """
        self.server = environ.get("VSPHERE_IP")
        self.username = environ.get("VSPHERE_USERNAME")
        self.password = environ.get("VSPHERE_PASSWORD")
        session = self.get_unverified_session() if not verify else None
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
        session.verify = False
        requests.packages.urllib3.disable_warnings()
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
                "VM '{}'-'({})' is not Powered On. Cannot reset it",
                instance_id,
                vm
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
            logging.info("Stopped VM -- '{}-({})'", instance_id, vm)
            return True
        except AlreadyInDesiredState:
            logging.info(
                "VM '{}'-'({})' is already Powered Off", instance_id, vm
            )
            return False

    def start_instances(self, instance_id):
        """
        Stops the VM whose name is given by 'instance_id'.
        @Returns: True if successful, or False if the VM is already powered on
        """

        vm = self.get_vm(instance_id)
        try:
            self.client.vcenter.vm.Power.start(vm)
            logging.info("Started VM -- '{}-({})'", instance_id, vm)
            return True
        except AlreadyInDesiredState:
            logging.info(
                "VM '{}'-'({})' is already Powered On", instance_id, vm
            )
            return False

    def list_instances(self, datacenter):
        """
        @Returns: a list of VMs present in the datacenter
        """

        datacenter_filter = self.client.vcenter.Datacenter.FilterSpec(
            names=set([datacenter])
        )
        datacenter_summaries = self.client.vcenter.Datacenter.list(
            datacenter_filter
        )
        try:
            datacenter_id = datacenter_summaries[0].datacenter
        except IndexError:
            logging.error("Datacenter '{}' doesn't exist", datacenter)
            sys.exit(1)

        vm_filter = self.client.vcenter.VM.FilterSpec(
            datacenters={datacenter_id}
        )
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
            {
                "datacenter_id": datacenter.datacenter,
                "datacenter_name": datacenter.name
            }
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
        datastore_summaries = self.client.vcenter.Datastore.list(
            datastore_filter
        )
        datastore_names = []
        for datastore in datastore_summaries:
            datastore_names.append(
                {
                    "datastore_name": datastore.name,
                    "datastore_id": datastore.datastore
                }
            )
        return datastore_names

    def get_folder_list(self, datacenter=None):
        """
        @Returns: a dictionary containing all the folder names and
                  IDs belonging to a specific datacenter
        """

        folder_filter = self.client.vcenter.Folder.FilterSpec(
            datacenters={datacenter}
        )
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
        resource_pool_summaries = self.client.vcenter.ResourcePool.list(
            filter_spec
        )
        if len(resource_pool_summaries) > 0:
            resource_pool = resource_pool_summaries[0].resource_pool
            return resource_pool
        else:
            logging.error(
                "ResourcePool not found in Datacenter '{}'",
                datacenter
            )
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
                resource_pool = self.get_resource_pool(
                    datacenter["datacenter_id"]
                )
                folder = random.choice(  # nosec
                    self.get_folder_list(datacenter["datacenter_id"])
                )["folder_id"]
                datastore = random.choice(  # nosec
                    self.get_datastore_list(datacenter["datacenter_id"])
                )["datastore_id"]
                vm_name = "Test-" + str(time.time_ns())
                return (
                    create_vm(
                        vm_name,
                        resource_pool,
                        folder,
                        datastore,
                        guest_os
                    ),
                    vm_name,
                )
            except Exception as e:
                logging.error(
                    "Default VM could not be created, retrying. "
                    "Error was: %s",
                    str(e)
                )
        logging.error(
            "Default VM could not be created in %s attempts. "
            "Check your VMware resources",
            max_attempts
        )
        return None, None

    def get_vm_status(self, instance_id):
        """
        Returns the status of the VM whose name is given by 'instance_id'
        """

        try:
            vm = self.get_vm(instance_id)
            state = self.client.vcenter.vm.Power.get(vm).state
            logging.info("Check instance %s status", instance_id)
            return state
        except Exception as e:
            logging.error(
                "Failed to get node instance status %s. Encountered following "
                "exception: %s.", instance_id, e
            )
            return None

    def wait_until_released(self, instance_id, timeout):
        """
        Waits until the VM is deleted or until the timeout. Returns True if
        the VM is successfully deleted, else returns False
        """

        time_counter = 0
        vm = self.get_vm(instance_id)
        while vm is not None:
            vm = self.get_vm(instance_id)
            logging.info(
                "VM %s is still being deleted, "
                "sleeping for 5 seconds",
                instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(
                    "VM %s is still not deleted in allotted time",
                    instance_id
                )
                return False
        return True

    def wait_until_running(self, instance_id, timeout):
        """
        Waits until the VM switches to POWERED_ON state or until the timeout.
        Returns True if the VM switches to POWERED_ON, else returns False
        """

        time_counter = 0
        status = self.get_vm_status(instance_id)
        while status != Power.State.POWERED_ON:
            status = self.get_vm_status(instance_id)
            logging.info(
                "VM %s is still not running, "
                "sleeping for 5 seconds",
                instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(
                    "VM %s is still not ready in allotted time",
                    instance_id
                )
                return False
        return True

    def wait_until_stopped(self, instance_id, timeout):
        """
        Waits until the VM switches to POWERED_OFF state or until the timeout.
        Returns True if the VM switches to POWERED_OFF, else returns False
        """

        time_counter = 0
        status = self.get_vm_status(instance_id)
        while status != Power.State.POWERED_OFF:
            status = self.get_vm_status(instance_id)
            logging.info(
                "VM %s is still not running, "
                "sleeping for 5 seconds",
                instance_id
            )
            time.sleep(5)
            time_counter += 5
            if time_counter >= timeout:
                logging.info(
                    "VM %s is still not ready in allotted time",
                    instance_id
                )
                return False
        return True


@dataclass
class Node:
    name: str


@dataclass
class NodeScenarioSuccessOutput:

    nodes: typing.Dict[int, Node] = field(
        metadata={
            "name": "Nodes started/stopped/terminated/rebooted",
            "description": "Map between timestamps and the pods "
                           "started/stopped/terminated/rebooted. "
                           "The timestamp is provided in nanoseconds",
        }
    )
    action: kube_helper.Actions = field(
        metadata={
            "name": "The action performed on the node",
            "description": "The action performed or attempted to be "
                           "performed on the node. Possible values"
                           "are : Start, Stop, Terminate, Reboot",
        }
    )


@dataclass
class NodeScenarioErrorOutput:

    error: str
    action: kube_helper.Actions = field(
        metadata={
            "name": "The action performed on the node",
            "description": "The action attempted to be performed on the node. "
            "Possible values are : Start Stop, Terminate, Reboot",
        }
    )


@dataclass
class NodeScenarioConfig:

    name: typing.Annotated[
        typing.Optional[str],
        validation.required_if_not("label_selector"),
        validation.required_if("skip_openshift_checks"),
    ] = field(
        default=None,
        metadata={
            "name": "Name",
            "description": "Name(s) for target nodes. "
                           "Required if label_selector is not set.",
        },
    )

    runs: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=1,
        metadata={
            "name": "Number of runs per node",
            "description": "Number of times to inject each scenario under "
                           "actions (will perform on same node each time)",
        },
    )

    label_selector: typing.Annotated[
        typing.Optional[str],
        validation.min(1),
        validation.required_if_not("name")
    ] = field(
        default=None,
        metadata={
            "name": "Label selector",
            "description": "Kubernetes label selector for the target nodes. "
                           "Required if name is not set.\n"
            "See https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/ "  # noqa
            "for details.",
        },
    )

    timeout: typing.Annotated[typing.Optional[int], validation.min(1)] = field(
        default=180,
        metadata={
            "name": "Timeout",
            "description": "Timeout to wait for the target pod(s) "
                           "to be removed in seconds.",
        },
    )

    instance_count: typing.Annotated[
        typing.Optional[int],
        validation.min(1)
    ] = field(
        default=1,
        metadata={
            "name": "Instance Count",
            "description": "Number of nodes to perform action/select "
                           "that match the label selector.",
        },
    )

    skip_openshift_checks: typing.Optional[bool] = field(
        default=False,
        metadata={
            "name": "Skip Openshift Checks",
            "description": "Skip checking the status of the openshift nodes.",
        },
    )

    verify_session: bool = field(
        default=True,
        metadata={
            "name": "Verify API Session",
            "description": "Verifies the vSphere client session. "
                           "It is enabled by default",
        },
    )

    kubeconfig_path: typing.Optional[str] = field(
        default=None,
        metadata={
            "name": "Kubeconfig path",
            "description": "Path to your Kubeconfig file. "
                           "Defaults to ~/.kube/config.\n"
            "See https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/ "  # noqa
            "for details.",
        },
    )


@plugin.step(
    id="vmware-node-start",
    name="Start the node",
    description="Start the node(s) by starting the VMware VM "
                "on which the node is configured",
    outputs={
        "success": NodeScenarioSuccessOutput,
        "error": NodeScenarioErrorOutput
    },
)
def node_start(
    cfg: NodeScenarioConfig,
) -> typing.Tuple[
    str, typing.Union[NodeScenarioSuccessOutput, NodeScenarioErrorOutput]
]:
    with kube_helper.setup_kubernetes(None) as cli:
        vsphere = vSphere(verify=cfg.verify_session)
        core_v1 = client.CoreV1Api(cli)
        watch_resource = watch.Watch()
        node_list = kube_helper.get_node_list(
            cfg,
            kube_helper.Actions.START,
            core_v1
        )
        nodes_started = {}
        for name in node_list:
            try:
                for _ in range(cfg.runs):
                    logging.info("Starting node_start_scenario injection")
                    logging.info("Starting the node %s ", name)
                    vm_started = vsphere.start_instances(name)
                    if vm_started:
                        vsphere.wait_until_running(name, cfg.timeout)
                        if not cfg.skip_openshift_checks:
                            kube_helper.wait_for_ready_status(
                                name, cfg.timeout, watch_resource, core_v1
                            )
                        nodes_started[int(time.time_ns())] = Node(name=name)
                    logging.info(
                        "Node with instance ID: %s is in running state", name
                    )
                    logging.info(
                        "node_start_scenario has been successfully injected!"
                    )
            except Exception as e:
                logging.error("Failed to start node instance. Test Failed")
                logging.error(
                    "node_start_scenario injection failed! "
                    "Error was: %s", str(e)
                )
                return "error", NodeScenarioErrorOutput(
                    format_exc(), kube_helper.Actions.START
                )

    return "success", NodeScenarioSuccessOutput(
        nodes_started, kube_helper.Actions.START
    )


@plugin.step(
    id="vmware-node-stop",
    name="Stop the node",
    description="Stop the node(s) by starting the VMware VM "
                "on which the node is configured",
    outputs={
        "success": NodeScenarioSuccessOutput,
        "error": NodeScenarioErrorOutput
    },
)
def node_stop(
    cfg: NodeScenarioConfig,
) -> typing.Tuple[
    str, typing.Union[NodeScenarioSuccessOutput, NodeScenarioErrorOutput]
]:
    with kube_helper.setup_kubernetes(None) as cli:
        vsphere = vSphere(verify=cfg.verify_session)
        core_v1 = client.CoreV1Api(cli)
        watch_resource = watch.Watch()
        node_list = kube_helper.get_node_list(
            cfg,
            kube_helper.Actions.STOP,
            core_v1
        )
        nodes_stopped = {}
        for name in node_list:
            try:
                for _ in range(cfg.runs):
                    logging.info("Starting node_stop_scenario injection")
                    logging.info("Stopping the node %s ", name)
                    vm_stopped = vsphere.stop_instances(name)
                    if vm_stopped:
                        vsphere.wait_until_stopped(name, cfg.timeout)
                        if not cfg.skip_openshift_checks:
                            kube_helper.wait_for_ready_status(
                                name, cfg.timeout, watch_resource, core_v1
                            )
                        nodes_stopped[int(time.time_ns())] = Node(name=name)
                    logging.info(
                        "Node with instance ID: %s is in stopped state", name
                    )
                    logging.info(
                        "node_stop_scenario has been successfully injected!"
                    )
            except Exception as e:
                logging.error("Failed to stop node instance. Test Failed")
                logging.error(
                    "node_stop_scenario injection failed! "
                    "Error was: %s", str(e)
                )
                return "error", NodeScenarioErrorOutput(
                    format_exc(), kube_helper.Actions.STOP
                )

        return "success", NodeScenarioSuccessOutput(
            nodes_stopped, kube_helper.Actions.STOP
        )


@plugin.step(
    id="vmware-node-reboot",
    name="Reboot VMware VM",
    description="Reboot the node(s) by starting the VMware VM "
                "on which the node is configured",
    outputs={
        "success": NodeScenarioSuccessOutput,
        "error": NodeScenarioErrorOutput
    },
)
def node_reboot(
    cfg: NodeScenarioConfig,
) -> typing.Tuple[
    str, typing.Union[NodeScenarioSuccessOutput, NodeScenarioErrorOutput]
]:
    with kube_helper.setup_kubernetes(None) as cli:
        vsphere = vSphere(verify=cfg.verify_session)
        core_v1 = client.CoreV1Api(cli)
        watch_resource = watch.Watch()
        node_list = kube_helper.get_node_list(
            cfg,
            kube_helper.Actions.REBOOT,
            core_v1
        )
        nodes_rebooted = {}
        for name in node_list:
            try:
                for _ in range(cfg.runs):
                    logging.info("Starting node_reboot_scenario injection")
                    logging.info("Rebooting the node %s ", name)
                    vsphere.reboot_instances(name)
                    if not cfg.skip_openshift_checks:
                        kube_helper.wait_for_unknown_status(
                            name, cfg.timeout, watch_resource, core_v1
                        )
                        kube_helper.wait_for_ready_status(
                            name, cfg.timeout, watch_resource, core_v1
                        )
                    nodes_rebooted[int(time.time_ns())] = Node(name=name)
                    logging.info(
                        "Node with instance ID: %s has rebooted "
                        "successfully", name
                    )
                    logging.info(
                        "node_reboot_scenario has been successfully injected!"
                    )
            except Exception as e:
                logging.error("Failed to reboot node instance. Test Failed")
                logging.error(
                    "node_reboot_scenario injection failed! "
                    "Error was: %s", str(e)
                )
                return "error", NodeScenarioErrorOutput(
                    format_exc(), kube_helper.Actions.REBOOT
                )

    return "success", NodeScenarioSuccessOutput(
        nodes_rebooted, kube_helper.Actions.REBOOT
    )


@plugin.step(
    id="vmware-node-terminate",
    name="Reboot VMware VM",
    description="Wait for the node to be terminated",
    outputs={"success": NodeScenarioSuccessOutput, "error": NodeScenarioErrorOutput},
)
def node_terminate(
    cfg: NodeScenarioConfig,
) -> typing.Tuple[
    str, typing.Union[NodeScenarioSuccessOutput, NodeScenarioErrorOutput]
]:
    with kube_helper.setup_kubernetes(None) as cli:
        vsphere = vSphere(verify=cfg.verify_session)
        core_v1 = client.CoreV1Api(cli)
        node_list = kube_helper.get_node_list(
            cfg, kube_helper.Actions.TERMINATE, core_v1
        )
        nodes_terminated = {}
        for name in node_list:
            try:
                for _ in range(cfg.runs):
                    logging.info(
                        "Starting node_termination_scenario injection "
                        "by first stopping the node"
                    )
                    vsphere.stop_instances(name)
                    vsphere.wait_until_stopped(name, cfg.timeout)
                    logging.info(
                        "Releasing the node with instance ID: %s ", name
                    )
                    vsphere.release_instances(name)
                    vsphere.wait_until_released(name, cfg.timeout)
                    nodes_terminated[int(time.time_ns())] = Node(name=name)
                    logging.info(
                        "Node with instance ID: %s has been released", name
                    )
                    logging.info(
                        "node_terminate_scenario has been "
                        "successfully injected!"
                    )
            except Exception as e:
                logging.error("Failed to terminate node instance. Test Failed")
                logging.error(
                    "node_terminate_scenario injection failed! "
                    "Error was: %s", str(e)
                )
                return "error", NodeScenarioErrorOutput(
                    format_exc(), kube_helper.Actions.TERMINATE
                )

    return "success", NodeScenarioSuccessOutput(
        nodes_terminated, kube_helper.Actions.TERMINATE
    )
