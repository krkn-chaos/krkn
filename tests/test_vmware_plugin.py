import unittest
import os
import logging
from arcaflow_plugin_sdk import plugin
from kraken.plugins.node_scenarios.kubernetes_functions import Actions
from kraken.plugins.node_scenarios import vmware_plugin


class NodeScenariosTest(unittest.TestCase):
    def setUp(self):
        vsphere_env_vars = [
            "VSPHERE_IP",
            "VSPHERE_USERNAME",
            "VSPHERE_PASSWORD"
        ]
        self.credentials_present = all(
            env_var in os.environ for env_var in vsphere_env_vars
        )

    def test_serialization(self):
        plugin.test_object_serialization(
            vmware_plugin.NodeScenarioConfig(
                name="test",
                skip_openshift_checks=True
            ),
            self.fail,
        )
        plugin.test_object_serialization(
            vmware_plugin.NodeScenarioSuccessOutput(
                nodes={}, action=Actions.START
            ),
            self.fail,
        )
        plugin.test_object_serialization(
            vmware_plugin.NodeScenarioErrorOutput(
                error="Hello World", action=Actions.START
            ),
            self.fail,
        )

    def test_node_start(self):
        if not self.credentials_present:
            self.skipTest(
                "Check if the environmental variables 'VSPHERE_IP', "
                "'VSPHERE_USERNAME', 'VSPHERE_PASSWORD' are set"
            )
        vsphere = vmware_plugin.vSphere(verify=False)
        vm_id, vm_name = vsphere.create_default_vm()
        if vm_id is None:
            self.fail("Could not create test VM")

        output_id, output_data = vmware_plugin.node_start(
            vmware_plugin.NodeScenarioConfig(
                name=vm_name, skip_openshift_checks=True, verify_session=False
            )
        )
        if output_id == "error":
            logging.error(output_data.error)
            self.fail("The VMware VM did not start because an error occurred")
        vsphere.release_instances(vm_name)

    def test_node_stop(self):
        if not self.credentials_present:
            self.skipTest(
                "Check if the environmental variables 'VSPHERE_IP', "
                "'VSPHERE_USERNAME', 'VSPHERE_PASSWORD' are set"
            )
        vsphere = vmware_plugin.vSphere(verify=False)
        vm_id, vm_name = vsphere.create_default_vm()
        if vm_id is None:
            self.fail("Could not create test VM")
        vsphere.start_instances(vm_name)

        output_id, output_data = vmware_plugin.node_stop(
            vmware_plugin.NodeScenarioConfig(
                name=vm_name, skip_openshift_checks=True, verify_session=False
            )
        )
        if output_id == "error":
            logging.error(output_data.error)
            self.fail("The VMware VM did not stop because an error occurred")
        vsphere.release_instances(vm_name)

    def test_node_reboot(self):
        if not self.credentials_present:
            self.skipTest(
                "Check if the environmental variables 'VSPHERE_IP', "
                "'VSPHERE_USERNAME', 'VSPHERE_PASSWORD' are set"
            )
        vsphere = vmware_plugin.vSphere(verify=False)
        vm_id, vm_name = vsphere.create_default_vm()
        if vm_id is None:
            self.fail("Could not create test VM")
        vsphere.start_instances(vm_name)

        output_id, output_data = vmware_plugin.node_reboot(
            vmware_plugin.NodeScenarioConfig(
                name=vm_name, skip_openshift_checks=True, verify_session=False
            )
        )
        if output_id == "error":
            logging.error(output_data.error)
            self.fail("The VMware VM did not reboot because an error occurred")
        vsphere.release_instances(vm_name)

    def test_node_terminate(self):
        if not self.credentials_present:
            self.skipTest(
                "Check if the environmental variables 'VSPHERE_IP', "
                "'VSPHERE_USERNAME', 'VSPHERE_PASSWORD' are set"
            )
        vsphere = vmware_plugin.vSphere(verify=False)
        vm_id, vm_name = vsphere.create_default_vm()
        if vm_id is None:
            self.fail("Could not create test VM")
        vsphere.start_instances(vm_name)

        output_id, output_data = vmware_plugin.node_terminate(
            vmware_plugin.NodeScenarioConfig(
                name=vm_name, skip_openshift_checks=True, verify_session=False
            )
        )
        if output_id == "error":
            logging.error(output_data.error)
            self.fail("The VMware VM did not reboot because an error occurred")


if __name__ == "__main__":
    unittest.main()
