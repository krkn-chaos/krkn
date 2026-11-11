#!/usr/bin/env python3

"""
Test suite for VMI Outage Scenario Plugin

This comprehensive test suite covers the VmiOutageScenarioPlugin class
using extensive mocks to avoid needing actual Kubernetes/KubeVirt infrastructure.

Test Coverage:
- Core scenario flows: injection, recovery, deletion, waiting
- Edge cases: timeouts, missing parameters, validation failures
- API exceptions: 404, 500, and general exceptions
- Helper methods: get_vmi, get_vmis, patch_vm_spec, validate_environment
- Multiple VMI scenarios with kill_count
- Auto-restart disable functionality

IMPORTANT: These tests use comprehensive mocking and do NOT require any Kubernetes
cluster or KubeVirt installation. All API calls are mocked.

Usage:
    # Run all tests
    python -m unittest tests.test_vmi_outage -v

    # Run with coverage
    python -m coverage run -a -m unittest tests/test_vmi_outage.py -v

Assisted By: Claude Code
"""

import copy
import itertools
import os
import sys
import tempfile
import datetime
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# Ensure we import the real plugin, not a mock from test_logging_and_code_quality.py
# Remove any mocked versions from sys.modules before importing
_modules_to_clear = [
    "krkn.scenario_plugins.vmi_outage.vmi_outage_scenario_plugin",
    "krkn.scenario_plugins.vmi_outage",
]
for mod in _modules_to_clear:
    if mod in sys.modules:
        # Check if it's a mock by seeing if it's a types.ModuleType with minimal attributes
        module = sys.modules[mod]
        # If the module has VmiOutageScenarioPlugin and it's a MagicMock, remove it
        if hasattr(module, 'VmiOutageScenarioPlugin'):
            cls = getattr(module, 'VmiOutageScenarioPlugin')
            if type(cls).__name__ == 'MagicMock' or 'Mock' in type(cls).__name__:
                del sys.modules[mod]

import yaml
# Import krkn_lib items - these might be mocked but we'll handle that in setUp
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedVMI, VmisStatus
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from kubernetes.client.rest import ApiException

from krkn.scenario_plugins.vmi_outage.vmi_outage_scenario_plugin import VmiOutageScenarioPlugin


class TestVmiOutageScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for VmiOutageScenarioPlugin
        """
        self.plugin = VmiOutageScenarioPlugin()

        # Create mock k8s client (spec=KrknKubernetes if it's a real class, otherwise no spec)
        # This handles the case where test_logging_and_code_quality.py has already mocked KrknKubernetes
        try:
            self.k8s_client = MagicMock(spec=KrknKubernetes)
        except Exception:
            # If KrknKubernetes is already a mock, just create a plain MagicMock
            self.k8s_client = MagicMock()
        self.custom_object_client = MagicMock()
        self.k8s_client.custom_object_client = self.custom_object_client
        self.plugin.k8s_client = self.k8s_client
        self.plugin.custom_object_client = self.custom_object_client

        # Mock krkn-lib VM/VMI methods
        self.k8s_client.get_vm = MagicMock()
        self.k8s_client.get_vmi = MagicMock()
        self.k8s_client.get_vmis = MagicMock()
        self.k8s_client.get_vms = MagicMock()
        self.k8s_client.delete_vmi = MagicMock()
        self.k8s_client.create_vmi = MagicMock()
        self.k8s_client.patch_vm = MagicMock()
        
        # Mock VMI data
        self.mock_vmi = {
            "metadata": {
                "name": "test-vm",
                "namespace": "default",
                "creationTimestamp": "2023-01-01T00:00:00Z"
            },
            "status": {
                "phase": "Running"
            }
        }
        base_time = datetime.now()
        # Mock VMI with new creation timestamp (after recreation)
        self.mock_vmi_recreated = {
            "metadata": {
                "name": "test-vm",
                "namespace": "default",
                "creationTimestamp": (base_time + timedelta(minutes=1)).isoformat() + "Z"
            },
            "status": {
                "phase": "Running"
            }
        }

        # Create test config
        self.config = {
            "scenarios": [
                {
                    "name": "vmi outage test",
                    "scenario": "vmi_outage",
                    "parameters": {
                        "vm_name": "test-vm",
                        "namespace": "default",
                        "duration": 0
                    }
                }
            ]
        }

        # Create a temporary config file
        temp_dir = tempfile.gettempdir()
        self.scenario_file = os.path.join(temp_dir, "test_vmi_scenario.yaml")
        with open(self.scenario_file, "w") as f:
            yaml.dump(self.config, f)

        # Mock dependencies
        self.telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        self.scenario_telemetry = MagicMock(spec=ScenarioTelemetry)
        self.telemetry.get_lib_kubernetes.return_value = self.k8s_client

        # Initialize counters for reusable mock functions
        self.delete_count = 0
        self.wait_count = 0

    def create_incrementing_time_function(self):
        """
        Create an incrementing time function that returns sequential float values.
        Returns a callable that can be used with patch('time.time', side_effect=...)
        """
        counter = itertools.count(1)
        def mock_time():
            return float(next(counter))
        return mock_time

    def mock_delete(self, *args, **kwargs):
        """Reusable mock for delete_vmi that tracks calls and sets up affected_pod"""
        self.delete_count += 1
        self.plugin.affected_vmi = AffectedVMI(vmi_name=f"test-vm-{self.delete_count}", namespace="default")
        self.plugin.affected_vmi.vmi_rescheduling_time = 5.0
        return 0

    def mock_wait(self, *args, **kwargs):
        """Reusable mock for wait_for_running that tracks calls and sets vmi_readiness_time"""
        self.wait_count += 1
        self.plugin.affected_vmi.vmi_readiness_time = 3.0
        return 0

    # ==================== Core Scenario Tests ====================

    def test_successful_injection_and_recovery(self):
        """
        Test successful deletion and recovery of a VMI using detailed mocking
        """
        # Setup k8s_client mocks for krkn-lib methods
        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm"}}]

        # Mock VMI with new timestamp after deletion (successful recreation)
        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi['metadata']['creationTimestamp'] = '2023-01-01T00:05:00Z'

        # Sequence of calls to get_vmi:
        # 1. validate_environment checks if VMI exists
        # 2. execute_scenario gets VMI details
        # 3. delete_vmi loop checks for recreation
        # 4. wait_for_running checks if VMI is running
        self.k8s_client.get_vmi.side_effect = [
            self.mock_vmi,  # validate_environment
            self.mock_vmi,  # execute_scenario
            new_vmi,        # delete_vmi - recreated with new timestamp
            new_vmi         # wait_for_running - confirm it's running
        ]

        self.k8s_client.delete_vmi.return_value = None

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 0)
        self.k8s_client.delete_vmi.assert_called_once_with("test-vm", "default")

    def test_no_matching_vmis_fails_scenario(self):
        """A target selection with no matching VMIs must fail the scenario."""
        self.k8s_client.get_vmis.return_value = []

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run(
                "test-uuid", self.scenario_file, self.telemetry, self.scenario_telemetry
            )

        self.assertEqual(result, 1)
        self.assertIn("No VMIs found", self.scenario_telemetry.affected_vmis.error)
        self.k8s_client.get_vmis.assert_called_once_with(
            "test-vm", "default", label_selector=None
        )
        
    def test_injection_failure(self):
        """
        Test failure during VMI deletion
        """
        # Setup k8s_client mocks
        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm"}}]

        # VMI exists before and after deletion (stays same timestamp - timeout)
        self.k8s_client.get_vmi.return_value = self.mock_vmi

        # Make delete_vmi raise an exception to simulate failure
        self.k8s_client.delete_vmi.side_effect = ApiException(status=500)

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 1)
        self.k8s_client.delete_vmi.assert_called_once_with("test-vm", "default")
        self.assertEqual(len(self.scenario_telemetry.affected_vmis.unrecovered), 1)
        
    def test_disable_auto_restart(self):
        """
        Test VM auto-restart can be disabled
        """
        # Configure test with disable_auto_restart=True
        self.config["scenarios"][0]["parameters"]["disable_auto_restart"] = True

        # Setup k8s_client mocks
        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm"}}]

        # Mock VM to be patched
        mock_vm = {
            "metadata": {"name": "test-vm", "namespace": "default"},
            "spec": {"running": True}
        }
        self.k8s_client.get_vm.return_value = mock_vm
        self.k8s_client.patch_vm.return_value = mock_vm

        # Mock VMI with new timestamp after deletion
        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi['metadata']['creationTimestamp'] = '2023-01-01T00:05:00Z'

        self.k8s_client.get_vmi.side_effect = [
            self.mock_vmi,  # validate_environment
            self.mock_vmi,  # execute_scenario
            new_vmi,        # delete_vmi - recreated
            new_vmi         # wait_for_running
        ]

        self.k8s_client.delete_vmi.return_value = None

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 0)
        # Verify patch_vm was called to disable auto-restart
        self.k8s_client.patch_vm.assert_called_once()
        self.k8s_client.delete_vmi.assert_called_once_with("test-vm", "default")
        
    def test_recovery_when_vmi_does_not_exist(self):
        """
        Test recovery logic when VMI does not exist after deletion
        """
        # Store the original VMI in the plugin for recovery
        self.plugin.original_vmi = copy.deepcopy(self.mock_vmi)

        # Set up running VMI data for after recovery
        running_vmi = copy.deepcopy(self.mock_vmi)
        running_vmi['status']['phase'] = 'Running'

        # Mock get_vmi to return None (not auto-recovered), then running after create
        self.k8s_client.get_vmi.side_effect = [None, running_vmi]

        # Mock create_vmi to return success
        self.k8s_client.create_vmi.return_value = running_vmi

        # Run recovery with mocked time.sleep and time.time
        with patch('time.sleep'):
            # Use itertools.count() to avoid StopIteration on time.time() calls
            with patch('time.time', side_effect=(x for x in itertools.count(0))):
                result = self.plugin.recover("test-vm", "default", False)

        self.assertEqual(result, 0)
        # Verify create_vmi was called
        self.k8s_client.create_vmi.assert_called_once()
    
    def test_validation_failure(self):
        """
        Test validation failure when KubeVirt is not installed
        """
        # Setup k8s_client mocks
        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        # Return empty list to simulate KubeVirt CRDs not found
        self.k8s_client.get_vms.return_value = []
        self.k8s_client.get_vmi.return_value = None

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, self.telemetry, self.scenario_telemetry)

        # When validation fails, run() returns 1 due to exception handling
        self.assertEqual(result, 1)

    # ==================== Timeout Tests ====================

    def test_delete_vmi_timeout(self):
        """
        Test timeout during VMI deletion
        """
        # Initialize original_vmi which is required by delete_vmi
        self.plugin.original_vmi = copy.deepcopy(self.mock_vmi)

        # Initialize pods_status which delete_vmi needs
        self.plugin.vmis_status = VmisStatus()
        self.plugin.affected_vmi = AffectedVMI(vmi_name="test-vm", namespace="default")
        self.plugin.vmis_status = VmisStatus()

        # Mock successful delete operation
        self.k8s_client.delete_vmi.return_value = None

        # Mock that get_vmi always returns VMI with same creationTimestamp (never gets recreated)
        self.k8s_client.get_vmi.return_value = self.mock_vmi

        # Simulate timeout by using itertools.count() - increment by 10 to eventually trigger timeout
        with patch('time.sleep'), patch('time.time', side_effect=(x * 10 for x in itertools.count(0))):
            result = self.plugin.delete_vmi("test-vm", "default", False)

        self.assertEqual(result, 1)
        self.k8s_client.delete_vmi.assert_called_once_with("test-vm", "default")
        self.assertEqual(len(self.plugin.vmis_status.unrecovered), 0)

    def test_patch_vm_spec_success(self):
        """
        Test patch_vm_spec successfully patches VM
        """
        mock_vm = {
            "metadata": {"name": "test-vm", "namespace": "default"},
            "spec": {"running": True}
        }

        self.k8s_client.get_vm.return_value = mock_vm
        self.k8s_client.patch_vm.return_value = mock_vm

        result = self.plugin.patch_vm_spec("test-vm", "default", False)

        self.assertTrue(result)
        self.k8s_client.patch_vm.assert_called_once()

    def test_patch_vm_spec_api_exception(self):
        """
        Test patch_vm_spec handles ApiException
        """
        api_error = ApiException(status=404, reason="Not Found")
        self.k8s_client.get_vm.side_effect = api_error

        result = self.plugin.patch_vm_spec("test-vm", "default", False)

        self.assertFalse(result)

    def test_patch_vm_spec_general_exception(self):
        """
        Test patch_vm_spec handles general exceptions
        """
        self.k8s_client.get_vm.side_effect = Exception("Connection error")

        result = self.plugin.patch_vm_spec("test-vm", "default", False)

        self.assertFalse(result)

    def test_delete_vmi_successful_recreation(self):
        """
        Test delete_vmi succeeds when VMI is recreated with new creationTimestamp
        """
        # Initialize required attributes - use deepcopy to avoid shared references
        self.plugin.original_vmi = copy.deepcopy(self.mock_vmi)
        self.plugin.vmis_status = VmisStatus()
        self.plugin.affected_vmi = AffectedVMI(vmi_name="test-vm", namespace="default")

        self.k8s_client.delete_vmi.return_value = None

        # Mock get_vmi to return VMI with new creationTimestamp - use deepcopy
        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi['metadata']['creationTimestamp'] = '2023-01-01T00:05:00Z'

        # Use itertools to create an infinite iterator for time values
        time_iter = itertools.count(0, 0.001)

        self.k8s_client.get_vmi.return_value = new_vmi

        with patch('time.sleep'):
            with patch('time.time', side_effect=lambda: next(time_iter)):
                result = self.plugin.delete_vmi("test-vm", "default", False)

        self.assertEqual(result, 0)
        self.assertIsNotNone(self.plugin.affected_vmi.vmi_rescheduling_time)

    def test_delete_vmi_with_disable_auto_restart_failure(self):
        """
        Test delete_vmi continues when patch_vm_spec fails and VMI stays deleted
        """
        # Initialize required attributes
        self.plugin.original_vmi = copy.deepcopy(self.mock_vmi)
        self.plugin.vmis_status = VmisStatus()
        self.plugin.affected_vmi = AffectedVMI(vmi_name="test-vm", namespace="default")

        # Mock patch_vm_spec to fail
        with patch.object(self.plugin, 'patch_vm_spec', return_value=False):
            self.k8s_client.delete_vmi.return_value = None

            # Mock VMI deleted (returns None) - it will timeout waiting for recreation
            self.k8s_client.get_vmi.return_value = None

            with patch('time.sleep'):
                # Use itertools to create infinite time sequence
                # Use 1.0 increment to quickly reach timeout (120 seconds)
                time_iter = itertools.count(0, 1.0)
                with patch('time.time', side_effect=lambda: next(time_iter)):
                    result = self.plugin.delete_vmi("test-vm", "default", True)

        # When VMI stays deleted (None), delete_vmi waits for recreation and times out
        self.assertEqual(result, 1)

    def test_wait_for_running_timeout(self):
        """
        Test wait_for_running times out when VMI doesn't reach Running state
        """
        self.plugin.affected_vmi = AffectedVMI(vmi_name="test-vm", namespace="default")

        # Mock VMI in Pending state
        pending_vmi = copy.deepcopy(self.mock_vmi)
        pending_vmi['status']['phase'] = 'Pending'

        self.k8s_client.get_vmi.return_value = pending_vmi

        with patch('time.sleep'):
            # Use itertools.count() to avoid StopIteration - increment by 10 to simulate timeout
            with patch('time.time', side_effect=(x * 10 for x in itertools.count(0))):
                result = self.plugin.wait_for_running("test-vm", "default", 120)

        self.assertEqual(result, 1)

    def test_wait_for_running_vmi_not_exists(self):
        """
        Test wait_for_running when VMI doesn't exist yet
        """
        self.plugin.affected_vmi = AffectedVMI(vmi_name="test-vm", namespace="default")

        # First return None (not exists), then return running VMI
        running_vmi = copy.deepcopy(self.mock_vmi)
        running_vmi['status']['phase'] = 'Running'

        self.k8s_client.get_vmi.side_effect = [None, None, running_vmi]

        with patch('time.sleep'):
            # Use itertools.count() to avoid StopIteration on time.time() calls
            # time.time() called for: start_time, while loop checks, end_time, and potentially logging
            with patch('time.time', side_effect=(x for x in itertools.count(0))):
                result = self.plugin.wait_for_running("test-vm", "default", 120)

        self.assertEqual(result, 0)
        self.assertIsNotNone(self.plugin.affected_vmi.vmi_readiness_time)

    # ==================== Recovery Tests ====================

    def test_recover_no_original_vmi(self):
        """
        Test recover fails when no original VMI is captured
        """
        self.plugin.original_vmi = None

        result = self.plugin.recover("test-vm", "default", False)

        self.assertEqual(result, 1)

    def test_recover_exception_during_creation(self):
        """
        Test recover handles exception during VMI creation
        """
        self.plugin.original_vmi = copy.deepcopy(self.mock_vmi)

        self.k8s_client.create_vmi.side_effect = Exception("Creation failed")
        self.k8s_client.get_vmi.return_value = None

        with patch('time.sleep'):
            # Use itertools.count() to avoid StopIteration on time.time() calls
            with patch('time.time', side_effect=(x for x in itertools.count(0))):
                result = self.plugin.recover("test-vm", "default", False)

        self.assertEqual(result, 1)

    # ==================== Execute Scenario Tests ====================

    def test_execute_scenario_missing_vm_name(self):
        """
        Test execute_scenario fails when vm_name is missing
        """
        config = {
            "parameters": {
                "namespace": "default"
            }
        }

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        # Should return empty PodsStatus when vm_name is missing
        self.assertIsInstance(result, VmisStatus)
        self.assertEqual(len(result.recovered), 0)
        self.assertEqual(len(result.unrecovered), 0)

    def test_execute_scenario_vmi_not_found(self):
        """
        Test execute_scenario when VMI is not found after get_vmi
        """
        config = {
            "parameters": {
                "vm_name": "test-vm",
                "namespace": "default"
            }
        }

        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm"}}]
        # First get_vmi returns VMI for validation, second returns None in execute_scenario
        self.k8s_client.get_vmi.side_effect = [self.mock_vmi, None]

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        # Should be PodsStatus with unrecovered pod when VMI not found
        self.assertIsInstance(result, VmisStatus)
        self.assertEqual(len(result.unrecovered), 1)

    def test_execute_scenario_with_kill_count(self):
        """
        Test execute_scenario with kill_count > 1
        """
        # Create multiple VMIs
        vmi_1 = copy.deepcopy(self.mock_vmi)
        vmi_1["metadata"]["name"] = "test-vm-1"
        vmi_2 = copy.deepcopy(self.mock_vmi)
        vmi_2["metadata"]["name"] = "test-vm-2"

        config = {
            "parameters": {
                "vm_name": "test-vm",
                "namespace": "default",
                "kill_count": 2
            }
        }

        # Setup k8s_client mocks
        self.k8s_client.get_vmis.return_value = [vmi_1, vmi_2]
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm-1"}}, {"metadata": {"name": "test-vm-2"}}]

        # Mock VMIs with new timestamps after deletion
        new_vmi_1 = copy.deepcopy(vmi_1)
        new_vmi_1['metadata']['creationTimestamp'] = '2023-01-01T00:05:00Z'
        new_vmi_2 = copy.deepcopy(vmi_2)
        new_vmi_2['metadata']['creationTimestamp'] = '2023-01-01T00:05:00Z'

        # Sequence of get_vmi calls for 2 kills
        self.k8s_client.get_vmi.side_effect = [
            vmi_1,      # validate first
            vmi_1,      # execute_scenario first
            new_vmi_1,  # delete_vmi recreated first
            new_vmi_1,  # wait_for_running first
            vmi_2,      # validate second
            vmi_2,      # execute_scenario second
            new_vmi_2,  # delete_vmi recreated second
            new_vmi_2   # wait_for_running second
        ]

        self.k8s_client.delete_vmi.return_value = None

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        # Should call delete_vmi twice
        self.assertEqual(self.k8s_client.delete_vmi.call_count, 2)

    def test_execute_scenario_wait_for_running_failure(self):
        """
        Test execute_scenario when wait_for_running fails
        """
        config = {
            "parameters": {
                "vm_name": "test-vm",
                "namespace": "default"
            }
        }

        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm"}}]

        # Mock VMI with new timestamp after deletion
        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi['metadata']['creationTimestamp'] = '2023-01-01T00:05:00Z'

        # Mock VMI in pending state for wait_for_running timeout
        pending_vmi = copy.deepcopy(new_vmi)
        pending_vmi['status']['phase'] = 'Pending'

        # Need many pending_vmi returns for wait_for_running loop to timeout
        vmi_sequence = [
            self.mock_vmi,  # validate
            self.mock_vmi,  # execute_scenario
            new_vmi,        # delete_vmi - recreated
        ] + [pending_vmi] * 130  # wait_for_running - stays pending (will timeout after 120 iterations)

        self.k8s_client.get_vmi.side_effect = vmi_sequence

        self.k8s_client.delete_vmi.return_value = None

        with patch('time.sleep'):
            # Need more time.time() calls for delete_vmi loop and wait_for_running timeout
            time_values = [0, 1] + [i for i in range(2, 140)]  # Enough values to exceed timeout
            with patch('time.time', side_effect=time_values):
                result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        # Should have unrecovered pod
        self.assertEqual(len(result.unrecovered), 1)

    def test_validate_environment_exception(self):
        """
        Test validate_environment handles exceptions
        """
        self.k8s_client.get_vms.side_effect = Exception("Connection error")

        result = self.plugin.validate_environment("test-vm", "default")

        self.assertFalse(result)

    def test_validate_environment_vmi_not_found(self):
        """
        Test validate_environment when VMI doesn't exist
        """
        # Mock CRDs exist but VMI not found
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm"}}]
        self.k8s_client.get_vmi.return_value = None

        result = self.plugin.validate_environment("test-vm", "default")

        self.assertFalse(result)

    def test_init_clients(self):
        """
        Test init_clients initializes k8s client correctly
        """
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_custom_client = MagicMock()
        mock_k8s.custom_object_client = mock_custom_client

        self.plugin.init_clients(mock_k8s)

        self.assertEqual(self.plugin.k8s_client, mock_k8s)
        self.assertEqual(self.plugin.custom_object_client, mock_custom_client)

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        # Should support both new name and legacy name for backwards compatibility
        self.assertIn("vmi_outage", result)
        self.assertIn("kubevirt_vm_outage", result)
        self.assertEqual(len(result), 2)

    # ==================== label_selector Tests ====================

    def test_execute_scenario_missing_both_vm_name_and_label_selector(self):
        """
        Test execute_scenario returns empty status when neither vm_name nor label_selector is set
        """
        config = {"parameters": {"namespace": "default"}}

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        self.assertIsInstance(result, VmisStatus)
        self.assertEqual(len(result.recovered), 0)
        self.assertEqual(len(result.unrecovered), 0)
        self.k8s_client.get_vmis.assert_not_called()

    def test_execute_scenario_with_label_selector_only(self):
        """
        Test execute_scenario succeeds using label_selector without vm_name
        """
        config = {
            "parameters": {
                "label_selector": "app=test-vm",
                "namespace": "default",
            }
        }

        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm"}}]

        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi["metadata"]["creationTimestamp"] = "2023-01-01T00:05:00Z"

        self.k8s_client.get_vmi.side_effect = [
            self.mock_vmi,  # validate_environment
            self.mock_vmi,  # execute_scenario
            new_vmi,        # delete_vmi - recreated
            new_vmi,        # wait_for_running
        ]
        self.k8s_client.delete_vmi.return_value = None

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        self.assertIsInstance(result, VmisStatus)
        self.assertEqual(len(result.recovered), 1)
        self.k8s_client.get_vmis.assert_called_once_with(
            ".*", "default", label_selector="app=test-vm"
        )

    def test_execute_scenario_with_both_vm_name_and_label_selector(self):
        """
        Test execute_scenario passes both vm_name and label_selector to get_vmis
        """
        config = {
            "parameters": {
                "vm_name": "test-vm",
                "label_selector": "app=test-vm",
                "namespace": "default",
            }
        }

        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm"}}]

        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi["metadata"]["creationTimestamp"] = "2023-01-01T00:05:00Z"

        self.k8s_client.get_vmi.side_effect = [
            self.mock_vmi,
            self.mock_vmi,
            new_vmi,
            new_vmi,
        ]
        self.k8s_client.delete_vmi.return_value = None

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        self.assertIsInstance(result, VmisStatus)
        self.assertEqual(len(result.recovered), 1)
        self.k8s_client.get_vmis.assert_called_once_with(
            "test-vm", "default", label_selector="app=test-vm"
        )

    def test_execute_scenario_empty_vmis_list_returns_early(self):
        """
        Test execute_scenario returns empty status without crashing when no VMIs match
        """
        config = {
            "parameters": {
                "vm_name": "nonexistent-vm",
                "namespace": "default",
            }
        }
        self.k8s_client.get_vmis.return_value = []

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        self.assertIsInstance(result, VmisStatus)
        self.assertEqual(len(result.recovered), 0)
        self.assertEqual(len(result.unrecovered), 0)
        self.k8s_client.delete_vmi.assert_not_called()

    def test_execute_scenario_empty_label_selector_treated_as_none(self):
        """
        Test that an empty string label_selector is treated the same as not set,
        so vm_name is still required
        """
        config = {
            "parameters": {
                "label_selector": "",
                "namespace": "default",
            }
        }

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        self.assertIsInstance(result, VmisStatus)
        self.assertEqual(len(result.recovered), 0)
        self.assertEqual(len(result.unrecovered), 0)
        self.k8s_client.get_vmis.assert_not_called()

    def test_legacy_scenario_name_backwards_compatibility(self):
        """
        Test that legacy scenario name 'kubevirt_vm_outage' still works
        """
        # Create test config with legacy scenario name
        legacy_config = {
            "scenarios": [
                {
                    "name": "legacy test",
                    "scenario": "kubevirt_vm_outage",  # Old name
                    "parameters": {
                        "vm_name": "test-vm",
                        "namespace": "default",
                        "duration": 0
                    }
                }
            ]
        }

        # Create a temporary config file with legacy name
        temp_dir = tempfile.gettempdir()
        legacy_scenario_file = os.path.join(temp_dir, "test_legacy_scenario.yaml")
        with open(legacy_scenario_file, "w") as f:
            yaml.dump(legacy_config, f)

        # Setup k8s_client mocks
        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm"}}]

        # Mock VMI with new timestamp after deletion
        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi['metadata']['creationTimestamp'] = '2023-01-01T00:05:00Z'

        self.k8s_client.get_vmi.side_effect = [
            self.mock_vmi,  # validate_environment
            self.mock_vmi,  # execute_scenario
            new_vmi,        # delete_vmi - recreated
            new_vmi         # wait_for_running
        ]

        self.k8s_client.delete_vmi.return_value = None

        # Run with legacy scenario name - should still work
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(legacy_config))):
            result = self.plugin.run("test-uuid", legacy_scenario_file, self.telemetry, self.scenario_telemetry)

        # Should succeed with legacy name
        self.assertEqual(result, 0)
        self.k8s_client.delete_vmi.assert_called_once_with("test-vm", "default")


    # ==================== Guest reachability MTTR ====================

    def test_get_vmi_ip_from_interfaces(self):
        vmi = {
            "status": {
                "interfaces": [
                    {"name": "eth0", "ipAddress": "10.0.0.5"},
                ]
            }
        }
        self.assertEqual(VmiOutageScenarioPlugin.get_vmi_ip(vmi), "10.0.0.5")

    def test_get_vmi_ip_from_ip_addresses_list(self):
        vmi = {
            "status": {
                "interfaces": [
                    {"name": "eth0", "ipAddresses": ["192.168.1.10", "fe80::1"]},
                ]
            }
        }
        self.assertEqual(VmiOutageScenarioPlugin.get_vmi_ip(vmi), "192.168.1.10")

    def test_get_vmi_ips_skips_link_local_and_dedupes(self):
        vmi = {
            "status": {
                "interfaces": [
                    {
                        "name": "default",
                        "ipAddress": "10.0.0.5",
                        "ipAddresses": ["10.0.0.5", "fe80::1"],
                    },
                    {
                        "name": "secondary",
                        "ipAddress": "192.168.100.2",
                    },
                ]
            }
        }
        self.assertEqual(
            VmiOutageScenarioPlugin.get_vmi_ips(vmi),
            ["10.0.0.5", "192.168.100.2"],
        )

    def test_get_vmi_ip_missing(self):
        self.assertIsNone(VmiOutageScenarioPlugin.get_vmi_ip({}))
        self.assertIsNone(VmiOutageScenarioPlugin.get_vmi_ip({"status": {}}))

    def test_wait_for_guest_reachable_tries_all_ips(self):
        """First interface may be unreachable; later ones must still succeed."""
        self.plugin.affected_vmi = AffectedVMI(
            vmi_name="test-vm", namespace="default"
        )
        multi_ip = copy.deepcopy(self.mock_vmi)
        multi_ip["status"]["interfaces"] = [
            {"ipAddress": "10.0.0.1"},
            {"ipAddress": "10.0.0.9"},
        ]
        self.k8s_client.get_vmi.return_value = multi_ip

        def probe(host, *_a, **_k):
            return host == "10.0.0.9"

        self.plugin.probe_guest_via_pod = MagicMock(side_effect=probe)

        with patch("time.time", side_effect=[100.0, 100.5, 101.0]):
            with patch("time.sleep"):
                result = self.plugin.wait_for_guest_reachable(
                    "test-vm",
                    "default",
                    timeout=30,
                    interval=1,
                    method="icmp",
                    probe_pod="probe-pod",
                )

        self.assertEqual(result, 0)
        probed = [
            c.args[0] for c in self.plugin.probe_guest_via_pod.call_args_list
        ]
        self.assertEqual(probed, ["10.0.0.1", "10.0.0.9"])

    def test_wait_for_guest_reachable_via_pod(self):
        """Probes via a ready helper pod; create is done before chaos."""
        self.plugin.affected_vmi = AffectedVMI(
            vmi_name="test-vm", namespace="default"
        )
        running_with_ip = copy.deepcopy(self.mock_vmi)
        running_with_ip["status"]["interfaces"] = [{"ipAddress": "10.0.0.9"}]
        self.k8s_client.get_vmi.return_value = running_with_ip
        self.k8s_client.exec_cmd_in_pod = MagicMock(return_value="OK\n")

        with patch("time.time", side_effect=[200.0, 200.5, 201.0]):
            with patch("time.sleep"):
                result = self.plugin.wait_for_guest_reachable(
                    "test-vm",
                    "default",
                    timeout=30,
                    interval=1,
                    method="icmp",
                    probe_pod="probe-pod",
                )

        self.assertEqual(result, 0)
        self.assertAlmostEqual(
            self.plugin.affected_vmi.guest_reachable_time, 1.0, places=3
        )
        self.k8s_client.exec_cmd_in_pod.assert_called()

    def test_wait_for_guest_reachable_timeout(self):
        self.plugin.affected_vmi = AffectedVMI(
            vmi_name="test-vm", namespace="default"
        )
        running_with_ip = copy.deepcopy(self.mock_vmi)
        running_with_ip["status"]["interfaces"] = [{"ipAddress": "10.0.0.9"}]
        self.k8s_client.get_vmi.return_value = running_with_ip
        self.k8s_client.exec_cmd_in_pod = MagicMock(return_value="FAIL\n")

        times = itertools.count(0, 10)

        with patch("time.time", side_effect=lambda: float(next(times))):
            with patch("time.sleep"):
                result = self.plugin.wait_for_guest_reachable(
                    "test-vm",
                    "default",
                    timeout=5,
                    interval=1,
                    method="icmp",
                    probe_pod="probe-pod",
                )

        self.assertEqual(result, 1)
        self.assertIsNone(
            getattr(self.plugin.affected_vmi, "guest_reachable_time", None)
        )

    def test_ensure_guest_probe_pod_creates(self):
        self.plugin._create_guest_probe_pod = MagicMock(return_value="probe-pod")

        name, owned = self.plugin._ensure_guest_probe_pod(
            "default", method="tcp"
        )

        self.assertEqual(name, "probe-pod")
        self.assertTrue(owned)
        self.plugin._create_guest_probe_pod.assert_called_once_with(
            "default",
            method="tcp",
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools",
        )

    def test_guest_probe_pod_body_net_raw_only_for_icmp(self):
        icmp_caps = self.plugin._guest_probe_pod_body(
            "p", method="icmp"
        )["spec"]["containers"][0]["securityContext"]["capabilities"]
        self.assertEqual(icmp_caps.get("add"), ["NET_RAW"])
        self.assertEqual(icmp_caps.get("drop"), ["ALL"])

        tcp_caps = self.plugin._guest_probe_pod_body(
            "p", method="tcp"
        )["spec"]["containers"][0]["securityContext"]["capabilities"]
        self.assertNotIn("add", tcp_caps)
        self.assertEqual(tcp_caps.get("drop"), ["ALL"])

    def test_guest_probe_pod_body_uses_custom_image(self):
        body = self.plugin._guest_probe_pod_body(
            "p",
            method="icmp",
            image="registry.local/krkn-tools:latest",
        )
        self.assertEqual(
            body["spec"]["containers"][0]["image"],
            "registry.local/krkn-tools:latest",
        )

    def test_create_guest_probe_pod_cleans_up_on_startup_failure(self):
        self.k8s_client.create_pod = MagicMock(
            side_effect=Exception("Starting pod failed")
        )
        self.k8s_client.delete_pod = MagicMock()

        with self.assertRaises(Exception):
            self.plugin._create_guest_probe_pod("default", method="tcp")

        self.k8s_client.create_pod.assert_called_once()
        self.k8s_client.delete_pod.assert_called_once()
        deleted_name = self.k8s_client.delete_pod.call_args.args[0]
        self.assertTrue(deleted_name.startswith("krkn-guest-ping-"))

    def test_create_guest_probe_pod_waits_for_container_ready(self):
        """New pods use the same container-ready gate as reused pods."""
        self.k8s_client.create_pod = MagicMock()
        self.k8s_client.is_pod_running = MagicMock(return_value=True)
        self.k8s_client.delete_pod = MagicMock()

        pod_name = self.plugin._create_guest_probe_pod(
            "default", method="icmp"
        )

        self.assertTrue(pod_name.startswith("krkn-guest-ping-"))
        self.k8s_client.create_pod.assert_called_once()
        self.k8s_client.is_pod_running.assert_called_with(
            pod_name, "default"
        )
        self.k8s_client.delete_pod.assert_not_called()

    def test_create_guest_probe_pod_cleans_up_on_ready_timeout(self):
        self.k8s_client.create_pod = MagicMock()
        self.k8s_client.is_pod_running = MagicMock(return_value=False)
        self.k8s_client.delete_pod = MagicMock()
        self.plugin._wait_for_probe_pod_ready = MagicMock(
            side_effect=TimeoutError("not ready")
        )

        with self.assertRaises(TimeoutError):
            self.plugin._create_guest_probe_pod("default", method="tcp")

        self.k8s_client.create_pod.assert_called_once()
        self.k8s_client.delete_pod.assert_called_once()

    def test_ensure_guest_probe_pod_reuses_existing(self):
        self.k8s_client.is_pod_running = MagicMock(return_value=True)
        self.plugin._create_guest_probe_pod = MagicMock()

        name, owned = self.plugin._ensure_guest_probe_pod(
            "default",
            probe_pod="krkn-guest-ping-diagnosis",
        )

        self.assertEqual(name, "krkn-guest-ping-diagnosis")
        self.assertFalse(owned)
        self.plugin._create_guest_probe_pod.assert_not_called()
        self.k8s_client.is_pod_running.assert_called_with(
            "krkn-guest-ping-diagnosis", "default"
        )

    def test_execute_scenario_spins_probe_before_delete(self):
        """Helper pod is prepared before VMI delete when guest ping is enabled."""
        config = {
            "parameters": {
                "vm_name": "test-vm",
                "namespace": "default",
                "wait_for_guest_ping": True,
                "guest_ping_settle_seconds": 3,
                "guest_ping_timeout": 30,
                "guest_ping_interval": 1,
            }
        }
        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [
            {"metadata": {"name": "test-vm"}}
        ]
        self.k8s_client.is_pod_running = MagicMock(return_value=True)
        self.k8s_client.exec_cmd_in_pod = MagicMock(return_value="OK\n")
        self.k8s_client.delete_pod = MagicMock()
        self.plugin._create_guest_probe_pod = MagicMock(
            return_value="probe-early"
        )

        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi["metadata"]["creationTimestamp"] = "2023-01-01T00:05:00Z"
        new_vmi["status"]["interfaces"] = [{"ipAddress": "10.0.0.9"}]
        self.k8s_client.get_vmi.side_effect = [
            self.mock_vmi,
            self.mock_vmi,
            new_vmi,
            new_vmi,
            new_vmi,
        ]
        self.k8s_client.delete_vmi.return_value = None

        order = []

        def track_create(*_a, **_k):
            order.append("create_probe")
            return "probe-early"

        def track_delete(*_a, **_k):
            order.append("delete_vmi")

        def track_settle(seconds):
            if seconds == 3:
                order.append("settle")

        self.plugin._create_guest_probe_pod = MagicMock(
            side_effect=track_create
        )
        self.k8s_client.delete_vmi.side_effect = track_delete

        with patch("time.sleep", side_effect=track_settle):
            result = self.plugin.execute_scenario(
                config, self.scenario_telemetry
            )

        self.assertEqual(len(result.recovered), 1)
        self.assertEqual(order[:3], ["create_probe", "settle", "delete_vmi"])
        self.k8s_client.delete_pod.assert_called_once()

    def test_probe_guest_via_pod_tcp_command(self):
        self.k8s_client.exec_cmd_in_pod = MagicMock(return_value="OK")
        ok = self.plugin.probe_guest_via_pod(
            "10.0.0.9",
            "probe-pod",
            "default",
            method="tcp",
            port=3389,
        )
        self.assertTrue(ok)
        cmd = self.k8s_client.exec_cmd_in_pod.call_args.args[0][0]
        self.assertIn("nc -z", cmd)
        self.assertIn("3389", cmd)

    def test_execute_scenario_with_guest_ping_includes_in_total(self):
        """Full flow with wait_for_guest_ping adds guest_reachable_time into total."""
        config = copy.deepcopy(self.config)
        config["scenarios"][0]["parameters"]["wait_for_guest_ping"] = True
        config["scenarios"][0]["parameters"]["guest_ping_method"] = "icmp"
        config["scenarios"][0]["parameters"]["guest_ping_timeout"] = 60
        config["scenarios"][0]["parameters"]["guest_ping_interval"] = 1
        config["scenarios"][0]["parameters"]["guest_ping_settle_seconds"] = 0

        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [{"metadata": {"name": "test-vm"}}]
        self.k8s_client.is_pod_running = MagicMock(return_value=True)
        self.k8s_client.exec_cmd_in_pod = MagicMock(return_value="OK\n")
        self.k8s_client.create_pod = MagicMock()
        self.k8s_client.delete_pod = MagicMock()

        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi["metadata"]["creationTimestamp"] = "2023-01-01T00:05:00Z"
        new_vmi["status"]["interfaces"] = [{"ipAddress": "10.0.0.9"}]

        self.k8s_client.get_vmi.side_effect = [
            self.mock_vmi,  # validate
            self.mock_vmi,  # capture
            new_vmi,  # delete recreate
            new_vmi,  # wait_for_running
            new_vmi,  # wait_for_guest_reachable
        ]
        self.k8s_client.delete_vmi.return_value = None

        with patch("time.sleep"):
            with patch(
                "builtins.open",
                unittest.mock.mock_open(read_data=yaml.dump(config)),
            ):
                result = self.plugin.run(
                    "test-uuid",
                    self.scenario_file,
                    self.telemetry,
                    self.scenario_telemetry,
                )

        self.assertEqual(result, 0)
        recovered = self.scenario_telemetry.affected_vmis.recovered
        self.assertEqual(len(recovered), 1)
        self.assertIsNotNone(recovered[0].guest_reachable_time)
        expected_total = (
            (recovered[0].vmi_rescheduling_time or 0)
            + (recovered[0].vmi_readiness_time or 0)
            + (recovered[0].guest_reachable_time or 0)
        )
        self.assertAlmostEqual(
            recovered[0].total_recovery_time, expected_total, places=2
        )

    def test_as_bool_string_false(self):
        from krkn.scenario_plugins.vmi_outage.vmi_outage_scenario_plugin import (
            _as_bool,
        )

        self.assertFalse(_as_bool("False"))
        self.assertFalse(_as_bool("false"))
        self.assertTrue(_as_bool("True"))
        self.assertTrue(_as_bool(True))
        self.assertFalse(_as_bool(False))

    def test_as_number_blank_and_invalid(self):
        from krkn.scenario_plugins.vmi_outage.vmi_outage_scenario_plugin import (
            _as_number,
        )

        self.assertEqual(_as_number("", 300, int), 300)
        self.assertEqual(_as_number(None, 2, float), 2.0)
        self.assertEqual(_as_number("nope", 22, int), 22)
        self.assertEqual(_as_number("5", 300, int), 5)

    def test_empty_guest_ping_params_do_not_block_default_outage(self):
        """Envsubst blanks must not abort when wait_for_guest_ping is off."""
        config = {
            "parameters": {
                "vm_name": "test-vm",
                "namespace": "default",
                "wait_for_guest_ping": False,
                "guest_ping_timeout": "",
                "guest_ping_interval": "",
                "guest_ping_port": "",
                "guest_ping_settle_seconds": "",
            }
        }
        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [
            {"metadata": {"name": "test-vm"}}
        ]
        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi["metadata"]["creationTimestamp"] = "2023-01-01T00:05:00Z"
        self.k8s_client.get_vmi.side_effect = [
            self.mock_vmi,
            self.mock_vmi,
            new_vmi,
            new_vmi,
        ]
        self.k8s_client.delete_vmi.return_value = None

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        self.assertIsNone(result.error)
        self.assertEqual(len(result.recovered), 1)
        self.k8s_client.delete_vmi.assert_called_once()

    def test_invalid_guest_ping_method_fails_fast(self):
        config = {
            "parameters": {
                "vm_name": "test-vm",
                "namespace": "default",
                "wait_for_guest_ping": True,
                "guest_ping_method": "udp",
            }
        }
        self.k8s_client.get_vmis.return_value = [self.mock_vmi]

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        self.assertIsNotNone(result.error)
        self.assertIn("guest_ping_method", result.error)
        self.k8s_client.delete_vmi.assert_not_called()
        self.k8s_client.create_pod.assert_not_called()

    def test_guest_ping_disabled_excludes_guest_reachable_from_total(self):
        """Disabled path: guest_reachable_time stays None and out of total."""
        config = {
            "parameters": {
                "vm_name": "test-vm",
                "namespace": "default",
                "wait_for_guest_ping": False,
            }
        }
        self.k8s_client.get_vmis.return_value = [self.mock_vmi]
        self.k8s_client.get_vms.return_value = [
            {"metadata": {"name": "test-vm"}}
        ]
        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi["metadata"]["creationTimestamp"] = "2023-01-01T00:05:00Z"
        self.k8s_client.get_vmi.side_effect = [
            self.mock_vmi,
            self.mock_vmi,
            new_vmi,
            new_vmi,
        ]
        self.k8s_client.delete_vmi.return_value = None
        self.k8s_client.create_pod = MagicMock()
        self.k8s_client.exec_cmd_in_pod = MagicMock()

        result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        self.assertIsNone(result.error)
        self.assertEqual(len(result.recovered), 1)
        recovered = result.recovered[0]
        self.assertIsNone(
            getattr(recovered, "guest_reachable_time", None)
        )
        expected_total = (
            (recovered.vmi_rescheduling_time or 0)
            + (recovered.vmi_readiness_time or 0)
        )
        self.assertAlmostEqual(
            recovered.total_recovery_time, expected_total, places=2
        )
        self.k8s_client.create_pod.assert_not_called()
        self.k8s_client.exec_cmd_in_pod.assert_not_called()


if __name__ == "__main__":
    unittest.main()
