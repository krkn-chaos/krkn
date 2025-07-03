import unittest
import time
from unittest.mock import MagicMock, patch

import yaml
from krkn_lib.k8s import KrknKubernetes
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
                "namespace": "default"
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
        # Mock get_vmi to return our mock VMI
        with patch.object(self.plugin, 'get_vmi', return_value=self.mock_vmi):
            # Mock inject and recover to simulate success
            with patch.object(self.plugin, 'inject', return_value=0) as mock_inject:
                with patch.object(self.plugin, 'recover', return_value=0) as mock_recover:
                    with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
                        result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)
                    
        self.assertEqual(result, 0)
        mock_inject.assert_called_once_with("test-vm", "default", False)
        mock_recover.assert_called_once_with("test-vm", "default", False)
        
    def test_injection_failure(self):
        """
        Test failure during VMI deletion
        """
        # Mock get_vmi to return our mock VMI
        with patch.object(self.plugin, 'get_vmi', return_value=self.mock_vmi):
            # Mock inject to simulate failure
            with patch.object(self.plugin, 'inject', return_value=1) as mock_inject:
                with patch.object(self.plugin, 'recover', return_value=0) as mock_recover:
                    with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
                        result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)
                    
        self.assertEqual(result, 1)
        mock_inject.assert_called_once_with("test-vm", "default", False)
        mock_recover.assert_not_called()
        
    def test_disable_auto_restart(self):
        """
        Test VM auto-restart can be disabled
        """
        # Configure test with disable_auto_restart=True
        self.config["scenarios"][0]["parameters"]["disable_auto_restart"] = True
        
        # Mock VM object for patching
        mock_vm = {
            "metadata": {"name": "test-vm", "namespace": "default"},
            "spec": {}
        }
        
        # Mock get_vmi to return our mock VMI
        with patch.object(self.plugin, 'get_vmi', return_value=self.mock_vmi):
            # Mock VM patch operation
            with patch.object(self.plugin, 'patch_vm_spec') as mock_patch_vm:
                mock_patch_vm.return_value = True
                # Mock inject and recover
                with patch.object(self.plugin, 'inject', return_value=0) as mock_inject:
                    with patch.object(self.plugin, 'recover', return_value=0) as mock_recover:
                        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
                            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)
        
        self.assertEqual(result, 0)
        # Should call patch_vm_spec to disable auto-restart
        mock_patch_vm.assert_any_call("test-vm", "default", False)
        # Should call patch_vm_spec to re-enable auto-restart during recovery
        mock_patch_vm.assert_any_call("test-vm", "default", True)
        mock_inject.assert_called_once_with("test-vm", "default", True)
        mock_recover.assert_called_once_with("test-vm", "default", True)
        
    def test_recovery_when_vmi_does_not_exist(self):
        """
        Test recovery logic when VMI does not exist after deletion
        """
        # Store the original VMI in the plugin for recovery
        self.plugin.original_vmi = self.mock_vmi.copy()
        
        # Create a cleaned vmi_dict as the plugin would
        vmi_dict = self.mock_vmi.copy()
        
        # Set up running VMI data for after recovery
        running_vmi = {
            "metadata": {"name": "test-vm", "namespace": "default"},
            "status": {"phase": "Running"}
        }
        
        # Set up time.time to immediately exceed the timeout for auto-recovery
        with patch('time.time', side_effect=[0, 301, 301, 301, 301, 310, 320]):
            # Mock get_vmi to always return None (not auto-recovered)
            with patch.object(self.plugin, 'get_vmi', side_effect=[None, None, running_vmi]):
                # Mock the custom object API to return success
                self.custom_object_client.create_namespaced_custom_object = MagicMock(return_value=running_vmi)
                
                # Run recovery with mocked time.sleep
                with patch('time.sleep'):
                    result = self.plugin.recover("test-vm", "default", False)
        
        self.assertEqual(result, 0)
        # Verify create was called with the right arguments for our API version and kind
        self.custom_object_client.create_namespaced_custom_object.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace="default",
            plural="virtualmachineinstances",
            body=vmi_dict
        )
    
    def test_validation_failure(self):
        """
        Test validation failure when KubeVirt is not installed
        """
        # Mock empty CRD list (no KubeVirt CRDs)
        empty_crd_list = MagicMock()
        empty_crd_list.items = []
        self.k8s_client.list_custom_resource_definition.return_value = empty_crd_list
        
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)
            
        self.assertEqual(result, 1)
        
    def test_delete_vmi_timeout(self):
        """
        Test timeout during VMI deletion
        """
        # Mock successful delete operation
        self.custom_object_client.delete_namespaced_custom_object = MagicMock(return_value={})
        
        # Mock that get_vmi always returns VMI (never gets deleted)
        with patch.object(self.plugin, 'get_vmi', return_value=self.mock_vmi):
            # Simulate timeout by making time.time return values that exceed the timeout
            with patch('time.sleep'), patch('time.time', side_effect=[0, 10, 20, 130, 130, 130, 130, 140]):
                result = self.plugin.inject("test-vm", "default", False)
            
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
