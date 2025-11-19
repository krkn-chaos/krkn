#!/usr/bin/env python3

"""
Test suite for PvcScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_pvc_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.pvc.pvc_scenario_plugin import PvcScenarioPlugin


class TestPvcScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for PvcScenarioPlugin
        """
        self.plugin = PvcScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pvc_scenarios"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
