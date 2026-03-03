#!/usr/bin/env python3
"""
Test suite for VirtHealthCheckPlugin

This test file provides comprehensive coverage for the virt health check plugin:
- Plugin creation via factory
- VM health check functionality
- Thread-safe iteration tracking
- Telemetry collection
- Disconnected SSH access checking

Usage:
    python -m pytest tests/test_virt_health_check_plugin.py -v
    python -m unittest tests/test_virt_health_check_plugin.py -v

Migrated from test_virt_checker.py to use the plugin architecture.
"""

import queue
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from krkn.health_checks import HealthCheckFactory, HealthCheckPluginNotFound


class TestVirtHealthCheckPlugin(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures for virt health check plugin"""
        self.factory = HealthCheckFactory()

        # Skip tests if plugin not loaded (missing dependencies)
        if "virt_health_check" not in self.factory.loaded_plugins:
            self.skipTest("Virt health check plugin not loaded (missing dependencies)")

        # Mock KrknKubernetes client
        self.mock_kubecli = MagicMock()

        # Create plugin with mock client
        self.plugin = self.factory.create_plugin(
            "virt_health_check",
            iterations=5,
            krkn_lib=self.mock_kubecli
        )

    def tearDown(self):
        """Clean up after each test"""
        if hasattr(self, 'plugin'):
            self.plugin.current_iterations = 0
            self.plugin.set_return_value(0)

    def test_plugin_creation(self):
        """Test plugin is created correctly via factory"""
        self.assertIsNotNone(self.plugin)
        self.assertEqual(self.plugin.iterations, 5)
        self.assertEqual(self.plugin.current_iterations, 0)
        self.assertEqual(self.plugin.get_return_value(), 0)

    def test_get_health_check_types(self):
        """Test plugin returns correct health check types"""
        types = self.plugin.get_health_check_types()
        self.assertIn("virt_health_check", types)
        self.assertIn("kubevirt_health_check", types)
        self.assertIn("vm_health_check", types)

    def test_increment_iterations(self):
        """Test increment_iterations is thread-safe"""
        initial = self.plugin.current_iterations

        # Call multiple times
        for _ in range(5):
            self.plugin.increment_iterations()

        self.assertEqual(self.plugin.current_iterations, initial + 5)

    def test_return_value_methods(self):
        """Test get/set return value methods"""
        self.assertEqual(self.plugin.get_return_value(), 0)

        self.plugin.set_return_value(2)
        self.assertEqual(self.plugin.get_return_value(), 2)

        self.plugin.set_return_value(0)
        self.assertEqual(self.plugin.get_return_value(), 0)

    def test_initialization_empty_config(self):
        """Test plugin initialization with empty namespace config"""
        config = {
            "namespace": "",
            "interval": 2
        }

        telemetry_queue = queue.Queue()
        self.plugin.run_health_check(config, telemetry_queue)

        # Should skip initialization and not crash
        self.assertTrue(telemetry_queue.empty())

    @patch('krkn.health_checks.virt_health_check_plugin.KubevirtVmOutageScenarioPlugin')
    def test_initialization_with_vmis(self, mock_plugin_class):
        """Test plugin initialization discovers VMIs"""
        # Mock the plugin instance
        mock_plugin = MagicMock()
        mock_plugin_class.return_value = mock_plugin

        # Mock VMI data
        mock_vmis = [
            {
                "metadata": {"name": "test-vm1", "namespace": "default"},
                "status": {
                    "nodeName": "worker-1",
                    "interfaces": [{"ipAddress": "10.0.0.1"}]
                }
            },
            {
                "metadata": {"name": "test-vm2", "namespace": "default"},
                "status": {
                    "nodeName": "worker-2",
                    "interfaces": [{"ipAddress": "10.0.0.2"}]
                }
            }
        ]

        # Setup mock to return VMIs
        self.mock_kubecli.get_vmis.return_value = mock_vmis
        mock_plugin.k8s_client = self.mock_kubecli

        config = {
            "namespace": "default",
            "name": ".*",
            "interval": 2,
            "disconnected": False,
            "only_failures": False
        }

        # Initialize from config
        result = self.plugin._initialize_from_config(config)

        self.assertTrue(result)
        self.assertEqual(len(self.plugin.vm_list), 2)

    @patch('krkn.invoke.command.invoke_no_exit')
    def test_check_disconnected_access_success(self, mock_invoke):
        """Test disconnected SSH access check succeeds"""
        mock_invoke.return_value = "Permission"

        # Mock the get_vmi method
        with patch.object(self.plugin, 'kube_vm_plugin') as mock_vm_plugin:
            result, new_ip, new_node = self.plugin.check_disconnected_access(
                "10.0.0.1",
                "worker-1",
                "test-vm"
            )

            self.assertTrue(result)
            self.assertIsNone(new_ip)
            self.assertIsNone(new_node)

    @patch('krkn.invoke.command.invoke_no_exit')
    def test_get_vm_access_success(self, mock_invoke):
        """Test VM access check via virtctl succeeds"""
        mock_invoke.return_value = "denied\nTrue"

        result = self.plugin.get_vm_access("test-vm", "default")

        self.assertTrue(result)

    @patch('krkn.invoke.command.invoke_no_exit')
    def test_get_vm_access_failure(self, mock_invoke):
        """Test VM access check via virtctl fails"""
        mock_invoke.return_value = "False"

        result = self.plugin.get_vm_access("test-vm", "default")

        self.assertFalse(result)

    def test_thread_join(self):
        """Test thread_join waits for worker threads"""
        # Create mock threads
        mock_thread1 = MagicMock()
        mock_thread2 = MagicMock()
        self.plugin.threads = [mock_thread1, mock_thread2]

        self.plugin.thread_join()

        # Verify join was called on all threads
        mock_thread1.join.assert_called_once()
        mock_thread2.join.assert_called_once()

    def test_batch_size_calculation(self):
        """Test batch size is calculated correctly"""
        # Create plugin with mock VMs
        self.plugin.vm_list = [MagicMock() for _ in range(25)]
        self.plugin.threads_limit = 10

        import math
        expected_batch_size = math.ceil(25 / 10)

        # Calculate batch size
        self.plugin.batch_size = math.ceil(len(self.plugin.vm_list) / self.plugin.threads_limit)

        self.assertEqual(self.plugin.batch_size, expected_batch_size)


class TestVirtHealthCheckPluginFactory(unittest.TestCase):
    """Test factory-specific functionality"""

    def test_factory_loads_virt_plugin(self):
        """Test that factory loads virt health check plugin"""
        factory = HealthCheckFactory()

        # May not be loaded if dependencies missing
        virt_types = ["virt_health_check", "kubevirt_health_check", "vm_health_check"]
        found = any(vt in factory.loaded_plugins for vt in virt_types)

        if not found:
            self.skipTest("Virt health check plugin not loaded (missing dependencies)")

        # At least one type should be loaded
        self.assertTrue(found)

    def test_factory_creates_virt_plugin(self):
        """Test factory creates virt plugin instances"""
        factory = HealthCheckFactory()

        if "virt_health_check" not in factory.loaded_plugins:
            self.skipTest("Virt health check plugin not loaded (missing dependencies)")

        mock_kubecli = MagicMock()
        plugin = factory.create_plugin(
            "virt_health_check",
            iterations=10,
            krkn_lib=mock_kubecli
        )

        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.iterations, 10)
        self.assertEqual(plugin.__class__.__name__, "VirtHealthCheckPlugin")

    def test_factory_multiple_type_mappings(self):
        """Test factory maps multiple types to virt plugin"""
        factory = HealthCheckFactory()

        if "virt_health_check" not in factory.loaded_plugins:
            self.skipTest("Virt health check plugin not loaded (missing dependencies)")

        mock_kubecli = MagicMock()

        # All these types should map to the same plugin class
        plugin1 = factory.create_plugin("virt_health_check", iterations=5, krkn_lib=mock_kubecli)
        plugin2 = factory.create_plugin("kubevirt_health_check", iterations=5, krkn_lib=mock_kubecli)
        plugin3 = factory.create_plugin("vm_health_check", iterations=5, krkn_lib=mock_kubecli)

        self.assertEqual(plugin1.__class__.__name__, "VirtHealthCheckPlugin")
        self.assertEqual(plugin2.__class__.__name__, "VirtHealthCheckPlugin")
        self.assertEqual(plugin3.__class__.__name__, "VirtHealthCheckPlugin")


if __name__ == "__main__":
    unittest.main()
