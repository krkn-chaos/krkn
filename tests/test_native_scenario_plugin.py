#!/usr/bin/env python3

"""
Test suite for NativeScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_native_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.native.native_scenario_plugin import NativeScenarioPlugin


class TestNativeScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for NativeScenarioPlugin
        """
        self.plugin = NativeScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario types
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pod_network_scenarios", "ingress_node_scenarios"])
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
