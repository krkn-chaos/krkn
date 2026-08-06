#!/usr/bin/env python3

"""
Test suite for PodDisruptionScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_pod_disruption_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch, mock_open
import yaml

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin import PodDisruptionScenarioPlugin
from krkn.scenario_plugins.pod_disruption.models.models import InputParams


class TestPodDisruptionScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for PodDisruptionScenarioPlugin
        """
        self.plugin = PodDisruptionScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pod_disruption_scenarios"])
        self.assertEqual(len(result), 1)

    def _make_scenario_config(self, namespace_pattern="default", **kwargs):
        """Helper to build a minimal scenario config dict."""
        config = {
            "namespace_pattern": namespace_pattern,
            "label_selector": "app=test",
            "name_pattern": "",
            "kill": 1,
            "duration": 1,
            "timeout": 180,
            "krkn_pod_recovery_time": 180,
            "exclude_label": None,
            "node_label_selector": None,
            "node_names": None,
        }
        config.update(kwargs)
        return config

    @patch("builtins.open", new_callable=mock_open)
    def test_run_skips_scenario_with_empty_namespace_pattern(self, mock_file):
        """
        When namespace_pattern is empty, the scenario should be skipped
        (continue) without launching a monitoring future, and run() should
        return 0 since no fatal error occurred.
        """
        scenario_data = [{"config": self._make_scenario_config(namespace_pattern="")}]
        mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(scenario_data)

        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_scenario_telemetry = MagicMock()

        with patch("yaml.safe_load", return_value=scenario_data):
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

        # start_monitoring should NOT have been called
        mock_telemetry.get_lib_kubernetes.assert_not_called()
        # run() returns 0 — bad scenario was skipped, not a fatal failure
        self.assertEqual(result, 0)

    @patch("builtins.open", new_callable=mock_open)
    def test_run_skips_scenario_with_none_namespace_pattern(self, mock_file):
        """
        When namespace_pattern is None, the scenario should be skipped
        without launching a monitoring future.
        """
        scenario_data = [{"config": self._make_scenario_config(namespace_pattern=None)}]
        mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(scenario_data)

        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_scenario_telemetry = MagicMock()

        with patch("yaml.safe_load", return_value=scenario_data):
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

        mock_telemetry.get_lib_kubernetes.assert_not_called()
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
