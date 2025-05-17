import unittest
from unittest.mock import MagicMock, patch, Mock

import yaml
from kubevirt.rest import ApiException
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.kubevirt_vm_outage.kubevirt_vm_outage_scenario_plugin import KubevirtVmOutageScenarioPlugin


class TestKubevirtVmOutageScenarioPlugin(unittest.TestCase):
    
    def setUp(self):
        """
        Set up test fixtures for KubevirtVmOutageScenarioPlugin
        """
        self.plugin = KubevirtVmOutageScenarioPlugin()
        self.plugin.kubevirt_api = MagicMock()
        self.plugin.k8s_api = MagicMock()
        
        self.mock_vmi = MagicMock()
        self.mock_vmi.metadata = MagicMock()
        self.mock_vmi.metadata.name = "test-vm"
        self.mock_vmi.metadata.namespace = "default"
        self.mock_vmi.status = MagicMock()
        self.mock_vmi.status.phase = "Running"
        
        self.config = {
            "scenarios": [
                {
                    "name": "kubevirt outage test",
                    "scenario": "kubevirt_vm_outage",
                    "parameters": {
                        "vm_name": "test-vm",
                        "namespace": "default",
                        "duration": 0  # Dynamic, for now set to 0 for faster tests
                    }
                }
            ]
        }
        
        self.scenario_file = "/tmp/test_kubevirt_scenario.yaml"
        with open(self.scenario_file, "w") as f:
            yaml.dump(self.config, f)
            
        self.telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        self.scenario_telemetry = MagicMock(spec=ScenarioTelemetry)
        self.telemetry.get_lib_kubernetes.return_value = self.plugin.k8s_api
        
    def test_successful_injection_and_recovery(self):
        """
        Test successful deletion and recovery of a VMI
        """
        self.plugin.get_vmi = MagicMock(return_value=self.mock_vmi)
        self.plugin.validate_environment = MagicMock(return_value=True)
        self.plugin.inject = MagicMock(return_value=0)
        self.plugin.recover = MagicMock(return_value=0)
        
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)
            
        self.assertEqual(result, 0)
        self.plugin.inject.assert_called_once_with("test-vm", "default")
        self.plugin.recover.assert_called_once_with("test-vm", "default")
        
    def test_injection_failure(self):
        """
        Test failure during VMI deletion
        """
        self.plugin.get_vmi = MagicMock(return_value=self.mock_vmi)
        self.plugin.validate_environment = MagicMock(return_value=True)
        self.plugin.inject = MagicMock(return_value=1)  # Failure
        
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)
            
        self.assertEqual(result, 1)
        self.plugin.inject.assert_called_once_with("test-vm", "default")
        self.plugin.recover.assert_not_called()
        
    def test_recovery_when_vmi_does_not_exist(self):
        """
        Test recovery logic when VMI does not exist after deletion
        """
        self.plugin.get_vmi = MagicMock(side_effect=[self.mock_vmi, None])  # First call returns VMI, second call returns None
        self.plugin.validate_environment = MagicMock(return_value=True)
        self.plugin.inject = MagicMock(return_value=0)
        
        self.plugin.original_vmi = self.mock_vmi
        self.plugin.kubevirt_api.create_namespaced_virtual_machine_instance = MagicMock()
        
        api_exception = ApiException(status=404, reason="Not Found")
        running_vmi = MagicMock()
        running_vmi.status.phase = "Running"
        self.plugin.kubevirt_api.read_namespaced_virtual_machine_instance = MagicMock(
            side_effect=[api_exception, running_vmi]
        )
        
        result = self.plugin.recover("test-vm", "default")
        
        self.assertEqual(result, 0)
        self.plugin.kubevirt_api.create_namespaced_virtual_machine_instance.assert_called_once()
        
    def test_validation_failure(self):
        """
        Test validation failure when KubeVirt is not installed
        """
        self.plugin.validate_environment = MagicMock(return_value=False)
        
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)
            
        self.assertEqual(result, 1)
        self.plugin.inject.assert_not_called()
        self.plugin.recover.assert_not_called()


if __name__ == "__main__":
    unittest.main()
