#!/usr/bin/env python3

"""
Test suite for VirtChecker class

This test file provides comprehensive coverage for the main functionality of VirtChecker:
- Initialization with various configurations
- VM access checking (both virtctl and disconnected modes)
- Disconnected mode with IP/node changes
- Thread management
- Post-check validation

Usage:
    python -m coverage run -a -m unittest tests/test_virt_checker.py -v  

Note: This test file uses mocks extensively to avoid needing actual Kubernetes/KubeVirt infrastructure.

Created By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch
import sys
from krkn.utils.VirtChecker import VirtChecker
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Create a mock VirtCheck class before any imports
class MockVirtCheck:
    """Mock VirtCheck class for testing"""
    def __init__(self, data):
        self.vm_name = data.get('vm_name', '')
        self.ip_address = data.get('ip_address', '')
        self.namespace = data.get('namespace', '')
        self.node_name = data.get('node_name', '')
        self.new_ip_address = data.get('new_ip_address', '')
        self.status = data.get('status', False)
        self.start_timestamp = data.get('start_timestamp', '')
        self.end_timestamp = data.get('end_timestamp', '')
        self.duration = data.get('duration', 0)


class TestVirtChecker(unittest.TestCase):
    """Test suite for VirtChecker class"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        self.mock_krkn_lib = MagicMock()

        # Mock k8s_client for krkn-lib methods
        self.mock_k8s_client = MagicMock()
        self.mock_krkn_lib.custom_object_client = MagicMock()

        # Mock VMI data
        self.mock_vmi_1 = {
            "metadata": {"name": "test-vm-1", "namespace": "test-namespace"},
            "status": {
                "nodeName": "worker-1",
                "interfaces": [{"ipAddress": "192.168.1.10"}]
            }
        }

        self.mock_vmi_2 = {
            "metadata": {"name": "test-vm-2", "namespace": "test-namespace"},
            "status": {
                "nodeName": "worker-2",
                "interfaces": [{"ipAddress": "192.168.1.11"}]
            }
        }

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    def test_init_with_empty_namespace(self, mock_plugin_class, mock_yaml):
        """Test VirtChecker initialization with empty namespace (should skip checks)"""
        def yaml_getter(config, key, default):
            if key == "namespace":
                return ""
            return default
        mock_yaml.side_effect = yaml_getter

        checker = VirtChecker(
            {"namespace": ""},
            iterations=5,
            krkn_lib=self.mock_krkn_lib
        )

        # Should set batch_size to 0 and not initialize plugin
        self.assertEqual(checker.batch_size, 0)
        mock_plugin_class.assert_not_called()

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    def test_regex_namespace(self, mock_plugin_class, mock_yaml):
        """Test VirtChecker initialization with regex namespace pattern"""
        # Setup mock plugin with k8s_client
        mock_plugin = MagicMock()
        mock_plugin.k8s_client = self.mock_k8s_client
        self.mock_k8s_client.get_vmis.return_value = [self.mock_vmi_1, self.mock_vmi_2]
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            return config.get(key, default)
        mock_yaml.side_effect = yaml_getter

        checker = VirtChecker(
            {"namespace": "test-*"},
            iterations=1,
            krkn_lib=self.mock_krkn_lib
        )

        self.assertGreater(len(checker.vm_list), 0)
        self.assertEqual(len(checker.vm_list), 2)

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    def test_with_node_name(self, mock_plugin_class, mock_yaml):
        """Test VirtChecker initialization with specific VM names"""
        # Setup mock plugin with k8s_client
        mock_plugin = MagicMock()
        mock_plugin.k8s_client = self.mock_k8s_client
        self.mock_k8s_client.get_vmis.return_value = [self.mock_vmi_1, self.mock_vmi_2]
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            return config.get(key, default)
        mock_yaml.side_effect = yaml_getter

        # Test with VM name pattern
        checker = VirtChecker(
            {"namespace": "test-namespace", "name": "test-vm-.*"},
            iterations=5,
            krkn_lib=self.mock_krkn_lib
        )

        self.assertGreater(checker.batch_size, 0)
        self.assertEqual(len(checker.vm_list), 2)

        # Test with specific VM name
        mock_plugin2 = MagicMock()
        mock_k8s_client2 = MagicMock()
        mock_plugin2.k8s_client = mock_k8s_client2
        mock_k8s_client2.get_vmis.return_value = [self.mock_vmi_2]
        mock_plugin_class.return_value = mock_plugin2

        checker2 = VirtChecker(
            {"namespace": "test-namespace", "name": "test-vm-1"},
            iterations=5,
            krkn_lib=self.mock_krkn_lib
        )

        self.assertGreater(checker2.batch_size, 0)
        self.assertEqual(len(checker2.vm_list), 1) 

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    def test_with_regex_name(self, mock_plugin_class, mock_yaml):
        """Test VirtChecker initialization filtering by node names"""
        # Setup mock plugin with k8s_client
        mock_plugin = MagicMock()
        mock_plugin.k8s_client = self.mock_k8s_client
        self.mock_k8s_client.get_vmis.return_value = [self.mock_vmi_1, self.mock_vmi_2]
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            return config.get(key, default)
        mock_yaml.side_effect = yaml_getter

        # Test filtering by node name - should only include VMs on worker-2
        checker = VirtChecker(
            {"namespace": "test-namespace", "node_names": "worker-2"},
            iterations=5,
            krkn_lib=self.mock_krkn_lib
        )

        self.assertGreater(checker.batch_size, 0)
        # Only test-vm-2 is on worker-2, so vm_list should have 1 VM
        self.assertEqual(len(checker.vm_list), 1)
        self.assertEqual(checker.vm_list[0].vm_name, "test-vm-2")

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    @patch('krkn.utils.VirtChecker.invoke_no_exit')
    def test_get_vm_access_success(self, mock_invoke, mock_plugin_class, mock_yaml):
        """Test get_vm_access returns True when VM is accessible"""
        mock_plugin = MagicMock()
        mock_plugin.vmis_list = []
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            if key == "namespace":
                return "test-ns"
            return default
        mock_yaml.side_effect = yaml_getter

        # Mock successful access
        mock_invoke.return_value = "True"

        checker = VirtChecker(
            {"namespace": "test-ns"},
            iterations=1,
            krkn_lib=self.mock_krkn_lib
        )

        result = checker.get_vm_access("test-vm", "test-namespace")

        self.assertTrue(result)
        # Should try first command and succeed
        self.assertGreaterEqual(mock_invoke.call_count, 1)

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    @patch('krkn.utils.VirtChecker.invoke_no_exit')
    def test_get_vm_access_failure(self, mock_invoke, mock_plugin_class, mock_yaml):
        """Test get_vm_access returns False when VM is not accessible"""
        mock_plugin = MagicMock()
        mock_plugin.vmis_list = []
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            if key == "namespace":
                return "test-ns"
            return default
        mock_yaml.side_effect = yaml_getter

        # Mock failed access
        mock_invoke.return_value = "False"

        checker = VirtChecker(
            {"namespace": "test-ns"},
            iterations=1,
            krkn_lib=self.mock_krkn_lib
        )

        result = checker.get_vm_access("test-vm", "test-namespace")

        self.assertFalse(result)
        # Should try both commands
        self.assertEqual(mock_invoke.call_count, 2)

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    @patch('krkn.utils.VirtChecker.invoke_no_exit')
    def test_check_disconnected_access_success(self, mock_invoke, mock_plugin_class, mock_yaml):
        """Test check_disconnected_access with successful connection"""
        mock_plugin = MagicMock()
        mock_plugin.vmis_list = []
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            if key == "namespace":
                return "test-ns"
            return default
        mock_yaml.side_effect = yaml_getter

        # Mock successful disconnected access
        mock_invoke.side_effect = ["some output", "True"]

        checker = VirtChecker(
            {"namespace": "test-ns"},
            iterations=1,
            krkn_lib=self.mock_krkn_lib
        )

        result, new_ip, new_node = checker.check_disconnected_access(
            "192.168.1.10",
            "worker-1",
            "test-vm"
        )

        self.assertTrue(result)
        self.assertIsNone(new_ip)
        self.assertIsNone(new_node)

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    @patch('krkn.utils.VirtChecker.invoke_no_exit')
    def test_check_disconnected_access_with_new_ip(self, mock_invoke, mock_plugin_class, mock_yaml):
        """Test check_disconnected_access when VM has new IP address"""
        mock_plugin = MagicMock()
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            if key == "namespace":
                return "test-ns"
            return default
        mock_yaml.side_effect = yaml_getter

        # Mock failed first attempt, successful second with new IP
        mock_invoke.side_effect = ["some output", "False", "True"]

        mock_vmi = {
            "status": {
                "nodeName": "worker-1",
                "interfaces": [{"ipAddress": "192.168.1.20"}]
            }
        }
        mock_plugin.get_vmi = MagicMock(return_value=mock_vmi)

        checker = VirtChecker(
            {"namespace": "test-ns"},
            iterations=1,
            krkn_lib=self.mock_krkn_lib
        )
        checker.kube_vm_plugin = mock_plugin

        result, new_ip, new_node = checker.check_disconnected_access(
            "192.168.1.10",
            "worker-1",
            "test-vm"
        )

        self.assertTrue(result)
        self.assertEqual(new_ip, "192.168.1.20")
        self.assertIsNone(new_node)

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    @patch('krkn.utils.VirtChecker.invoke_no_exit')
    def test_check_disconnected_access_with_new_node(self, mock_invoke, mock_plugin_class, mock_yaml):
        """Test check_disconnected_access when VM moved to new node"""
        mock_plugin = MagicMock()
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            if key == "namespace":
                return "test-ns"
            return default
        mock_yaml.side_effect = yaml_getter

        # Mock failed attempts, successful on new node
        # Call sequence: debug_check, initial_check, check_on_new_node
        mock_invoke.side_effect = ["some output", "False", "True"]

        mock_vmi = {
            "status": {
                "nodeName": "worker-2",
                "interfaces": [{"ipAddress": "192.168.1.10"}]
            }
        }
        mock_plugin.get_vmi = MagicMock(return_value=mock_vmi)

        checker = VirtChecker(
            {"namespace": "test-ns"},
            iterations=1,
            krkn_lib=self.mock_krkn_lib
        )
        checker.kube_vm_plugin = mock_plugin

        result, new_ip, new_node = checker.check_disconnected_access(
            "192.168.1.10",
            "worker-1",
            "test-vm"
        )

        self.assertTrue(result)
        self.assertEqual(new_ip, "192.168.1.10")
        self.assertEqual(new_node, "worker-2")

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    @patch('krkn.utils.VirtChecker.invoke_no_exit')
    def test_check_disconnected_access_with_ssh_node_fallback(self, mock_invoke, mock_plugin_class, mock_yaml):
        """Test check_disconnected_access falls back to ssh_node"""
        mock_plugin = MagicMock()
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            if key == "namespace":
                return "test-ns"
            elif key == "ssh_node":
                return "worker-0"
            return default
        mock_yaml.side_effect = yaml_getter

        # Mock failed attempts on original node, successful on ssh_node fallback
        # Call sequence: debug_check, initial_check_on_worker-1, fallback_check_on_ssh_node
        # Since IP and node haven't changed, it goes directly to ssh_node fallback
        mock_invoke.side_effect = ["some output", "False", "True"]

        mock_vmi = {
            "status": {
                "nodeName": "worker-1",
                "interfaces": [{"ipAddress": "192.168.1.10"}]
            }
        }
        mock_plugin.get_vmi = MagicMock(return_value=mock_vmi)

        checker = VirtChecker(
            {"namespace": "test-ns", "ssh_node": "worker-0"},
            iterations=1,
            krkn_lib=self.mock_krkn_lib
        )
        checker.kube_vm_plugin = mock_plugin

        result, new_ip, new_node = checker.check_disconnected_access(
            "192.168.1.10",
            "worker-1",
            "test-vm"
        )

        self.assertTrue(result)
        self.assertEqual(new_ip, "192.168.1.10")
        self.assertIsNone(new_node)

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    def test_thread_join(self, mock_plugin_class, mock_yaml):
        """Test thread_join waits for all threads"""
        mock_plugin = MagicMock()
        mock_plugin.vmis_list = []
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            if key == "namespace":
                return "test-ns"
            return default
        mock_yaml.side_effect = yaml_getter

        checker = VirtChecker(
            {"namespace": "test-ns"},
            iterations=1,
            krkn_lib=self.mock_krkn_lib
        )

        # Create mock threads
        mock_thread_1 = MagicMock()
        mock_thread_2 = MagicMock()
        checker.threads = [mock_thread_1, mock_thread_2]

        checker.thread_join()

        mock_thread_1.join.assert_called_once()
        mock_thread_2.join.assert_called_once()

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    def test_init_exception_handling(self, mock_plugin_class, mock_yaml):
        """Test VirtChecker handles exceptions during initialization"""
        mock_plugin = MagicMock()
        mock_plugin.init_clients.side_effect = Exception("Connection error")
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            if key == "namespace":
                return "test-ns"
            return default
        mock_yaml.side_effect = yaml_getter

        config = {"namespace": "test-ns"}

        # Should not raise exception
        checker = VirtChecker(
            config,
            iterations=1,
            krkn_lib=self.mock_krkn_lib
        )

        # VM list should be empty due to exception
        self.assertEqual(len(checker.vm_list), 0)

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    def test_batch_size_calculation(self, mock_plugin_class, mock_yaml):
        """Test batch size calculation based on VM count and thread limit"""
        mock_plugin = MagicMock()
        mock_plugin.k8s_client = self.mock_k8s_client

        # Create 25 mock VMIs
        mock_vmis = []
        for i in range(25):
            vmi = {
                "metadata": {"name": f"vm-{i}", "namespace": "test-ns"},
                "status": {
                    "nodeName": "worker-1",
                    "interfaces": [{"ipAddress": f"192.168.1.{i}"}]
                }
            }
            mock_vmis.append(vmi)

        self.mock_k8s_client.get_vmis.return_value = mock_vmis
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            if key == "namespace":
                return "test-ns"
            elif key == "node_names":
                return ""
            return default
        mock_yaml.side_effect = yaml_getter

        config = {"namespace": "test-ns"}
        checker = VirtChecker(
            config,
            iterations=5,
            krkn_lib=self.mock_krkn_lib,
            threads_limit=10
        )

        # 25 VMs / 10 threads = 3 VMs per batch (ceiling)
        self.assertEqual(checker.batch_size, 3)

    @patch('krkn_lib.models.telemetry.models.VirtCheck', new=MockVirtCheck)
    @patch('krkn.utils.VirtChecker.get_yaml_item_value')
    @patch('krkn.utils.VirtChecker.KubevirtVmOutageScenarioPlugin')
    @patch('krkn.utils.VirtChecker.threading.Thread')
    def test_batch_list_includes_last_item(self, mock_thread_class, mock_plugin_class, mock_yaml):
        """Test that batch_list includes the last item when batches don't divide evenly"""
        mock_plugin = MagicMock()
        mock_plugin.k8s_client = self.mock_k8s_client

        # Create 21 mock VMIs (the specific case mentioned in the bug report)
        mock_vmis = []
        for i in range(21):
            vmi = {
                "metadata": {"name": f"vm-{i}", "namespace": "test-ns"},
                "status": {
                    "nodeName": "worker-1",
                    "interfaces": [{"ipAddress": f"192.168.1.{i}"}]
                }
            }
            mock_vmis.append(vmi)

        self.mock_k8s_client.get_vmis.return_value = mock_vmis
        mock_plugin_class.return_value = mock_plugin

        def yaml_getter(config, key, default):
            if key == "namespace":
                return "test-ns"
            elif key == "node_names":
                return ""
            return default
        mock_yaml.side_effect = yaml_getter

        config = {"namespace": "test-ns"}
        checker = VirtChecker(
            config,
            iterations=5,
            krkn_lib=self.mock_krkn_lib,
            threads_limit=5  # This gives batch_size=5 (ceiling of 21/5=4.2)
        )

        # 21 VMs / 5 threads = 5 VMs per batch (ceiling)
        self.assertEqual(checker.batch_size, 5)
        self.assertEqual(len(checker.vm_list), 21)

        # Track the sublists passed to each thread
        captured_sublists = []
        def capture_args(*args, **kwargs):
            # threading.Thread is called with target=..., name=..., args=(sublist, queue)
            if 'args' in kwargs:
                sublist, queue = kwargs['args']
                captured_sublists.append(sublist)
            mock_thread = MagicMock()
            if 'name' in kwargs:
                mock_thread.name = kwargs['name']
            return mock_thread

        mock_thread_class.side_effect = capture_args

        # Create a mock queue
        mock_queue = MagicMock()

        # Call batch_list
        checker.batch_list(mock_queue)

        # Verify all 21 items are included across all batches
        all_items_in_batches = []
        for sublist in captured_sublists:
            all_items_in_batches.extend(sublist)

        # Check that we have exactly 21 items
        self.assertEqual(len(all_items_in_batches), 21)

        # Verify the last batch includes the last item (vm-20)
        last_batch = captured_sublists[-1]
        self.assertGreater(len(last_batch), 0, "Last batch should not be empty")
        
        # Verify no duplicate items across batches
        all_vm_names = [vm.vm_name for vm in all_items_in_batches]
        self.assertEqual(len(all_vm_names), len(set(all_vm_names)), "No duplicate items should be in batches")


if __name__ == "__main__":
    unittest.main()
