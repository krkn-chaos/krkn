#!/usr/bin/env python3

"""
Test suite for KubeVirt VM Outage Scenario Plugin

This comprehensive test suite covers the KubevirtVmOutageScenarioPlugin class
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
    python -m unittest tests.test_kubevirt_vm_outage -v

    # Run with coverage
    python -m coverage run -a -m unittest tests/test_kubevirt_vm_outage.py -v

Assisted By: Claude Code
"""

import copy
import itertools
import os
import tempfile
import datetime
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedPod, PodsStatus
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from kubernetes.client.rest import ApiException

from krkn.scenario_plugins.kubevirt_vm_outage.kubevirt_vm_outage_scenario_plugin import KubevirtVmOutageScenarioPlugin


class TestKubevirtVmOutageScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for KubevirtVmOutageScenarioPlugin
        """
        self.plugin = KubevirtVmOutageScenarioPlugin()

        # Create mock k8s client (spec=KrknKubernetes)
        self.k8s_client = MagicMock(spec=KrknKubernetes)
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
                    "name": "kubevirt outage test",
                    "scenario": "kubevirt_vm_outage",
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
        self.scenario_file = os.path.join(temp_dir, "test_kubevirt_scenario.yaml")
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
        self.plugin.affected_pod = AffectedPod(pod_name=f"test-vm-{self.delete_count}", namespace="default")
        self.plugin.affected_pod.pod_rescheduling_time = 5.0
        return 0

    def mock_wait(self, *args, **kwargs):
        """Reusable mock for wait_for_running that tracks calls and sets pod_readiness_time"""
        self.wait_count += 1
        self.plugin.affected_pod.pod_readiness_time = 3.0
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
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 0)
        self.k8s_client.delete_vmi.assert_called_once_with("test-vm", "default")
        
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
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 1)
        self.k8s_client.delete_vmi.assert_called_once_with("test-vm", "default")
        
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
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

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
            with patch('time.time', side_effect=[0, 301, 310]):
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
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

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
        from krkn_lib.models.k8s import PodsStatus, AffectedPod
        self.plugin.pods_status = PodsStatus()
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")
        self.plugin.pods_status = PodsStatus()

        # Mock successful delete operation
        self.k8s_client.delete_vmi.return_value = None

        # Mock that get_vmi always returns VMI with same creationTimestamp (never gets recreated)
        self.k8s_client.get_vmi.return_value = self.mock_vmi

        # Simulate timeout by making time.time return values that exceed the timeout
        with patch('time.sleep'), patch('time.time', side_effect=[0, 10, 20, 130, 130, 130, 130, 140]):
            result = self.plugin.delete_vmi("test-vm", "default", False)

        self.assertEqual(result, 1)
        self.k8s_client.delete_vmi.assert_called_once_with("test-vm", "default")

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
        self.plugin.pods_status = PodsStatus()
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

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
        self.assertIsNotNone(self.plugin.affected_pod.pod_rescheduling_time)

    def test_delete_vmi_with_disable_auto_restart_failure(self):
        """
        Test delete_vmi continues when patch_vm_spec fails and VMI stays deleted
        """
        # Initialize required attributes
        self.plugin.original_vmi = copy.deepcopy(self.mock_vmi)
        self.plugin.pods_status = PodsStatus()
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

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
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

        # Mock VMI in Pending state
        pending_vmi = copy.deepcopy(self.mock_vmi)
        pending_vmi['status']['phase'] = 'Pending'

        self.k8s_client.get_vmi.return_value = pending_vmi

        with patch('time.sleep'):
            with patch('time.time', side_effect=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 121]):
                result = self.plugin.wait_for_running("test-vm", "default", 120)

        self.assertEqual(result, 1)

    def test_wait_for_running_vmi_not_exists(self):
        """
        Test wait_for_running when VMI doesn't exist yet
        """
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

        # First return None (not exists), then return running VMI
        running_vmi = copy.deepcopy(self.mock_vmi)
        running_vmi['status']['phase'] = 'Running'

        self.k8s_client.get_vmi.side_effect = [None, None, running_vmi]

        with patch('time.sleep'):
            # time.time() called: start_time (0), while loop iteration 1 (1), iteration 2 (2), iteration 3 (3), end_time (3)
            with patch('time.time', side_effect=[0, 1, 2, 3, 3]):
                result = self.plugin.wait_for_running("test-vm", "default", 120)

        self.assertEqual(result, 0)
        self.assertIsNotNone(self.plugin.affected_pod.pod_readiness_time)

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
            with patch('time.time', side_effect=[0, 301]):
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
        self.assertIsInstance(result, PodsStatus)
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
        self.assertIsInstance(result, PodsStatus)
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

        self.assertEqual(result, ["kubevirt_vm_outage"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
