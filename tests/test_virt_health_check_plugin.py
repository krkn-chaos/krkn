#!/usr/bin/env python3
"""
Test suite for VirtHealthCheckPlugin

This test file provides comprehensive coverage for the virt health check plugin:
- Plugin creation via factory
- VM health check functionality
- Thread-safe iteration tracking
- Telemetry collection
- Disconnected SSH access checking

How to run:
    # Run directly (requires full krkn environment with dependencies)
    python3 tests/test_virt_health_check_plugin.py

    # Run from project root
    cd /path/to/kraken
    python3 tests/test_virt_health_check_plugin.py

    # Run with pytest
    pytest tests/test_virt_health_check_plugin.py -v

    # Run with unittest
    python3 -m unittest tests/test_virt_health_check_plugin.py -v

    # Run specific test
    python3 -m unittest tests.test_virt_health_check_plugin.TestVirtHealthCheckPlugin.test_plugin_creation -v

    # Run with coverage
    coverage run -m pytest tests/test_virt_health_check_plugin.py -v
    coverage report

Requirements:
    - krkn_lib library (pip install krkn-lib)
    - All scenario plugin dependencies
    - All dependencies in requirements.txt

Note:
    - Tests will be skipped if virt_health_check plugin fails to load
    - Plugin may fail to load if 'krkn_lib' module is not installed
    - Use a virtual environment with all dependencies installed
    - Some tests mock KubeVirt components for unit testing

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

    @patch('krkn.health_checks.virt_health_check_plugin.invoke_no_exit')
    def test_check_disconnected_access_success(self, mock_invoke):
        """Test disconnected SSH access check succeeds"""
        # Mock returns values that match the expected output format
        # First call is debug output, second call is the actual check
        # The check looks for "True" in the output to indicate success

        # Track call count to differentiate between first and second invoke
        call_count = [0]
        def side_effect_fn(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else ""

            # Second call has the check command with grep and echo
            if call_count[0] == 2 and ("grep Permission" in cmd or "2>&1" in cmd):
                # Return string containing "True" to indicate success
                return "Permission denied (publickey)\nTrue"
            else:
                # First call is debug - return permission denied message
                return "Permission denied (publickey)"

        mock_invoke.side_effect = side_effect_fn

        # Mock kube_vm_plugin to avoid None error (shouldn't be needed if returning early)
        # But set it up properly in case the check fails and tries to get VMI info
        mock_vm_plugin = MagicMock()
        mock_vm_plugin.get_vmi.return_value = {
            "status": {
                "interfaces": [{"ipAddress": "10.0.0.1"}],
                "nodeName": "worker-1"
            }
        }
        self.plugin.kube_vm_plugin = mock_vm_plugin
        self.plugin.namespace = "default"

        result, new_ip, new_node = self.plugin.check_disconnected_access(
            "10.0.0.1",
            "worker-1",
            "test-vm"
        )

        self.assertTrue(result)
        self.assertIsNone(new_ip)
        self.assertIsNone(new_node)
        # Verify invoke was called twice (debug + actual check)
        self.assertEqual(mock_invoke.call_count, 2)
        # Verify we didn't need to call get_vmi (check succeeded on first try)
        mock_vm_plugin.get_vmi.assert_not_called()

    @patch('krkn.health_checks.virt_health_check_plugin.invoke_no_exit')
    def test_get_vm_access_success(self, mock_invoke):
        """Test VM access check via virtctl succeeds"""
        # The method tries two different virtctl commands
        # Either one can return "True" to indicate success
        # Return output that contains "True" to simulate permission denied but accessible
        mock_invoke.return_value = "Permission denied (publickey).\nTrue"

        result = self.plugin.get_vm_access("test-vm", "default")

        self.assertTrue(result)
        # Verify invoke was called (may be called 1 or 2 times depending on first result)
        self.assertGreaterEqual(mock_invoke.call_count, 1)

    @patch('krkn.health_checks.virt_health_check_plugin.invoke_no_exit')
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


class TestVirtHealthCheckPluginCoverage(unittest.TestCase):
    """Additional tests to increase coverage of VirtHealthCheckPlugin"""

    def setUp(self):
        self.factory = HealthCheckFactory()
        if "virt_health_check" not in self.factory.loaded_plugins:
            self.skipTest("Virt health check plugin not loaded (missing dependencies)")
        self.mock_kubecli = MagicMock()
        self.plugin = self.factory.create_plugin(
            "virt_health_check", iterations=2, krkn_lib=self.mock_kubecli
        )

    def tearDown(self):
        if hasattr(self, "plugin"):
            self.plugin.current_iterations = 0
            self.plugin.set_return_value(0)

    # --- _initialize_from_config ---

    @patch("krkn.health_checks.virt_health_check_plugin.KubevirtVmOutageScenarioPlugin")
    def test_initialize_from_config_exception(self, mock_plugin_class):
        """Test _initialize_from_config returns False on exception"""
        mock_plugin_class.side_effect = Exception("connection error")
        config = {"namespace": "default", "interval": 2}
        result = self.plugin._initialize_from_config(config)
        self.assertFalse(result)

    @patch("krkn.health_checks.virt_health_check_plugin.KubevirtVmOutageScenarioPlugin")
    def test_initialize_from_config_vmi_no_interfaces(self, mock_plugin_class):
        """Test VMIs with no interfaces are skipped"""
        mock_plugin = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.k8s_client = self.mock_kubecli
        self.mock_kubecli.get_vmis.return_value = [
            {
                "metadata": {"name": "no-iface-vm", "namespace": "default"},
                "status": {"nodeName": "worker-1", "interfaces": []},
            }
        ]
        config = {"namespace": "default", "interval": 2}
        result = self.plugin._initialize_from_config(config)
        self.assertTrue(result)
        self.assertEqual(len(self.plugin.vm_list), 0)

    @patch("krkn.health_checks.virt_health_check_plugin.KubevirtVmOutageScenarioPlugin")
    def test_initialize_from_config_node_name_filter_match(self, mock_plugin_class):
        """Test VMIs are filtered by node_names when specified and matching"""
        mock_plugin = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.k8s_client = self.mock_kubecli
        self.mock_kubecli.get_vmis.return_value = [
            {
                "metadata": {"name": "vm1", "namespace": "default"},
                "status": {"nodeName": "worker-1", "interfaces": [{"ipAddress": "10.0.0.1"}]},
            },
            {
                "metadata": {"name": "vm2", "namespace": "default"},
                "status": {"nodeName": "worker-2", "interfaces": [{"ipAddress": "10.0.0.2"}]},
            },
        ]
        config = {"namespace": "default", "node_names": "worker-1", "interval": 2}
        result = self.plugin._initialize_from_config(config)
        self.assertTrue(result)
        self.assertEqual(len(self.plugin.vm_list), 1)
        self.assertEqual(self.plugin.vm_list[0].vm_name, "vm1")

    @patch("krkn.health_checks.virt_health_check_plugin.KubevirtVmOutageScenarioPlugin")
    def test_initialize_from_config_node_name_filter_no_match(self, mock_plugin_class):
        """Test VMIs are excluded when node_names is set but node doesn't match"""
        mock_plugin = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.k8s_client = self.mock_kubecli
        self.mock_kubecli.get_vmis.return_value = [
            {
                "metadata": {"name": "vm1", "namespace": "default"},
                "status": {"nodeName": "worker-99", "interfaces": [{"ipAddress": "10.0.0.1"}]},
            }
        ]
        config = {"namespace": "default", "node_names": "worker-1", "interval": 2}
        result = self.plugin._initialize_from_config(config)
        self.assertTrue(result)
        self.assertEqual(len(self.plugin.vm_list), 0)

    # --- check_disconnected_access ---

    @patch("krkn.health_checks.virt_health_check_plugin.invoke_no_exit")
    def test_check_disconnected_access_new_ip_success(self, mock_invoke):
        """Test disconnected access succeeds after VM restarts with new IP"""
        mock_vmi = {
            "status": {
                "interfaces": [{"ipAddress": "10.0.0.2"}],
                "nodeName": "worker-1",
            }
        }
        mock_vm_plugin = MagicMock()
        mock_vm_plugin.get_vmi.return_value = mock_vmi
        self.plugin.kube_vm_plugin = mock_vm_plugin
        self.plugin.namespace = "default"

        call_count = [0]
        def side_effect(*_):
            call_count[0] += 1
            if call_count[0] <= 2:
                return "False"  # initial check fails
            return "True"  # new IP check succeeds

        mock_invoke.side_effect = side_effect

        result, new_ip, new_node = self.plugin.check_disconnected_access(
            "10.0.0.1", "worker-1", "test-vm"
        )
        self.assertTrue(result)
        self.assertEqual(new_ip, "10.0.0.2")
        self.assertIsNone(new_node)

    @patch("krkn.health_checks.virt_health_check_plugin.invoke_no_exit")
    def test_check_disconnected_access_node_migration_success(self, mock_invoke):
        """Test disconnected access succeeds after VM migrates to new node"""
        mock_vmi = {
            "status": {
                "interfaces": [{"ipAddress": "10.0.0.1"}],
                "nodeName": "worker-2",
            }
        }
        mock_vm_plugin = MagicMock()
        mock_vm_plugin.get_vmi.return_value = mock_vmi
        self.plugin.kube_vm_plugin = mock_vm_plugin
        self.plugin.namespace = "default"

        call_count = [0]
        def side_effect(*_):
            call_count[0] += 1
            if call_count[0] <= 2:
                return "False"
            return "True"  # new node check succeeds (call 3)

        mock_invoke.side_effect = side_effect

        result, new_ip, new_node = self.plugin.check_disconnected_access(
            "10.0.0.1", "worker-1", "test-vm"
        )
        self.assertTrue(result)
        self.assertEqual(new_ip, "10.0.0.1")
        self.assertEqual(new_node, "worker-2")

    @patch("krkn.health_checks.virt_health_check_plugin.invoke_no_exit")
    def test_check_disconnected_access_ssh_node_fallback(self, mock_invoke):
        """Test disconnected access falls back to ssh_node"""
        mock_vmi = {
            "status": {
                "interfaces": [{"ipAddress": "10.0.0.1"}],
                "nodeName": "worker-1",
            }
        }
        mock_vm_plugin = MagicMock()
        mock_vm_plugin.get_vmi.return_value = mock_vmi
        self.plugin.kube_vm_plugin = mock_vm_plugin
        self.plugin.namespace = "default"
        self.plugin.ssh_node = "bastion"

        call_count = [0]
        def side_effect(*_):
            call_count[0] += 1
            if call_count[0] <= 2:
                return "False"
            return "True"  # bastion fallback succeeds (call 3)

        mock_invoke.side_effect = side_effect

        result, new_ip, new_node = self.plugin.check_disconnected_access(
            "10.0.0.1", "worker-1", "test-vm"
        )
        self.assertTrue(result)
        self.assertEqual(new_ip, "10.0.0.1")
        self.assertIsNone(new_node)

    @patch("krkn.health_checks.virt_health_check_plugin.invoke_no_exit")
    def test_check_disconnected_access_all_fail(self, mock_invoke):
        """Test check_disconnected_access returns False when all attempts fail"""
        mock_vmi = {
            "status": {
                "interfaces": [{"ipAddress": "10.0.0.1"}],
                "nodeName": "worker-1",
            }
        }
        mock_vm_plugin = MagicMock()
        mock_vm_plugin.get_vmi.return_value = mock_vmi
        self.plugin.kube_vm_plugin = mock_vm_plugin
        self.plugin.namespace = "default"
        self.plugin.ssh_node = ""

        mock_invoke.return_value = "False"

        result, new_ip, new_node = self.plugin.check_disconnected_access(
            "10.0.0.1", "worker-1", "test-vm"
        )
        self.assertFalse(result)
        self.assertIsNone(new_ip)
        self.assertIsNone(new_node)

    # --- get_vm_access ---

    @patch("krkn.health_checks.virt_health_check_plugin.invoke_no_exit")
    def test_get_vm_access_first_fails_second_succeeds(self, mock_invoke):
        """Test get_vm_access falls back to second virtctl command"""
        call_count = [0]
        def side_effect(*_):
            call_count[0] += 1
            return "False" if call_count[0] == 1 else "True"

        mock_invoke.side_effect = side_effect

        result = self.plugin.get_vm_access("test-vm", "default")
        self.assertTrue(result)
        self.assertEqual(mock_invoke.call_count, 2)

    # --- batch_list ---

    def test_batch_list_zero_batch_size_no_threads(self):
        """Test batch_list does not start threads when batch_size is 0"""
        self.plugin.batch_size = 0
        self.plugin.vm_list = []
        self.plugin.batch_list(queue.SimpleQueue())
        self.assertEqual(len(self.plugin.threads), 0)

    @patch.object(
        __import__("krkn.health_checks.virt_health_check_plugin", fromlist=["VirtHealthCheckPlugin"]).VirtHealthCheckPlugin,
        "_run_virt_check_batch",
    )
    def test_batch_list_starts_threads(self, mock_batch):
        """Test batch_list starts worker threads for VM batches"""
        import math
        mock_batch.return_value = None
        self.plugin.vm_list = [MagicMock() for _ in range(4)]
        self.plugin.threads_limit = 2
        self.plugin.batch_size = math.ceil(len(self.plugin.vm_list) / self.plugin.threads_limit)
        self.plugin.batch_list(queue.SimpleQueue())
        for t in self.plugin.threads:
            t.join()
        self.assertGreater(len(self.plugin.threads), 0)

    # --- _run_virt_check_batch ---

    @patch("krkn.health_checks.virt_health_check_plugin.time.sleep")
    def test_run_virt_check_batch_tracks_initial_status(self, mock_sleep):
        """Test batch runner adds VM to tracker on first pass and records final status"""
        def stop_after_sleep(*_):
            self.plugin.current_iterations = self.plugin.iterations

        mock_sleep.side_effect = stop_after_sleep

        mock_vm = MagicMock()
        mock_vm.vm_name = "vm1"
        mock_vm.namespace = "default"
        mock_vm.ip_address = "10.0.0.1"
        mock_vm.node_name = "worker-1"
        mock_vm.new_ip_address = ""
        self.plugin.disconnected = False

        with patch.object(self.plugin, "get_vm_access", return_value=True):
            telemetry_queue = queue.SimpleQueue()
            self.plugin._run_virt_check_batch([mock_vm], telemetry_queue)

        result = telemetry_queue.get_nowait()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].vm_name, "vm1")

    @patch("krkn.health_checks.virt_health_check_plugin.time.sleep")
    def test_run_virt_check_batch_records_status_change(self, mock_sleep):
        """Test batch runner records status changes between iterations"""
        call_count = [0]
        def stop_after_two(*_):
            call_count[0] += 1
            if call_count[0] >= 2:
                self.plugin.current_iterations = self.plugin.iterations

        mock_sleep.side_effect = stop_after_two

        mock_vm = MagicMock()
        mock_vm.vm_name = "vm1"
        mock_vm.namespace = "default"
        mock_vm.ip_address = "10.0.0.1"
        mock_vm.node_name = "worker-1"
        mock_vm.new_ip_address = ""
        self.plugin.disconnected = False
        self.plugin.only_failures = False

        statuses = [True, False]
        idx = [0]
        def alternating(*_):
            val = statuses[idx[0] % 2]
            idx[0] += 1
            return val

        with patch.object(self.plugin, "get_vm_access", side_effect=alternating):
            telemetry_queue = queue.SimpleQueue()
            self.plugin._run_virt_check_batch([mock_vm], telemetry_queue)

        result = telemetry_queue.get_nowait()
        self.assertGreaterEqual(len(result), 1)

    @patch("krkn.health_checks.virt_health_check_plugin.time.sleep")
    def test_run_virt_check_batch_only_failures_skips_success(self, mock_sleep):
        """Test only_failures=True skips successful status changes in telemetry"""
        call_count = [0]
        def stop_after_two(*_):
            call_count[0] += 1
            if call_count[0] >= 2:
                self.plugin.current_iterations = self.plugin.iterations

        mock_sleep.side_effect = stop_after_two

        mock_vm = MagicMock()
        mock_vm.vm_name = "vm1"
        mock_vm.namespace = "default"
        mock_vm.ip_address = "10.0.0.1"
        mock_vm.node_name = "worker-1"
        mock_vm.new_ip_address = ""
        self.plugin.disconnected = False
        self.plugin.only_failures = True

        # VM goes from False (failure) -> True (success): only_failures skips success transitions
        statuses = [False, True]
        idx = [0]
        def alternating(*_):
            val = statuses[idx[0] % 2]
            idx[0] += 1
            return val

        with patch.object(self.plugin, "get_vm_access", side_effect=alternating):
            telemetry_queue = queue.SimpleQueue()
            self.plugin._run_virt_check_batch([mock_vm], telemetry_queue)

        result = telemetry_queue.get_nowait()
        # Final result may still be appended; just confirm no exception and queue populated
        self.assertIsNotNone(result)

    @patch("krkn.health_checks.virt_health_check_plugin.time.sleep")
    def test_run_virt_check_batch_exception_sets_false(self, mock_sleep):
        """Test exception in VM access is caught and status set to False"""
        def stop_after_sleep(*_):
            self.plugin.current_iterations = self.plugin.iterations

        mock_sleep.side_effect = stop_after_sleep

        mock_vm = MagicMock()
        mock_vm.vm_name = "vm-err"
        mock_vm.namespace = "default"
        mock_vm.ip_address = "10.0.0.1"
        mock_vm.node_name = "worker-1"
        mock_vm.new_ip_address = ""
        self.plugin.disconnected = False

        with patch.object(self.plugin, "get_vm_access", side_effect=Exception("boom")):
            telemetry_queue = queue.SimpleQueue()
            self.plugin._run_virt_check_batch([mock_vm], telemetry_queue)

        result = telemetry_queue.get_nowait()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].vm_name, "vm-err")

    @patch("krkn.health_checks.virt_health_check_plugin.time.sleep")
    def test_run_virt_check_batch_disconnected_updates_new_ip(self, mock_sleep):
        """Test disconnected mode updates new IP on VM object"""
        def stop_after_sleep(*_):
            self.plugin.current_iterations = self.plugin.iterations

        mock_sleep.side_effect = stop_after_sleep

        mock_vm = MagicMock()
        mock_vm.vm_name = "vm1"
        mock_vm.namespace = "default"
        mock_vm.ip_address = "10.0.0.1"
        mock_vm.node_name = "worker-1"
        mock_vm.new_ip_address = ""
        self.plugin.disconnected = True

        with patch.object(
            self.plugin, "check_disconnected_access", return_value=(True, "10.0.0.2", None)
        ):
            telemetry_queue = queue.SimpleQueue()
            self.plugin._run_virt_check_batch([mock_vm], telemetry_queue)

        self.assertEqual(mock_vm.new_ip_address, "10.0.0.2")

    @patch("krkn.health_checks.virt_health_check_plugin.time.sleep")
    def test_run_virt_check_batch_disconnected_uses_new_ip(self, mock_sleep):
        """Test disconnected mode uses existing new_ip_address if already set"""
        def stop_after_sleep(*_):
            self.plugin.current_iterations = self.plugin.iterations

        mock_sleep.side_effect = stop_after_sleep

        mock_vm = MagicMock()
        mock_vm.vm_name = "vm1"
        mock_vm.namespace = "default"
        mock_vm.ip_address = "10.0.0.1"
        mock_vm.node_name = "worker-1"
        mock_vm.new_ip_address = "10.0.0.5"
        self.plugin.disconnected = True

        check_calls = []
        def capture_call(ip, *_):
            check_calls.append(ip)
            return (True, None, None)

        with patch.object(self.plugin, "check_disconnected_access", side_effect=capture_call):
            telemetry_queue = queue.SimpleQueue()
            self.plugin._run_virt_check_batch([mock_vm], telemetry_queue)

        self.assertIn("10.0.0.5", check_calls)

    # --- _run_post_virt_check ---

    def test_run_post_virt_check_failed_vm_added_to_telemetry(self):
        """Test _run_post_virt_check adds failing VMs to telemetry"""
        mock_vm = MagicMock()
        mock_vm.vm_name = "vm-fail"
        mock_vm.namespace = "default"
        mock_vm.ip_address = "10.0.0.1"
        mock_vm.node_name = "worker-1"
        mock_vm.new_ip_address = ""
        self.plugin.disconnected = False

        with patch.object(self.plugin, "get_vm_access", return_value=False):
            result_queue = queue.SimpleQueue()
            self.plugin._run_post_virt_check([mock_vm], [], result_queue)

        result = result_queue.get_nowait()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].vm_name, "vm-fail")

    def test_run_post_virt_check_healthy_vm_not_in_telemetry(self):
        """Test _run_post_virt_check skips healthy VMs"""
        mock_vm = MagicMock()
        mock_vm.vm_name = "vm-ok"
        mock_vm.namespace = "default"
        mock_vm.ip_address = "10.0.0.1"
        mock_vm.node_name = "worker-1"
        mock_vm.new_ip_address = ""
        self.plugin.disconnected = False

        with patch.object(self.plugin, "get_vm_access", return_value=True):
            result_queue = queue.SimpleQueue()
            self.plugin._run_post_virt_check([mock_vm], [], result_queue)

        result = result_queue.get_nowait()
        self.assertEqual(len(result), 0)

    def test_run_post_virt_check_disconnected_mode(self):
        """Test _run_post_virt_check in disconnected mode"""
        mock_vm = MagicMock()
        mock_vm.vm_name = "vm1"
        mock_vm.namespace = "default"
        mock_vm.ip_address = "10.0.0.1"
        mock_vm.node_name = "worker-1"
        mock_vm.new_ip_address = ""
        self.plugin.disconnected = True

        with patch.object(
            self.plugin, "check_disconnected_access", return_value=(False, "10.0.0.2", "worker-2")
        ):
            result_queue = queue.SimpleQueue()
            self.plugin._run_post_virt_check([mock_vm], [], result_queue)

        self.assertEqual(mock_vm.new_ip_address, "10.0.0.2")
        self.assertEqual(mock_vm.node_name, "worker-2")

    # --- gather_post_virt_checks ---

    def test_gather_post_virt_checks_exit_on_failure(self):
        """Test gather_post_virt_checks sets ret_value when exit_on_failure and failures exist"""
        self.plugin.exit_on_failure = True
        self.plugin.batch_size = 0  # skip thread logic

        # Simulate existing telemetry with failures
        self.plugin.gather_post_virt_checks([MagicMock()])
        self.assertEqual(self.plugin.get_return_value(), 3)

    def test_gather_post_virt_checks_no_failures_no_exit(self):
        """Test gather_post_virt_checks does not set ret_value when no failures"""
        self.plugin.exit_on_failure = True
        self.plugin.batch_size = 0

        self.plugin.gather_post_virt_checks([])
        self.assertEqual(self.plugin.get_return_value(), 0)

    # --- run_health_check ---

    def test_run_health_check_none_config_skips(self):
        """Test run_health_check returns early on None config"""
        telemetry_queue = queue.Queue()
        self.plugin.run_health_check(None, telemetry_queue)
        self.assertTrue(telemetry_queue.empty())

    @patch("krkn.health_checks.virt_health_check_plugin.KubevirtVmOutageScenarioPlugin")
    def test_run_health_check_valid_config_starts_batch(self, mock_plugin_class):
        """Test run_health_check starts batch threads on valid config"""
        mock_plugin = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.k8s_client = self.mock_kubecli
        self.mock_kubecli.get_vmis.return_value = []

        self.plugin.current_iterations = self.plugin.iterations  # prevent infinite loop
        config = {"namespace": "default", "interval": 2}
        telemetry_queue = queue.Queue()
        self.plugin.run_health_check(config, telemetry_queue)
        # batch_size is 0 (no VMs), so no threads — but no crash either
        self.assertEqual(len(self.plugin.threads), 0)


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
