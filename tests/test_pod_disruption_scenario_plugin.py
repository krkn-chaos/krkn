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


if __name__ == "__main__":
    unittest.main()
