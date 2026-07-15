#!/usr/bin/env python3

"""
Test suite for PodDisruptionScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_pod_disruption_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.pod_disruption.models.models import InputParams
from krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin import PodDisruptionScenarioPlugin


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

    def test_killing_pods_with_exclude_label(self):
        config_data = {
            "name_pattern": ".*",
            "namespace_pattern": "test-namespace",
            "label_selector": "app=test",
            "exclude_label": "chaos=exclude",
            "kill": 2,
            "duration": 0,
            "timeout": 0,
            "krkn_pod_recovery_time": 0,
            "node_label_selector": None,
            "node_names": None
        }
        config = InputParams(config_data)

        # 5 normal pods, 2 of which will be excluded
        mock_pods = [
            ("pod-1", "test-namespace"),
            ("pod-2", "test-namespace"),
            ("pod-3", "test-namespace"),
            ("pod-4", "test-namespace"),
            ("pod-exclude-1", "test-namespace"),
        ]
        mock_exclude_pods = [
            ("pod-4", "test-namespace"),
            ("pod-exclude-1", "test-namespace"),
        ]

        def get_pods_side_effect(name_pattern, label_selector, namespace, kubecli, *args, **kwargs):
            if label_selector == "app=test":
                return list(mock_pods)
            if label_selector == "chaos=exclude":
                return list(mock_exclude_pods)
            return []

        self.plugin.get_pods = MagicMock(side_effect=get_pods_side_effect)
        self.plugin.wait_for_pods = MagicMock(return_value=0)
        mock_kubecli = MagicMock(spec=KrknKubernetes)

        result = self.plugin.killing_pods(config, mock_kubecli)

        self.assertEqual(result, 0)
        self.assertEqual(mock_kubecli.delete_pod.call_count, config.kill)
        self.plugin.wait_for_pods.assert_called_once()
        self.assertEqual(self.plugin.wait_for_pods.call_args[0][3], 5)

        for call in mock_kubecli.delete_pod.call_args_list:
            deleted_pod_name = call[0][0]
            self.assertNotIn(deleted_pod_name, ["pod-4", "pod-exclude-1"])

    def test_killing_pods_not_enough_pods(self):
        config_data = {
            "name_pattern": ".*",
            "namespace_pattern": "test-namespace",
            "label_selector": "app=test",
            "exclude_label": "chaos=exclude",
            "kill": 4, 
            "duration": 0,
            "timeout": 0,
            "krkn_pod_recovery_time": 0,
            "node_label_selector": None,
            "node_names": None
        }
        config = InputParams(config_data)

        # 5 pods total, but 2 excluded = 3 available (less than kill=4 requested)
        mock_pods = [
            ("pod-1", "test-namespace"),
            ("pod-2", "test-namespace"),
            ("pod-3", "test-namespace"),
            ("pod-4-exclude", "test-namespace"),
            ("pod-5-exclude", "test-namespace"),
        ]
        mock_exclude_pods = [
            ("pod-4-exclude", "test-namespace"),
            ("pod-5-exclude", "test-namespace"),
        ]

        def get_pods_side_effect(name_pattern, label_selector, namespace, kubecli, *args, **kwargs):
            if label_selector == "app=test":
                return list(mock_pods)
            if label_selector == "chaos=exclude":
                return list(mock_exclude_pods)
            return []

        self.plugin.get_pods = MagicMock(side_effect=get_pods_side_effect)
        mock_kubecli = MagicMock(spec=KrknKubernetes)

        result = self.plugin.killing_pods(config, mock_kubecli)

        self.assertEqual(result, 1)
        self.assertEqual(mock_kubecli.delete_pod.call_count, 0)


if __name__ == "__main__":
    unittest.main()
