#!/usr/bin/env python3

"""
Test suite for ApplicationOutageScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_application_outage_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.application_outage.application_outage_scenario_plugin import ApplicationOutageScenarioPlugin


class TestApplicationOutageScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ApplicationOutageScenarioPlugin
        """
        self.plugin = ApplicationOutageScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["application_outages_scenarios"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
