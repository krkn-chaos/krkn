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

        # Create mock k8s client
        self.k8s_client = MagicMock()
        self.custom_object_client = MagicMock()
        self.k8s_client.custom_object_client = self.custom_object_client
        self.plugin.k8s_client = self.k8s_client
        self.plugin.custom_object_client = self.custom_object_client

        # Mock methods needed for KubeVirt operations
        self.k8s_client.list_custom_resource_definition = MagicMock()

        # Mock custom resource definition list with KubeVirt CRDs
        crd_list = MagicMock()
        crd_item = MagicMock()
        crd_item.spec = MagicMock()
        crd_item.spec.group = "kubevirt.io"
        crd_list.items = [crd_item]
        self.k8s_client.list_custom_resource_definition.return_value = crd_list

        # Mock VMI data with timezone-aware timestamps
        base_time = datetime.now(timezone.utc)
        self.mock_vmi = {
            "metadata": {
                "name": "test-vm",
                "namespace": "default",
                "creationTimestamp": base_time.isoformat() + "Z"
            },
            "status": {
                "phase": "Running"
            }
        }

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
        # Mock list_namespaces_by_regex to return a single namespace
        self.k8s_client.list_namespaces_by_regex = MagicMock(return_value=["default"])

        # Mock list_namespaced_custom_object to return our VMI
        self.custom_object_client.list_namespaced_custom_object = MagicMock(
            side_effect=[
                {"items": [self.mock_vmi]},  # For get_vmis
                {"items": [{"metadata": {"name": "test-vm"}}]},  # For validate_environment
            ]
        )

        # Mock get_namespaced_custom_object with a sequence that handles multiple calls
        # Call sequence:
        # 1. validate_environment: get original VMI
        # 2. execute_scenario: get VMI before deletion
        # 3. delete_vmi: loop checking if timestamp changed (returns recreated VMI on first check)
        # 4+. wait_for_running: loop until phase is Running (may call multiple times)
        get_vmi_responses = [
            self.mock_vmi,            # Initial get in validate_environment
            self.mock_vmi,            # Get before delete
            self.mock_vmi_recreated,  # After delete (recreated with new timestamp)
            self.mock_vmi_recreated,  # Check if running
        ]

        class GetVmiSideEffect:
            """
            Callable helper that returns a predefined sequence of VMIs.
            If called more times than there are responses, it fails the test
            to surface unexpected additional calls instead of silently
            masking them.
            """
            def __init__(self, responses):
                self._responses = responses
                self._call_iter = itertools.count()
                self.call_count = 0

            def __call__(self, *args, **kwargs):
                call_num = next(self._call_iter)
                self.call_count = call_num + 1

                if call_num >= len(self._responses):
                    raise AssertionError(
                        f"get_vmi_side_effect called more times ({call_num + 1}) "
                        f"than expected ({len(self._responses)})."
                    )
                return self._responses[call_num]

        get_vmi_side_effect = GetVmiSideEffect(get_vmi_responses)
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=get_vmi_side_effect
        )

        # Mock delete operation
        self.custom_object_client.delete_namespaced_custom_object = MagicMock(return_value={})

        with patch('time.time', side_effect=self.create_incrementing_time_function()), patch('time.sleep'):
            with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
                result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 0)
        # Verify get_namespaced_custom_object was called exactly as many times as
        # there are predefined responses
        self.assertEqual(
            self.custom_object_client.get_namespaced_custom_object.call_count,
            len(get_vmi_responses),
        )

        # Verify that the VMI delete operation was performed once with expected parameters
        self.custom_object_client.delete_namespaced_custom_object.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace="default",
            plural="virtualmachineinstances",
            name="test-vm",
        )

    def test_injection_failure(self):
        """
        Test failure during VMI deletion
        """
        # Mock list_namespaces_by_regex
        self.k8s_client.list_namespaces_by_regex = MagicMock(return_value=["default"])

        # Mock list to return VMI
        self.custom_object_client.list_namespaced_custom_object = MagicMock(
            side_effect=[
                {"items": [self.mock_vmi]},  # For get_vmis
                {"items": [{"metadata": {"name": "test-vm"}}]},  # For validate_environment
            ]
        )

        # Mock get_vmi
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=[
                self.mock_vmi,  # validate_environment
                self.mock_vmi,  # get before delete
            ]
        )

        # Mock delete to raise an error
        self.custom_object_client.delete_namespaced_custom_object = MagicMock(
            side_effect=ApiException(status=500, reason="Internal Server Error")
        )

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 1)
        # Verify delete was attempted before the error occurred
        self.custom_object_client.delete_namespaced_custom_object.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace="default",
            plural="virtualmachineinstances",
            name="test-vm"
        )

    def test_disable_auto_restart(self):
        """
        Test VM auto-restart can be disabled
        """
        # Configure test with disable_auto_restart=True
        self.config["scenarios"][0]["parameters"]["disable_auto_restart"] = True

        # Mock list_namespaces_by_regex
        self.k8s_client.list_namespaces_by_regex = MagicMock(return_value=["default"])

        # Mock VM object for patching
        mock_vm = {
            "metadata": {"name": "test-vm", "namespace": "default"},
            "spec": {"running": True}
        }

        # Mock list to return VMI
        self.custom_object_client.list_namespaced_custom_object = MagicMock(
            side_effect=[
                {"items": [self.mock_vmi]},  # For get_vmis
                {"items": [{"metadata": {"name": "test-vm"}}]},  # For validate_environment
            ]
        )

        # Mock get_namespaced_custom_object with detailed call sequence
        # Call sequence:
        # 1. execute_scenario: get VMI before deletion
        # 2. patch_vm_spec: get VM for patching
        # 3. delete_vmi: loop checking if VMI timestamp changed
        # 4+. wait_for_running: loop until VMI phase is Running
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=[
                self.mock_vmi,  # Call 1: get VMI before delete
                mock_vm,  # Call 2: get VM for patching (different resource type)
                self.mock_vmi_recreated,  # Call 3: delete_vmi detects new timestamp
                self.mock_vmi_recreated,  # Call 4: wait_for_running checks phase
            ]
        )

        # Mock patch and delete operations
        self.custom_object_client.patch_namespaced_custom_object = MagicMock(return_value=mock_vm)
        self.custom_object_client.delete_namespaced_custom_object = MagicMock(return_value={})

        with patch('time.time', side_effect=self.create_incrementing_time_function()), patch('time.sleep'):
            with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
                result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 0)
        # Verify patch was called to disable auto-restart
        self.custom_object_client.patch_namespaced_custom_object.assert_called()

    def test_recovery_when_vmi_does_not_exist(self):
        """
        Test recovery logic when VMI does not exist after deletion
        """
        # Store the original VMI in the plugin for recovery
        self.plugin.original_vmi = self.mock_vmi.copy()

        # Initialize affected_pod which is used by wait_for_running
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

        # Set up running VMI data for after recovery
        running_vmi = {
            "metadata": {
                "name": "test-vm",
                "namespace": "default",
                "creationTimestamp": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat() + "Z"
            },
            "status": {"phase": "Running"}
        }

        # Mock get_namespaced_custom_object call sequence triggered during recovery
        # Call sequence:
        # 1. wait_for_running: first loop iteration - VMI creation requested but not visible yet
        # 2. wait_for_running: subsequent iterations - VMI exists and is running
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=[
                ApiException(status=404, reason="Not Found"),  # VMI not visible yet after create
                running_vmi,  # VMI now exists and is running
            ]
        )

        # Mock the create API to return success
        self.custom_object_client.create_namespaced_custom_object = MagicMock(return_value=running_vmi)

        # Run recovery with mocked time
        with patch('time.time', side_effect=self.create_incrementing_time_function()), patch('time.sleep'):
            result = self.plugin.recover("test-vm", "default", False)

        self.assertEqual(result, 0)
        # Verify create was called with the right arguments
        self.custom_object_client.create_namespaced_custom_object.assert_called_once()

    def test_validation_failure(self):
        """
        Test validation failure when KubeVirt is not installed
        """
        # Populate vmis_list to avoid randrange error
        self.plugin.vmis_list = [self.mock_vmi]

        # Mock get_vmis to not clear the list
        with patch.object(self.plugin, 'get_vmis'):
            # Mock get_vmi to return our mock VMI
            with patch.object(self.plugin, 'get_vmi', return_value=self.mock_vmi):
                # Mock validate_environment to return False (KubeVirt not installed)
                with patch.object(self.plugin, 'validate_environment', return_value=False):
                    with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
                        result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

        # When validation fails, run() returns 1 due to exception handling
        self.assertEqual(result, 1)

    # ==================== Timeout Tests ====================

    def test_delete_vmi_timeout(self):
        """
        Test timeout during VMI deletion
        """
        # Store original VMI
        self.plugin.original_vmi = self.mock_vmi

        # Initialize required attributes
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")
        self.plugin.pods_status = PodsStatus()

        # Mock successful delete operation
        self.custom_object_client.delete_namespaced_custom_object = MagicMock(return_value={})

        # Mock get_vmi to always return the same VMI with unchanged creationTimestamp
        # This simulates that the VMI has NOT been recreated after deletion
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            return_value=self.mock_vmi
        )

        # Simulate timeout by making time.time return values that exceed the timeout
        with patch('time.sleep'), patch('time.time', side_effect=[0, 10, 20, 130, 140]):
            result = self.plugin.delete_vmi("test-vm", "default", False, timeout=120)

        self.assertEqual(result, 1)
        self.custom_object_client.delete_namespaced_custom_object.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace="default",
            plural="virtualmachineinstances",
            name="test-vm"
        )

    def test_wait_for_running_timeout(self):
        """
        Test wait_for_running times out when VMI doesn't reach Running state
        """
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

        # Mock VMI in Pending state
        pending_vmi = self.mock_vmi.copy()
        pending_vmi['status']['phase'] = 'Pending'

        with patch.object(self.plugin, 'get_vmi', return_value=pending_vmi):
            with patch('time.sleep'):
                with patch('time.time', side_effect=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 121]):
                    result = self.plugin.wait_for_running("test-vm", "default", 120)

        self.assertEqual(result, 1)

    # ==================== API Exception Tests ====================

    def test_get_vmi_api_exception_non_404(self):
        """
        Test get_vmi raises ApiException for non-404 errors
        """
        # Mock API exception with non-404 status
        api_error = ApiException(status=500, reason="Internal Server Error")
        self.custom_object_client.get_namespaced_custom_object = MagicMock(side_effect=api_error)

        with self.assertRaises(ApiException):
            self.plugin.get_vmi("test-vm", "default")

    def test_get_vmi_general_exception(self):
        """
        Test get_vmi raises general exceptions
        """
        # Mock general exception
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=Exception("Connection error")
        )

        with self.assertRaises(Exception):
            self.plugin.get_vmi("test-vm", "default")

    def test_get_vmis_api_exception_404(self):
        """
        Test get_vmis handles 404 ApiException gracefully
        """
        self.k8s_client.list_namespaces_by_regex = MagicMock(return_value=["default"])
        api_error = ApiException(status=404, reason="Not Found")
        self.custom_object_client.list_namespaced_custom_object = MagicMock(side_effect=api_error)

        # Should not raise, returns empty list
        result = self.plugin.get_vmis("test-vm", "default")
        self.assertEqual(result, [])

    def test_get_vmis_api_exception_non_404(self):
        """
        Test get_vmis raises ApiException for non-404 errors
        """
        self.k8s_client.list_namespaces_by_regex = MagicMock(return_value=["default"])
        api_error = ApiException(status=500, reason="Internal Server Error")
        self.custom_object_client.list_namespaced_custom_object = MagicMock(side_effect=api_error)

        with self.assertRaises(ApiException):
            self.plugin.get_vmis("test-vm", "default")

    def test_delete_vmi_api_exception_404(self):
        """
        Test delete_vmi handles 404 ApiException during deletion
        """
        # Initialize required attributes
        self.plugin.original_vmi = self.mock_vmi.copy()
        self.plugin.original_vmi['metadata']['creationTimestamp'] = '2023-01-01T00:00:00Z'
        self.plugin.pods_status = PodsStatus()
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

        api_error = ApiException(status=404, reason="Not Found")
        self.custom_object_client.delete_namespaced_custom_object = MagicMock(side_effect=api_error)

        result = self.plugin.delete_vmi("test-vm", "default", False)

        self.assertEqual(result, 1)

    def test_delete_vmi_api_exception_non_404(self):
        """
        Test delete_vmi handles non-404 ApiException during deletion
        """
        # Initialize required attributes
        self.plugin.original_vmi = self.mock_vmi.copy()
        self.plugin.original_vmi['metadata']['creationTimestamp'] = '2023-01-01T00:00:00Z'
        self.plugin.pods_status = PodsStatus()
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

        api_error = ApiException(status=500, reason="Internal Server Error")
        self.custom_object_client.delete_namespaced_custom_object = MagicMock(side_effect=api_error)

        result = self.plugin.delete_vmi("test-vm", "default", False)

        self.assertEqual(result, 1)

    def test_patch_vm_spec_api_exception(self):
        """
        Test patch_vm_spec handles ApiException
        """
        api_error = ApiException(status=404, reason="Not Found")
        self.custom_object_client.get_namespaced_custom_object = MagicMock(side_effect=api_error)

        result = self.plugin.patch_vm_spec("test-vm", "default", False)

        self.assertFalse(result)

    def test_patch_vm_spec_general_exception(self):
        """
        Test patch_vm_spec handles general exceptions
        """
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=Exception("Connection error")
        )

        result = self.plugin.patch_vm_spec("test-vm", "default", False)

        self.assertFalse(result)

    # ==================== Helper Method Tests ====================

    def test_get_vmis_with_regex_matching(self):
        """
        Test get_vmis successfully filters VMIs by regex pattern
        """
        # Mock namespace list
        self.k8s_client.list_namespaces_by_regex = MagicMock(return_value=["default", "test-ns"])

        # Mock VMI list with multiple VMIs
        vmi_list = {
            "items": [
                {"metadata": {"name": "test-vm-1"}, "status": {"phase": "Running"}},
                {"metadata": {"name": "test-vm-2"}, "status": {"phase": "Running"}},
                {"metadata": {"name": "other-vm"}, "status": {"phase": "Running"}},
            ]
        }
        self.custom_object_client.list_namespaced_custom_object = MagicMock(return_value=vmi_list)

        # Test with regex pattern that matches test-vm-*
        self.plugin.get_vmis("test-vm-.*", "default")

        # Should have 4 VMs (2 per namespace * 2 namespaces)
        self.assertEqual(len(self.plugin.vmis_list), 4)
        # Verify only test-vm-* were added
        for vmi in self.plugin.vmis_list:
            self.assertTrue(vmi["metadata"]["name"].startswith("test-vm-"))

    def test_patch_vm_spec_success(self):
        """
        Test patch_vm_spec successfully patches VM
        """
        mock_vm = {
            "metadata": {"name": "test-vm", "namespace": "default"},
            "spec": {"running": True}
        }

        self.custom_object_client.get_namespaced_custom_object = MagicMock(return_value=mock_vm)
        self.custom_object_client.patch_namespaced_custom_object = MagicMock(return_value=mock_vm)

        result = self.plugin.patch_vm_spec("test-vm", "default", False)

        self.assertTrue(result)
        self.custom_object_client.patch_namespaced_custom_object.assert_called_once()

    def test_validate_environment_exception(self):
        """
        Test validate_environment handles exceptions
        """
        self.custom_object_client.list_namespaced_custom_object = MagicMock(
            side_effect=Exception("Connection error")
        )

        result = self.plugin.validate_environment("test-vm", "default")

        self.assertFalse(result)

    def test_validate_environment_vmi_not_found(self):
        """
        Test validate_environment when VMI doesn't exist
        """
        # Mock CRDs exist
        mock_crd_list = MagicMock()
        mock_crd_list.items = MagicMock(return_value=["item1"])
        self.custom_object_client.list_namespaced_custom_object = MagicMock(return_value=mock_crd_list)

        # Mock VMI not found
        with patch.object(self.plugin, 'get_vmi', return_value=None):
            result = self.plugin.validate_environment("test-vm", "default")

        self.assertFalse(result)

    # ==================== Delete VMI Tests ====================

    def test_delete_vmi_successful_recreation(self):
        """
        Test delete_vmi succeeds when VMI is recreated with new creationTimestamp
        """
        # Initialize required attributes - use deepcopy to avoid shared references
        self.plugin.original_vmi = copy.deepcopy(self.mock_vmi)
        self.plugin.original_vmi['metadata']['creationTimestamp'] = '2023-01-01T00:00:00Z'
        self.plugin.pods_status = PodsStatus()
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

        self.custom_object_client.delete_namespaced_custom_object = MagicMock(return_value={})

        # Mock get_vmi to return VMI with new creationTimestamp - use deepcopy
        new_vmi = copy.deepcopy(self.mock_vmi)
        new_vmi['metadata']['creationTimestamp'] = '2023-01-01T00:05:00Z'

        # Use itertools to create an infinite iterator for time values
        time_iter = itertools.count(0, 0.001)

        with patch.object(self.plugin, 'get_vmi', return_value=new_vmi):
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
        self.plugin.original_vmi = self.mock_vmi.copy()
        self.plugin.original_vmi['metadata']['creationTimestamp'] = '2023-01-01T00:00:00Z'
        self.plugin.pods_status = PodsStatus()
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

        # Mock patch_vm_spec to fail
        with patch.object(self.plugin, 'patch_vm_spec', return_value=False):
            self.custom_object_client.delete_namespaced_custom_object = MagicMock(return_value={})

            # Mock VMI deleted (returns None) - it will timeout waiting for recreation
            with patch.object(self.plugin, 'get_vmi', return_value=None):
                with patch('time.sleep'):
                    # Use itertools to create infinite time sequence
                    # Use 1.0 increment to quickly reach timeout (120 seconds)
                    time_iter = itertools.count(0, 1.0)
                    with patch('time.time', side_effect=lambda: next(time_iter)):
                        result = self.plugin.delete_vmi("test-vm", "default", True)

        # When VMI stays deleted (None), delete_vmi waits for recreation and times out
        self.assertEqual(result, 1)

    # ==================== Wait for Running Tests ====================

    def test_wait_for_running_vmi_not_exists(self):
        """
        Test wait_for_running when VMI doesn't exist yet
        """
        self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")

        # First return None (not exists), then return running VMI
        running_vmi = self.mock_vmi.copy()
        running_vmi['status']['phase'] = 'Running'

        with patch.object(self.plugin, 'get_vmi', side_effect=[None, None, running_vmi]):
            with patch('time.sleep'):
                # time.time() called: start_time (0), iteration 1 (1), iteration 2 (2), iteration 3 (3), end_time (3)
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
        self.plugin.original_vmi = self.mock_vmi.copy()

        self.custom_object_client.create_namespaced_custom_object = MagicMock(
            side_effect=Exception("Creation failed")
        )

        with patch.object(self.plugin, 'get_vmi', return_value=None):
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

        self.assertEqual(result, 1)

    def test_execute_scenario_vmi_not_found(self):
        """
        Test execute_scenario when VMI is not found after get_vmi
        """
        self.plugin.vmis_list = [self.mock_vmi]

        config = {
            "parameters": {
                "vm_name": "test-vm",
                "namespace": "default"
            }
        }

        with patch.object(self.plugin, 'get_vmis'):
            with patch.object(self.plugin, 'validate_environment', return_value=True):
                # First get_vmi returns VMI, second returns None
                with patch.object(self.plugin, 'get_vmi', side_effect=[self.mock_vmi, None]):
                    result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        # Should be PodsStatus with unrecovered pod
        self.assertIsInstance(result, type(self.plugin.pods_status))

    def test_execute_scenario_with_kill_count(self):
        """
        Test execute_scenario with kill_count > 1
        """
        # Create multiple VMIs
        vmi_1 = self.mock_vmi.copy()
        vmi_1["metadata"]["name"] = "test-vm-1"
        vmi_2 = self.mock_vmi.copy()
        vmi_2["metadata"]["name"] = "test-vm-2"

        self.plugin.vmis_list = [vmi_1, vmi_2]

        config = {
            "parameters": {
                "vm_name": "test-vm",
                "namespace": "default",
                "kill_count": 2
            }
        }

        # Reset counters
        self.delete_count = 0
        self.wait_count = 0

        with patch.object(self.plugin, 'get_vmis'):
            with patch.object(self.plugin, 'validate_environment', return_value=True):
                with patch.object(self.plugin, 'get_vmi', side_effect=[vmi_1, vmi_2]):
                    with patch.object(self.plugin, 'delete_vmi', side_effect=self.mock_delete) as mock_del:
                        with patch.object(self.plugin, 'wait_for_running', side_effect=self.mock_wait) as mock_wt:
                            result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        # Should call delete_vmi and wait_for_running twice
        self.assertEqual(mock_del.call_count, 2)
        self.assertEqual(mock_wt.call_count, 2)

    def test_execute_scenario_wait_for_running_failure(self):
        """
        Test execute_scenario when wait_for_running fails
        """
        self.plugin.vmis_list = [self.mock_vmi]

        config = {
            "parameters": {
                "vm_name": "test-vm",
                "namespace": "default"
            }
        }

        def mock_delete(*args, **kwargs):
            self.plugin.affected_pod = AffectedPod(pod_name="test-vm", namespace="default")
            self.plugin.affected_pod.pod_rescheduling_time = 5.0
            return 0

        with patch.object(self.plugin, 'get_vmis'):
            with patch.object(self.plugin, 'validate_environment', return_value=True):
                with patch.object(self.plugin, 'get_vmi', return_value=self.mock_vmi):
                    with patch.object(self.plugin, 'delete_vmi', side_effect=mock_delete):
                        with patch.object(self.plugin, 'wait_for_running', return_value=1):
                            result = self.plugin.execute_scenario(config, self.scenario_telemetry)

        # Should have unrecovered pod
        self.assertEqual(len(result.unrecovered), 1)

    # ==================== Initialization Tests ====================

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
