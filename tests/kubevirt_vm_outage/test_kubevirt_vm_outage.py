import unittest
import time
from unittest.mock import MagicMock, patch

import yaml
from kubernetes.client.rest import ApiException
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedPod, PodsStatus
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

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
        
        # Mock VMI data
        self.mock_vmi = {
            "metadata": {
                "name": "test-vm",
                "namespace": "default",
                "creationTimestamp": "2024-01-01T00:00:00Z"
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
                "creationTimestamp": "2024-01-01T00:01:00Z"
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
        import tempfile, os
        temp_dir = tempfile.gettempdir()
        self.scenario_file = os.path.join(temp_dir, "test_kubevirt_scenario.yaml")
        with open(self.scenario_file, "w") as f:
            yaml.dump(self.config, f)
            
        # Mock dependencies
        self.telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        self.scenario_telemetry = MagicMock(spec=ScenarioTelemetry)
        self.telemetry.get_lib_kubernetes.return_value = self.k8s_client
    
    def create_incrementing_time_function(self):
        """
        Create an incrementing time function that returns sequential float values.
        Returns a callable that can be used with patch('time.time', side_effect=...)
        """
        time_counter = [0]
        def mock_time():
            time_counter[0] += 1
            return float(time_counter[0])
        return mock_time
        
    def test_successful_injection_and_recovery(self):
        """
        Test successful deletion and recovery of a VMI
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
        def get_vmi_side_effect(*args, **kwargs):
            """
            Return a predefined sequence of VMIs. If the function is called more
            times than there are responses, fail the test to surface unexpected
            additional calls instead of silently masking them.
            """
            index = get_vmi_side_effect.call_count
            try:
                return get_vmi_responses[index]
            except IndexError:
                raise AssertionError(
                    f"get_vmi_side_effect called more times ({index + 1}) "
                    f"than expected ({len(get_vmi_responses)})."
                )
            finally:
                get_vmi_side_effect.call_count += 1
        get_vmi_side_effect.call_count = 0
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=get_vmi_side_effect
        )

        # Mock delete operation
        self.custom_object_client.delete_namespaced_custom_object = MagicMock(return_value={})

        with patch('time.time', side_effect=self.create_incrementing_time_function()), patch('time.sleep'):
            with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
                result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 0)
        # Verify get_namespaced_custom_object was called at least the minimum expected times
        # (actual count may be higher due to wait_for_running loop iterations)
        self.assertGreaterEqual(self.custom_object_client.get_namespaced_custom_object.call_count, 4)
        
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
        # NOTE: This mock handles both VMI (virtualmachineinstances) and VM (virtualmachines) calls
        # Call sequence:
        # 1. validate_environment: get VMI (plural=virtualmachineinstances)
        # 2. execute_scenario: get VMI before deletion (plural=virtualmachineinstances)
        # 3. patch_vm_spec: get VM for patching (plural=virtualmachines)
        # 4. delete_vmi: loop checking if VMI timestamp changed (plural=virtualmachineinstances)
        # 5+. wait_for_running: loop until VMI phase is Running (plural=virtualmachineinstances)
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=[
                self.mock_vmi,  # Call 1: validate_environment
                self.mock_vmi,  # Call 2: get VMI before delete
                mock_vm,  # Call 3: get VM for patching (different resource type)
                self.mock_vmi_recreated,  # Call 4: delete_vmi detects new timestamp
                self.mock_vmi_recreated,  # Call 5: wait_for_running checks phase
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
                "creationTimestamp": "2024-01-01T00:02:00Z"
            },
            "status": {"phase": "Running"}
        }

        # Mock get_namespaced_custom_object call sequence in recover method
        # Call sequence:
        # 1. wait_for_running (line 391): first loop iteration - VMI may not be fully created yet
        # 2. wait_for_running: subsequent loop iterations - VMI exists and is running
        # Note: recover() does NOT call get_vmi before creating the VMI - it only checks
        # if self.original_vmi exists, then directly calls create_namespaced_custom_object.
        # All get_vmi calls happen within wait_for_running after VMI creation.
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=[
                ApiException(status=404, reason="Not Found"),  # wait_for_running: VMI still being created
                running_vmi,  # wait_for_running: VMI now exists and is running
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
        # Mock list_namespaces_by_regex
        self.k8s_client.list_namespaces_by_regex = MagicMock(return_value=["default"])

        # Mock list to return VMI for get_vmis
        self.custom_object_client.list_namespaced_custom_object = MagicMock(
            side_effect=[
                {"items": [self.mock_vmi]},  # For get_vmis
                {"items": []},  # For validate_environment - empty result simulating no KubeVirt CRDs  
            ]
        )

        # Mock get_vmi to return VMI
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            return_value=self.mock_vmi
        )

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 1)
        
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

        # Mock get_vmi to always return the same VMI with unchanged creationTimestamp.
        # This simulates a scenario where the VMI has NOT been recreated after deletion
        # (i.e., still has the original creationTimestamp from before deletion).
        # delete_vmi (lines 315-320) loops checking if creationTimestamp changed to detect
        # successful recreation. Since it never changes here, the loop continues until
        # the mocked time exceeds the timeout value, exercising the timeout path.

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


if __name__ == "__main__":
    unittest.main()
