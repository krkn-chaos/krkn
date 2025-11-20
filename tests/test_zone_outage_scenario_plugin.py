#!/usr/bin/env python3

"""
Test suite for ZoneOutageScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_zone_outage_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin import ZoneOutageScenarioPlugin


class TestZoneOutageScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ZoneOutageScenarioPlugin
        """
        self.plugin = ZoneOutageScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["zone_outages_scenarios"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
