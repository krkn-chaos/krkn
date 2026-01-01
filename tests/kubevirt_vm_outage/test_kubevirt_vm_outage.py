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

        # Mock get_vmi to first return the VMI, then None (deleted), then recreated VMI (running)
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=[
                self.mock_vmi,  # Initial get in validate_environment
                self.mock_vmi,  # Get before delete
                self.mock_vmi_recreated,  # After delete (recreated with new timestamp)
                self.mock_vmi_recreated,  # Check if running
            ]
        )

        # Mock delete operation
        self.custom_object_client.delete_namespaced_custom_object = MagicMock(return_value={})

        # Use a counter for time.time() that increments with each call
        time_counter = [0]
        def mock_time():
            time_counter[0] += 1
            return float(time_counter[0])

        with patch('time.time', side_effect=mock_time), patch('time.sleep'):
            with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
                result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)

        self.assertEqual(result, 0)
        
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

        # Mock get operations
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=[
                self.mock_vmi,  # validate_environment
                self.mock_vmi,  # get before delete
                mock_vm,  # get VM for patching
                self.mock_vmi_recreated,  # After delete (recreated)
                self.mock_vmi_recreated,  # Check if running
            ]
        )

        # Mock patch and delete operations
        self.custom_object_client.patch_namespaced_custom_object = MagicMock(return_value=mock_vm)
        self.custom_object_client.delete_namespaced_custom_object = MagicMock(return_value={})

        # Use a counter for time.time() that increments with each call
        time_counter = [0]
        def mock_time():
            time_counter[0] += 1
            return float(time_counter[0])

        with patch('time.time', side_effect=mock_time), patch('time.sleep'):
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

        # Mock get_vmi to return None (VMI not found), then the running VMI after recreation
        self.custom_object_client.get_namespaced_custom_object = MagicMock(
            side_effect=[
                ApiException(status=404, reason="Not Found"),  # First check - not found
                running_vmi,  # After creation - check if running
            ]
        )

        # Mock the create API to return success
        self.custom_object_client.create_namespaced_custom_object = MagicMock(return_value=running_vmi)

        # Use a counter for time.time() that increments with each call
        time_counter = [0]
        def mock_time():
            time_counter[0] += 1
            return float(time_counter[0])

        # Run recovery with mocked time
        with patch('time.time', side_effect=mock_time), patch('time.sleep'):
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
                {"items": []},  # For validate_environment - empty VMs list (no KubeVirt)
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

        # Mock that get_vmi always returns VMI with same timestamp (never gets deleted/recreated)
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
