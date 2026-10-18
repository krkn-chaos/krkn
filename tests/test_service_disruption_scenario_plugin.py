#!/usr/bin/env python3

"""
Test suite for ServiceDisruptionScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_service_disruption_scenario_plugin.py -v

Assisted By: Claude Code
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.service_disruption.service_disruption_scenario_plugin import ServiceDisruptionScenarioPlugin


class TestServiceDisruptionScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ServiceDisruptionScenarioPlugin
        """
        self.plugin = ServiceDisruptionScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["service_disruption_scenarios"])
        self.assertEqual(len(result), 1)

    def _run_with(self, namespaces, delete_count=1, runs=1):
        scenario = {
            "scenarios": [
                {
                    "namespace": "test-ns",
                    "label_selector": "",
                    "delete_count": delete_count,
                    "runs": runs,
                    "sleep": 0,
                }
            ]
        }
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            yaml.dump(scenario, f)
        self.addCleanup(os.remove, path)

        lib_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.check_namespaces.return_value = namespaces
        lib_telemetry.get_lib_kubernetes.return_value = kubecli

        return self.plugin.run(
            run_uuid="test-uuid",
            scenario=path,
            lib_telemetry=lib_telemetry,
            scenario_telemetry=MagicMock(),
        )

    @patch("time.sleep")
    def test_run_deletes_objects_in_matching_namespace(self, _):
        """
        Test a successful run deletes objects in the matching namespace and returns 0
        """
        with patch.object(
            self.plugin, "delete_objects", return_value={}
        ) as mock_delete:
            result = self._run_with(["test-ns"])

        self.assertEqual(result, 0)
        mock_delete.assert_called_once()
        self.assertEqual(mock_delete.call_args[0][1], "test-ns")

    @patch("time.sleep")
    def test_run_logs_error_when_delete_fails(self, _):
        """
        Test a failed namespace delete is logged at ERROR with the namespace and the cause
        """
        with patch.object(
            self.plugin, "delete_objects", side_effect=Exception("forbidden")
        ):
            with self.assertLogs(level="ERROR") as logs:
                result = self._run_with(["test-ns"])

        self.assertEqual(result, 1)
        errors = "\n".join(logs.output)
        self.assertIn("test-ns", errors)
        self.assertIn("forbidden", errors)
        self.assertIn("exit code: 1", errors)

    @patch("time.sleep")
    def test_run_reports_delete_count_when_not_enough_namespaces(self, _):
        """
        Test the not-enough-namespaces error reports delete_count, not runs
        """
        with self.assertLogs(level="ERROR") as logs:
            result = self._run_with([], delete_count=2, runs=5)

        self.assertEqual(result, 1)
        self.assertIn("Couldn't delete 2 namespaces", logs.output[0])
        self.assertIn("exit code: 1", logs.output[0])
        self.assertNotIn("ù", logs.output[0])

if __name__ == "__main__":
    unittest.main()
