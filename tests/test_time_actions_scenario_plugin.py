#!/usr/bin/env python3

"""
Test suite for TimeActionsScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_time_actions_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.time_actions.time_actions_scenario_plugin import TimeActionsScenarioPlugin


class TestTimeActionsScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for TimeActionsScenarioPlugin
        """
        self.plugin = TimeActionsScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["time_scenarios"])
        self.assertEqual(len(result), 1)

    @unittest.mock.patch('builtins.open', create=True)
    @unittest.mock.patch('yaml.full_load')
    @unittest.mock.patch('logging.error')
    def test_run_exception_handling_with_variable(self, mock_logging_error, mock_yaml, mock_open):
        """
        Test that run() properly captures exception variable and logs it
        This tests the fix for the undefined variable 'e' bug
        """
        # Setup mock to raise exception
        mock_yaml.side_effect = RuntimeError("Test exception message")
        
        mock_lib_telemetry = MagicMock()
        mock_scenario_telemetry = MagicMock()
        mock_krkn_config = {}
        
        # Execute the run method
        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario="test_scenario.yaml",
            krkn_config=mock_krkn_config,
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry
        )
        
        # Assert failure is returned
        self.assertEqual(result, 1)
        
        # Assert logging.error was called with the exception message
        mock_logging_error.assert_called_once()
        error_call_args = str(mock_logging_error.call_args)
        self.assertIn("Test exception message", error_call_args)
        self.assertIn("TimeActionsScenarioPlugin", error_call_args)

    @unittest.mock.patch('builtins.open', create=True)
    @unittest.mock.patch('yaml.full_load')
    def test_run_with_skew_time_exception(self, mock_yaml, mock_open):
        """
        Test that run() handles exceptions from skew_time method
        """
        # Setup mock scenario config
        mock_yaml.return_value = {
            "time_scenarios": [
                {
                    "action": "skew_time",
                    "object_type": "node",
                    "object_name": ["test-node"]
                }
            ]
        }
        
        mock_lib_telemetry = MagicMock()
        mock_kubecli = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_kubecli
        
        # Make skew_time raise an exception
        with unittest.mock.patch.object(self.plugin, 'skew_time', side_effect=Exception("Skew failed")):
            mock_scenario_telemetry = MagicMock()
            mock_krkn_config = {}
            
            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                krkn_config=mock_krkn_config,
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )
            
            # Assert failure is returned
            self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
