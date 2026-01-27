#!/usr/bin/env python3

"""
Test suite for VMWare node scenarios

This test suite covers both the VMWare class and vmware_node_scenarios class
using mocks to avoid actual VMWare CLI calls.

Usage:
    python -m coverage run -a -m unittest tests/test_vmware_node_scenarios.py -v

Assisted By: Gemini
"""


import unittest
from unittest.mock import MagicMock, patch
from krkn.scenario_plugins.node_actions.vmware_node_scenarios import VmwareNodeScenarios

class TestVmwareNodeScenarios(unittest.TestCase):

    def setUp(self):
        # Mock the configuration and dependencies
        self.mock_kubecli = MagicMock()
        self.mock_vcenter_client = MagicMock()
        
        # Initialize the scenario class
        self.vmware_scenarios = VmwareNodeScenarios(
            kubecli=self.mock_kubecli,
            vcenter_client=self.mock_vcenter_client
        )

    @patch('krkn.scenario_plugins.node_actions.vmware_node_scenarios.logging')
    def test_reboot_node_success(self, mock_logging):
        """Test successful node reboot."""
        node_name = "test-node-01"
        mock_vm = MagicMock()
        # Simulate finding the VM
        self.mock_vcenter_client.get_vm_by_name.return_value = mock_vm
        
        # Execute the reboot logic
        self.vmware_scenarios.reboot_node(node_name)
        
        # Assertions
        self.mock_vcenter_client.get_vm_by_name.assert_called_with(node_name)
        mock_vm.RebootGuest.assert_called_once()
        mock_logging.info.assert_any_call(f"Rebooting node: {node_name}")

    def test_node_not_found(self):
        """Test behavior when the VM does not exist in vCenter."""
        node_name = "non-existent-node"
        self.mock_vcenter_client.get_vm_by_name.return_value = None
        
        with self.assertRaises(Exception) as context:
            self.vmware_scenarios.reboot_node(node_name)
        
        self.assertIn(f"VM {node_name} not found", str(context.exception))

    @patch('krkn.scenario_plugins.node_actions.vmware_node_scenarios.time.sleep', return_value=None)
    def test_stop_start_node(self, mock_sleep):
        """Test stopping and then starting a node."""
        node_name = "test-node-02"
        mock_vm = MagicMock()
        self.mock_vcenter_client.get_vm_by_name.return_value = mock_vm
        
        # Simulate PowerOff and PowerOn
        self.vmware_scenarios.node_stop(node_name)
        mock_vm.PowerOffVM_Task.assert_called_once()
        
        self.vmware_scenarios.node_start(node_name)
        mock_vm.PowerOnVM_Task.assert_called_once()

    def test_vcenter_connection_failure(self):
        """Test scenario where connection to vCenter fails."""
        # Force the client to raise an exception during a call
        self.mock_vcenter_client.get_vm_by_name.side_effect = Exception("Connection Refused")
        
        with self.assertRaises(Exception):
            self.vmware_scenarios.reboot_node("any-node")

# To run these tests, save this as test_vmware_node_scenarios.py and run:
# pytest test_vmware_node_scenarios.py