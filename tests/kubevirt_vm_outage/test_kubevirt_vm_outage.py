import unittest
from unittest.mock import MagicMock, patch, Mock
import itertools

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
        self.plugin.recover = MagicMock()

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)
            
        self.assertEqual(result, 1)
        self.plugin.inject.assert_called_once_with("test-vm", "default")
        self.plugin.recover.assert_not_called()
        
    def test_recovery_when_vmi_does_not_exist(self):
        print("[test] Starting test_recovery_when_vmi_does_not_exist")

        plugin = Mock()
        plugin.logger = MagicMock()
        plugin.recover_timeout = 3

        api_exception = ApiException(status=404, reason="Not Found")

        call_count = {'count': 0}

        def read_vmi_side_effect(name, namespace):
            call_count['count'] += 1
            print(f"[mock] read call #{call_count['count']}")
            if call_count['count'] == 1:
                raise api_exception
            else:
                running_vmi = MagicMock()
                running_vmi.status = MagicMock()
                running_vmi.status.phase = "Running"
                return running_vmi

        plugin.kubevirt_api = Mock()
        plugin.kubevirt_api.read_namespaced_virtual_machine_instance = MagicMock(side_effect=read_vmi_side_effect)

        def recover(self, name, namespace):
            logging.info(f"[recover] Starting recovery for {name} in {namespace}")
            try:
                vmi = self.kubevirt_api.read_namespaced_virtual_machine_instance(name, namespace)
            except ApiException as e:
                if e.status == 404:
                    logging.warning(f"VMI {name} not found initially")
                    vmi = None
                else:
                    raise

            for attempt in range(1, self.recover_timeout + 1):
                try:
                    vmi = self.kubevirt_api.read_namespaced_virtual_machine_instance(name, namespace)
                    phase = getattr(vmi.status, "phase", None)
                    if phase == "Running":
                        return 0
                except ApiException as e:
                    if e.status == 404:
                        pass
                    else:
                        raise
                time.sleep(0.01)
            return 1

        plugin.recover = recover.__get__(plugin)

        with patch("time.sleep", return_value=None):
            result = plugin.recover("test-vm", "default")

        print(f"[test] recover returned {result}")
        self.assertEqual(result, 0)



    def test_validation_failure(self):
        """
        Testing validation failure when KubeVirt is not installed
        """
        self.plugin.validate_environment = MagicMock(return_value=False)
        self.plugin.inject = MagicMock()
        self.plugin.recover = MagicMock()

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(self.config))):
            result = self.plugin.run("test-uuid", self.scenario_file, {}, self.telemetry, self.scenario_telemetry)
            
        self.assertEqual(result, 1)
        self.plugin.inject.assert_not_called()
        self.plugin.recover.assert_not_called()


if __name__ == "__main__":
    unittest.main()
