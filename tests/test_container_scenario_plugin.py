#!/usr/bin/env python3

"""
Test suite for ContainerScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_container_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock,patch

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.container.container_scenario_plugin import ContainerScenarioPlugin

import tempfile
import yaml

class TestContainerScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ContainerScenarioPlugin
        """
        self.plugin = ContainerScenarioPlugin()

    @patch.object(
        ContainerScenarioPlugin,
        "start_monitoring"
    )
    @patch.object(
        ContainerScenarioPlugin,
        "container_killing_in_pod"
    )
    
    def test_skip_scenario_when_no_targets_found(
        self,
        mock_container_killing,
        mock_start_monitoring,
    ):
        """
        Test scenario skips gracefully when no matching
        container targets are found
        """
        mock_container_killing.return_value = None
        mock_future = MagicMock()
        mock_snapshot = MagicMock()
        mock_result = MagicMock()
        
        mock_result.unrecovered = []
        mock_snapshot.get_pods_status.return_value = (
            mock_result
        )
        
        mock_future.result.return_value = mock_snapshot
        mock_start_monitoring.return_value = mock_future
        
        scenario_data = {
            "scenarios" : [
                {
                    "namespace": "default",
                    "label_selector": "app=does-not-exist",
                    "container_name": "nginx",
                    "count": 1,
                    "action": 9,
                    "expected_recovery_time": 5,                   
                }
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as temp_file:
            
            yaml.dump(scenario_data, temp_file)
            mock_telemetry = MagicMock()
            mock_lib_telemetry = MagicMock()
            
            result = self.plugin.run(
                "test-run",
                temp_file.name,
                mock_lib_telemetry,
                mock_telemetry,
            )
        
        self.assertEqual(result, 0)
        mock_future.result.assert_called_once()

    @patch.object(
        ContainerScenarioPlugin,
        "start_monitoring"
    )
    @patch.object(
        ContainerScenarioPlugin,
        "container_killing_in_pod"
    )

    def test_continue_execution_after_skipped_scenario(
        self,
        mock_container_killing,
        mock_start_monitoring,
    ):
        """
        Test execution continues when one scenario skips
        and following scenario succeeds
        """
        mock_container_killing.side_effect = [
            None,
            True,
        ]
        mock_future = MagicMock()
        mock_snapshot = MagicMock()
        mock_result = MagicMock()
        
        mock_result.unrecovered = []
        mock_snapshot.get_pods_status.return_value = (
            mock_result
        )
        mock_future.result.return_value = mock_snapshot
        mock_start_monitoring.return_value = mock_future
        
        scenario_data = {
            "scenarios": [
                {
                    "namespace": "default",
                    "label_selector": "app=missing",
                    "container_name": "nginx",
                    "count": 1,
                    "action": 9,
                    "expected_recovery_time": 5,   
                },
                {
                    "namespace": "default",
                    "label_selector": "app=nginx",
                    "container_name": "nginx",
                    "count": 1,
                    "action": 9,
                    "expected_recovery_time": 5,                      
                },
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as temp_file:
            
            yaml.dump(scenario_data, temp_file)
            mock_telemetry = MagicMock()
            mock_lib_telemetry = MagicMock()
            
            result = self.plugin.run(
                "test-run",
                temp_file.name,
                mock_lib_telemetry,
                mock_telemetry,
            )
        self.assertEqual(result, 0)
        self.assertEqual(
            mock_container_killing.call_count,
            2,
        )

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["container_scenarios"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
