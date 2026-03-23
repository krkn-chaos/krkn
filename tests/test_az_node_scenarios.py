#!/usr/bin/env python3

"""
Test suite for azure_node_scenarios class

Usage:
    python -m coverage run -a -m unittest tests/test_az_node_scenarios.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import Mock, patch

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

from krkn.scenario_plugins.node_actions.az_node_scenarios import Azure, azure_node_scenarios


class TestAzure(unittest.TestCase):
    """Test suite for Azure class"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock environment variable
        self.env_patcher = patch.dict('os.environ', {'AZURE_SUBSCRIPTION_ID': 'test-subscription-id'})
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after tests"""
        self.env_patcher.stop()

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    @patch('logging.info')
    def test_azure_init(self, mock_logging, mock_credential, mock_compute, mock_network):
        """Test Azure class initialization"""
        mock_creds = Mock()
        mock_credential.return_value = mock_creds

        azure = Azure()

        mock_credential.assert_called_once()
        mock_compute.assert_called_once()
        mock_network.assert_called_once()
        self.assertIsNotNone(azure.compute_client)
        self.assertIsNotNone(azure.network_client)

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_get_instance_id_found(self, mock_credential, mock_compute, mock_network):
        """Test get_instance_id when VM is found"""
        azure = Azure()

        # Mock VM
        mock_vm = Mock()
        mock_vm.name = "test-node"
        mock_vm.id = "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-node"

        azure.compute_client.virtual_machines.list_all.return_value = [mock_vm]

        vm_name, resource_group = azure.get_instance_id("test-node")

        self.assertEqual(vm_name, "test-node")
        self.assertEqual(resource_group, "test-rg")

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_get_instance_id_not_found(self, mock_credential, mock_compute, mock_network, mock_logging):
        """Test get_instance_id when VM is not found"""
        azure = Azure()

        azure.compute_client.virtual_machines.list_all.return_value = []

        result = azure.get_instance_id("nonexistent-node")

        self.assertIsNone(result)
        mock_logging.assert_called()
        self.assertIn("Couldn't find vm", str(mock_logging.call_args))

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_get_network_interface(self, mock_credential, mock_compute, mock_network):
        """Test get_network_interface retrieves network details"""
        azure = Azure()

        # Mock VM with network profile
        mock_vm = Mock()
        mock_nic_ref = Mock()
        mock_nic_ref.id = "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Network/networkInterfaces/test-nic"
        mock_vm.network_profile.network_interfaces = [mock_nic_ref]

        # Mock NIC
        mock_nic = Mock()
        mock_nic.location = "eastus"
        mock_ip_config = Mock()
        mock_ip_config.private_ip_address = "10.0.1.5"
        mock_ip_config.subnet.id = "/subscriptions/sub-id/resourceGroups/network-rg/providers/Microsoft.Network/virtualNetworks/test-vnet/subnets/test-subnet"
        mock_nic.ip_configurations = [mock_ip_config]

        azure.compute_client.virtual_machines.get.return_value = mock_vm
        azure.network_client.network_interfaces.get.return_value = mock_nic

        subnet, vnet, ip, net_rg, location = azure.get_network_interface("test-node", "test-rg")

        self.assertEqual(subnet, "test-subnet")
        self.assertEqual(vnet, "test-vnet")
        self.assertEqual(ip, "10.0.1.5")
        self.assertEqual(net_rg, "network-rg")
        self.assertEqual(location, "eastus")

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_start_instances_success(self, mock_credential, mock_compute, mock_network, mock_logging):
        """Test start_instances successfully starts VM"""
        azure = Azure()

        mock_operation = Mock()
        azure.compute_client.virtual_machines.begin_start.return_value = mock_operation

        azure.start_instances("test-rg", "test-vm")

        azure.compute_client.virtual_machines.begin_start.assert_called_once_with("test-rg", "test-vm")
        mock_logging.assert_called()
        self.assertIn("started", str(mock_logging.call_args))

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_start_instances_failure(self, mock_credential, mock_compute, mock_network, mock_logging):
        """Test start_instances handles failure"""
        azure = Azure()

        azure.compute_client.virtual_machines.begin_start.side_effect = Exception("Start failed")

        with self.assertRaises(RuntimeError):
            azure.start_instances("test-rg", "test-vm")

        mock_logging.assert_called()
        self.assertIn("Failed to start", str(mock_logging.call_args))

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_stop_instances_success(self, mock_credential, mock_compute, mock_network, mock_logging):
        """Test stop_instances successfully stops VM"""
        azure = Azure()

        mock_operation = Mock()
        azure.compute_client.virtual_machines.begin_power_off.return_value = mock_operation

        azure.stop_instances("test-rg", "test-vm")

        azure.compute_client.virtual_machines.begin_power_off.assert_called_once_with("test-rg", "test-vm")
        mock_logging.assert_called()
        self.assertIn("stopped", str(mock_logging.call_args))

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_stop_instances_failure(self, mock_credential, mock_compute, mock_network, mock_logging):
        """Test stop_instances handles failure"""
        azure = Azure()

        azure.compute_client.virtual_machines.begin_power_off.side_effect = Exception("Stop failed")

        with self.assertRaises(RuntimeError):
            azure.stop_instances("test-rg", "test-vm")

        mock_logging.assert_called()
        self.assertIn("Failed to stop", str(mock_logging.call_args))

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_terminate_instances_success(self, mock_credential, mock_compute, mock_network, mock_logging):
        """Test terminate_instances successfully deletes VM"""
        azure = Azure()

        mock_operation = Mock()
        azure.compute_client.virtual_machines.begin_delete.return_value = mock_operation

        azure.terminate_instances("test-rg", "test-vm")

        azure.compute_client.virtual_machines.begin_delete.assert_called_once_with("test-rg", "test-vm")
        mock_logging.assert_called()
        self.assertIn("terminated", str(mock_logging.call_args))

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_terminate_instances_failure(self, mock_credential, mock_compute, mock_network, mock_logging):
        """Test terminate_instances handles failure"""
        azure = Azure()

        azure.compute_client.virtual_machines.begin_delete.side_effect = Exception("Delete failed")

        with self.assertRaises(RuntimeError):
            azure.terminate_instances("test-rg", "test-vm")

        mock_logging.assert_called()
        self.assertIn("Failed to terminate", str(mock_logging.call_args))

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_reboot_instances_success(self, mock_credential, mock_compute, mock_network, mock_logging):
        """Test reboot_instances successfully reboots VM"""
        azure = Azure()

        mock_operation = Mock()
        azure.compute_client.virtual_machines.begin_restart.return_value = mock_operation

        azure.reboot_instances("test-rg", "test-vm")

        azure.compute_client.virtual_machines.begin_restart.assert_called_once_with("test-rg", "test-vm")
        mock_logging.assert_called()
        self.assertIn("rebooted", str(mock_logging.call_args))

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_reboot_instances_failure(self, mock_credential, mock_compute, mock_network, mock_logging):
        """Test reboot_instances handles failure"""
        azure = Azure()

        azure.compute_client.virtual_machines.begin_restart.side_effect = Exception("Reboot failed")

        with self.assertRaises(RuntimeError):
            azure.reboot_instances("test-rg", "test-vm")

        mock_logging.assert_called()
        self.assertIn("Failed to reboot", str(mock_logging.call_args))

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_get_vm_status(self, mock_credential, mock_compute, mock_network):
        """Test get_vm_status returns VM power state"""
        azure = Azure()

        mock_status1 = Mock()
        mock_status1.code = "ProvisioningState/succeeded"
        mock_status2 = Mock()
        mock_status2.code = "PowerState/running"

        mock_instance_view = Mock()
        mock_instance_view.statuses = [mock_status1, mock_status2]
        azure.compute_client.virtual_machines.instance_view.return_value = mock_instance_view

        status = azure.get_vm_status("test-rg", "test-vm")

        self.assertEqual(status.code, "PowerState/running")

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_wait_until_running_success(self, mock_credential, mock_compute, mock_network, mock_logging, mock_sleep):
        """Test wait_until_running waits for VM to be running"""
        azure = Azure()

        mock_status_starting = Mock()
        mock_status_starting.code = "PowerState/starting"
        mock_status_running = Mock()
        mock_status_running.code = "PowerState/running"

        mock_instance_view1 = Mock()
        mock_instance_view1.statuses = [Mock(), mock_status_starting]
        mock_instance_view2 = Mock()
        mock_instance_view2.statuses = [Mock(), mock_status_running]

        azure.compute_client.virtual_machines.instance_view.side_effect = [
            mock_instance_view1,
            mock_instance_view2
        ]

        mock_affected_node = Mock(spec=AffectedNode)

        result = azure.wait_until_running("test-rg", "test-vm", 300, mock_affected_node)

        self.assertTrue(result)
        mock_affected_node.set_affected_node_status.assert_called_once()
        args = mock_affected_node.set_affected_node_status.call_args[0]
        self.assertEqual(args[0], "running")

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_wait_until_running_timeout(self, mock_credential, mock_compute, mock_network, mock_logging, mock_sleep):
        """Test wait_until_running returns False on timeout"""
        azure = Azure()

        mock_status = Mock()
        mock_status.code = "PowerState/starting"
        mock_instance_view = Mock()
        mock_instance_view.statuses = [Mock(), mock_status]

        azure.compute_client.virtual_machines.instance_view.return_value = mock_instance_view

        result = azure.wait_until_running("test-rg", "test-vm", 10, None)

        self.assertFalse(result)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_wait_until_stopped_success(self, mock_credential, mock_compute, mock_network, mock_logging, mock_sleep):
        """Test wait_until_stopped waits for VM to be stopped"""
        azure = Azure()

        mock_status_stopping = Mock()
        mock_status_stopping.code = "PowerState/stopping"
        mock_status_stopped = Mock()
        mock_status_stopped.code = "PowerState/stopped"

        mock_instance_view1 = Mock()
        mock_instance_view1.statuses = [Mock(), mock_status_stopping]
        mock_instance_view2 = Mock()
        mock_instance_view2.statuses = [Mock(), mock_status_stopped]

        azure.compute_client.virtual_machines.instance_view.side_effect = [
            mock_instance_view1,
            mock_instance_view2
        ]

        mock_affected_node = Mock(spec=AffectedNode)

        result = azure.wait_until_stopped("test-rg", "test-vm", 300, mock_affected_node)

        self.assertTrue(result)
        mock_affected_node.set_affected_node_status.assert_called_once()

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_wait_until_stopped_timeout(self, mock_credential, mock_compute, mock_network, mock_logging, mock_sleep):
        """Test wait_until_stopped returns False on timeout"""
        azure = Azure()

        mock_status = Mock()
        mock_status.code = "PowerState/stopping"
        mock_instance_view = Mock()
        mock_instance_view.statuses = [Mock(), mock_status]

        azure.compute_client.virtual_machines.instance_view.return_value = mock_instance_view

        result = azure.wait_until_stopped("test-rg", "test-vm", 10, None)

        self.assertFalse(result)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_wait_until_terminated_success(self, mock_credential, mock_compute, mock_network, mock_logging, mock_sleep):
        """Test wait_until_terminated waits for VM deletion"""
        azure = Azure()

        mock_status_deleting = Mock()
        mock_status_deleting.code = "ProvisioningState/deleting"
        mock_instance_view = Mock()
        mock_instance_view.statuses = [mock_status_deleting]

        # First call returns deleting, second raises exception (VM deleted)
        azure.compute_client.virtual_machines.instance_view.side_effect = [
            mock_instance_view,
            Exception("VM not found")
        ]

        mock_affected_node = Mock(spec=AffectedNode)

        result = azure.wait_until_terminated("test-rg", "test-vm", 300, mock_affected_node)

        self.assertTrue(result)
        mock_affected_node.set_affected_node_status.assert_called_once()
        args = mock_affected_node.set_affected_node_status.call_args[0]
        self.assertEqual(args[0], "terminated")

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_wait_until_terminated_timeout(self, mock_credential, mock_compute, mock_network, mock_logging, mock_sleep):
        """Test wait_until_terminated returns False on timeout"""
        azure = Azure()

        mock_status = Mock()
        mock_status.code = "ProvisioningState/deleting"
        mock_instance_view = Mock()
        mock_instance_view.statuses = [mock_status]

        azure.compute_client.virtual_machines.instance_view.return_value = mock_instance_view

        result = azure.wait_until_terminated("test-rg", "test-vm", 10, None)

        self.assertFalse(result)

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_create_security_group(self, mock_credential, mock_compute, mock_network):
        """Test create_security_group creates NSG with deny rules"""
        azure = Azure()

        mock_nsg_result = Mock()
        mock_nsg_result.id = "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Network/networkSecurityGroups/chaos"
        mock_operation = Mock()
        mock_operation.result.return_value = mock_nsg_result

        azure.network_client.network_security_groups.begin_create_or_update.return_value = mock_operation

        nsg_id = azure.create_security_group("test-rg", "chaos", "eastus", "10.0.1.5")

        self.assertEqual(nsg_id, mock_nsg_result.id)
        azure.network_client.network_security_groups.begin_create_or_update.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_delete_security_group(self, mock_credential, mock_compute, mock_network):
        """Test delete_security_group deletes NSG"""
        azure = Azure()

        mock_operation = Mock()
        mock_operation.result.return_value = None
        azure.network_client.network_security_groups.begin_delete.return_value = mock_operation

        azure.delete_security_group("test-rg", "chaos")

        azure.network_client.network_security_groups.begin_delete.assert_called_once_with("test-rg", "chaos")

    @patch('builtins.print')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_delete_security_group_with_result(self, mock_credential, mock_compute, mock_network, mock_print):
        """Test delete_security_group deletes NSG with non-None result"""
        azure = Azure()

        mock_result = Mock()
        mock_result.as_dict.return_value = {"id": "/test-nsg-id", "name": "chaos"}
        mock_operation = Mock()
        mock_operation.result.return_value = mock_result
        azure.network_client.network_security_groups.begin_delete.return_value = mock_operation

        azure.delete_security_group("test-rg", "chaos")

        azure.network_client.network_security_groups.begin_delete.assert_called_once_with("test-rg", "chaos")
        mock_result.as_dict.assert_called_once()
        mock_print.assert_called_once_with({"id": "/test-nsg-id", "name": "chaos"})

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.NetworkManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.ComputeManagementClient')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.DefaultAzureCredential')
    def test_update_subnet(self, mock_credential, mock_compute, mock_network):
        """Test update_subnet updates subnet NSG"""
        azure = Azure()

        # Mock existing subnet
        mock_old_nsg = Mock()
        mock_old_nsg.id = "/old-nsg-id"
        mock_subnet = Mock()
        mock_subnet.network_security_group = mock_old_nsg

        azure.network_client.subnets.get.return_value = mock_subnet

        old_nsg = azure.update_subnet("/new-nsg-id", "test-rg", "test-subnet", "test-vnet")

        self.assertEqual(old_nsg, "/old-nsg-id")
        azure.network_client.subnets.begin_create_or_update.assert_called_once()


class TestAzureNodeScenarios(unittest.TestCase):
    """Test suite for azure_node_scenarios class"""

    def setUp(self):
        """Set up test fixtures"""
        self.env_patcher = patch.dict('os.environ', {'AZURE_SUBSCRIPTION_ID': 'test-subscription-id'})
        self.env_patcher.start()

        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.affected_nodes_status = AffectedNodeStatus()

    def tearDown(self):
        """Clean up after tests"""
        self.env_patcher.stop()

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_init(self, mock_azure_class, mock_logging):
        """Test azure_node_scenarios initialization"""
        mock_azure_instance = Mock()
        mock_azure_class.return_value = mock_azure_instance

        scenarios = azure_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        self.assertEqual(scenarios.kubecli, self.mock_kubecli)
        self.assertTrue(scenarios.node_action_kube_check)
        self.assertEqual(scenarios.azure, mock_azure_instance)

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_start_scenario_success(self, mock_azure_class, mock_logging, mock_nodeaction):
        """Test node_start_scenario successfully starts node"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.wait_until_running.return_value = True

        scenarios = azure_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        scenarios.node_start_scenario(1, "test-node", 300, 15)

        mock_azure.get_instance_id.assert_called_once_with("test-node")
        mock_azure.start_instances.assert_called_once_with("test-rg", "test-vm")
        mock_azure.wait_until_running.assert_called_once()
        mock_nodeaction.wait_for_ready_status.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_start_scenario_no_kube_check(self, mock_azure_class, mock_logging, mock_nodeaction):
        """Test node_start_scenario without Kubernetes check"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.wait_until_running.return_value = True

        scenarios = azure_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        scenarios.node_start_scenario(1, "test-node", 300, 15)

        mock_azure.start_instances.assert_called_once()
        mock_nodeaction.wait_for_ready_status.assert_not_called()

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_start_scenario_failure(self, mock_azure_class, mock_logging):
        """Test node_start_scenario handles failure"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.start_instances.side_effect = Exception("Start failed")

        scenarios = azure_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        with self.assertRaises(RuntimeError):
            scenarios.node_start_scenario(1, "test-node", 300, 15)

        mock_logging.assert_called()
        # Check that failure was logged (either specific or general injection failed message)
        call_str = str(mock_logging.call_args)
        self.assertTrue("Failed to start" in call_str or "injection failed" in call_str)

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_start_scenario_multiple_runs(self, mock_azure_class, mock_logging, mock_nodeaction):
        """Test node_start_scenario with multiple runs"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.wait_until_running.return_value = True

        scenarios = azure_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        scenarios.node_start_scenario(3, "test-node", 300, 15)

        self.assertEqual(mock_azure.start_instances.call_count, 3)
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 3)

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_stop_scenario_success(self, mock_azure_class, mock_logging, mock_nodeaction):
        """Test node_stop_scenario successfully stops node"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.wait_until_stopped.return_value = True

        scenarios = azure_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        scenarios.node_stop_scenario(1, "test-node", 300, 15)

        mock_azure.get_instance_id.assert_called_once_with("test-node")
        mock_azure.stop_instances.assert_called_once_with("test-rg", "test-vm")
        mock_azure.wait_until_stopped.assert_called_once()
        mock_nodeaction.wait_for_unknown_status.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_stop_scenario_failure(self, mock_azure_class, mock_logging):
        """Test node_stop_scenario handles failure"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.stop_instances.side_effect = Exception("Stop failed")

        scenarios = azure_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        with self.assertRaises(RuntimeError):
            scenarios.node_stop_scenario(1, "test-node", 300, 15)

        mock_logging.assert_called()
        # Check that failure was logged
        call_str = str(mock_logging.call_args)
        self.assertTrue("Failed to stop" in call_str or "injection failed" in call_str)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_termination_scenario_success(self, mock_azure_class, mock_logging, mock_sleep):
        """Test node_termination_scenario successfully terminates node"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.wait_until_terminated.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["other-node"]

        scenarios = azure_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        scenarios.node_termination_scenario(1, "test-node", 300, 15)

        mock_azure.terminate_instances.assert_called_once_with("test-rg", "test-vm")
        mock_azure.wait_until_terminated.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('time.sleep')
    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_termination_scenario_node_still_exists(self, mock_azure_class, mock_logging, mock_sleep):
        """Test node_termination_scenario when node still exists after timeout"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.wait_until_terminated.return_value = True

        # Node still in list after termination attempt
        self.mock_kubecli.list_nodes.return_value = ["test-vm", "other-node"]

        scenarios = azure_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        with self.assertRaises(RuntimeError):
            scenarios.node_termination_scenario(1, "test-node", 5, 15)

        mock_logging.assert_called()
        # Check that failure was logged
        call_str = str(mock_logging.call_args)
        self.assertTrue("Failed to terminate" in call_str or "injection failed" in call_str)

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_reboot_scenario_success(self, mock_azure_class, mock_logging, mock_nodeaction):
        """Test node_reboot_scenario successfully reboots node"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")

        scenarios = azure_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        scenarios.node_reboot_scenario(1, "test-node", 300, soft_reboot=False)

        mock_azure.reboot_instances.assert_called_once_with("test-rg", "test-vm")
        mock_nodeaction.wait_for_ready_status.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_reboot_scenario_failure(self, mock_azure_class, mock_logging):
        """Test node_reboot_scenario handles failure"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.reboot_instances.side_effect = Exception("Reboot failed")

        scenarios = azure_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        with self.assertRaises(RuntimeError):
            scenarios.node_reboot_scenario(1, "test-node", 300)

        mock_logging.assert_called()
        # Check that failure was logged
        call_str = str(mock_logging.call_args)
        self.assertTrue("Failed to reboot" in call_str or "injection failed" in call_str)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_block_scenario_success(self, mock_azure_class, mock_logging, mock_sleep):
        """Test node_block_scenario successfully blocks and unblocks node"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.get_network_interface.return_value = (
            "test-subnet", "test-vnet", "10.0.1.5", "network-rg", "eastus"
        )
        mock_azure.create_security_group.return_value = "/new-nsg-id"
        mock_azure.update_subnet.return_value = "/old-nsg-id"

        scenarios = azure_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        scenarios.node_block_scenario(1, "test-node", 300, 60)

        mock_azure.create_security_group.assert_called_once()
        # Should be called twice: once to apply block, once to remove
        self.assertEqual(mock_azure.update_subnet.call_count, 2)
        mock_azure.delete_security_group.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('time.sleep')
    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_block_scenario_failure(self, mock_azure_class, mock_logging, mock_sleep):
        """Test node_block_scenario handles failure"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.get_network_interface.side_effect = Exception("Network error")

        scenarios = azure_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        with self.assertRaises(RuntimeError):
            scenarios.node_block_scenario(1, "test-node", 300, 60)

        mock_logging.assert_called()
        # Check that failure was logged
        call_str = str(mock_logging.call_args)
        self.assertTrue("Failed to block" in call_str or "injection failed" in call_str)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_node_block_scenario_duration_timing(self, mock_azure_class, mock_logging, mock_sleep):
        """Test node_block_scenario waits for specified duration"""
        mock_azure = Mock()
        mock_azure_class.return_value = mock_azure
        mock_azure.get_instance_id.return_value = ("test-vm", "test-rg")
        mock_azure.get_network_interface.return_value = (
            "test-subnet", "test-vnet", "10.0.1.5", "network-rg", "eastus"
        )
        mock_azure.create_security_group.return_value = "/new-nsg-id"
        mock_azure.update_subnet.return_value = "/old-nsg-id"

        scenarios = azure_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        scenarios.node_block_scenario(1, "test-node", 300, 120)

        # Verify sleep was called with the correct duration
        mock_sleep.assert_called_with(120)


if __name__ == "__main__":
    unittest.main()
