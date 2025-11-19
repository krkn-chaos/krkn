#!/usr/bin/env python3

"""
Test suite for NetworkChaosScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_network_chaos_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.network_chaos.network_chaos_scenario_plugin import NetworkChaosScenarioPlugin


class TestNetworkChaosScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for NetworkChaosScenarioPlugin
        """
        self.plugin = NetworkChaosScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["network_chaos_scenarios"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
