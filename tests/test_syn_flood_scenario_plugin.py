#!/usr/bin/env python3

"""
Test suite for SynFloodScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_syn_flood_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest

from krkn.scenario_plugins.syn_flood.syn_flood_scenario_plugin import SynFloodScenarioPlugin


class TestSynFloodScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for SynFloodScenarioPlugin
        """
        self.plugin = SynFloodScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["syn_flood_scenarios"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
