#!/usr/bin/env python3

"""
Test suite for ShutDownScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_shut_down_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest

from krkn.scenario_plugins.shut_down.shut_down_scenario_plugin import ShutDownScenarioPlugin


class TestShutDownScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ShutDownScenarioPlugin
        """
        self.plugin = ShutDownScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["cluster_shut_down_scenarios"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
