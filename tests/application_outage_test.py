import unittest
import tempfile
import yaml
import os
from unittest.mock import MagicMock, patch
from krkn.scenario_plugins.application_outage.application_outage_scenario_plugin import ApplicationOutageScenarioPlugin


class TestApplicationOutageScenarioPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = ApplicationOutageScenarioPlugin()
        self.mock_lib_telemetry = MagicMock()
        self.mock_scenario_telemetry = MagicMock()
        self.mock_k8s = MagicMock()
        self.mock_lib_telemetry.get_lib_kubernetes.return_value = self.mock_k8s
        
        # Create test config
        self.krkn_config = {
            "tunings": {
                "wait_duration": 10
            },
            # Add necessary cerberus config to prevent errors
            "cerberus": {
                "cerberus_enabled": False
            }
        }
        
        # Create a temporary scenario file
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
        self.valid_scenario = {
            "application_outage": {
                "namespace": "test-namespace",
                "pod_selector": {"app": "test-app"},
                "block": ["Ingress"],
                "duration": 10
            }
        }
        yaml.dump(self.valid_scenario, self.temp_file)
        self.temp_file.close()
    
    def tearDown(self):
        os.unlink(self.temp_file.name)
    
    @patch('time.sleep')
    @patch('krkn.scenario_plugins.application_outage.application_outage_scenario_plugin.cerberus')
    def test_valid_scenario(self, mock_cerberus, mock_sleep):
        # Mock sleep to avoid waiting during test
        mock_sleep.return_value = None
        # Mock cerberus to avoid actual calls
        mock_cerberus.publish_kraken_status.return_value = None
        
        # Run the plugin
        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario=self.temp_file.name,
            krkn_config=self.krkn_config,
            lib_telemetry=self.mock_lib_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry
        )
        
        # Verify the result and interactions
        self.assertEqual(result, 0, "Plugin should exit with 0 on success")
        self.mock_k8s.create_net_policy.assert_called_once()
        self.mock_k8s.delete_net_policy.assert_called_once()
        # Verify cerberus was called
        mock_cerberus.publish_kraken_status.assert_called_once()
    
    def test_invalid_traffic_type(self):
        # Create scenario with invalid traffic type
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as invalid_file:
            invalid_scenario = {
                "application_outage": {
                    "namespace": "test-namespace",
                    "pod_selector": {"app": "test-app"},
                    "block": ["InvalidType"],
                    "duration": 10
                }
            }
            yaml.dump(invalid_scenario, invalid_file)
        
        # Run the plugin
        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario=invalid_file.name,
            krkn_config=self.krkn_config,
            lib_telemetry=self.mock_lib_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry
        )
        
        # Verify the result
        self.assertEqual(result, 1, "Plugin should exit with 1 on invalid traffic type")
        os.unlink(invalid_file.name)
    
    def test_empty_pod_selector(self):
        # Create scenario with empty pod_selector
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as invalid_file:
            invalid_scenario = {
                "application_outage": {
                    "namespace": "test-namespace",
                    "pod_selector": {},  # Empty pod selector
                    "block": ["Ingress"],
                    "duration": 10
                }
            }
            yaml.dump(invalid_scenario, invalid_file)
        
        # Run the plugin
        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario=invalid_file.name,
            krkn_config=self.krkn_config,
            lib_telemetry=self.mock_lib_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry
        )
        
        # Verify the result
        self.assertEqual(result, 1, "Plugin should exit with 1 on empty pod selector")
        os.unlink(invalid_file.name)
    
    def test_missing_pod_selector(self):
        # Create scenario with missing pod_selector
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as invalid_file:
            invalid_scenario = {
                "application_outage": {
                    "namespace": "test-namespace",
                    "block": ["Ingress"],
                    "duration": 10
                }
            }
            yaml.dump(invalid_scenario, invalid_file)
        
        # Run the plugin
        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario=invalid_file.name,
            krkn_config=self.krkn_config,
            lib_telemetry=self.mock_lib_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry
        )
        
        # Verify the result
        self.assertEqual(result, 1, "Plugin should exit with 1 on missing pod selector")
        os.unlink(invalid_file.name)


if __name__ == '__main__':
    unittest.main()
