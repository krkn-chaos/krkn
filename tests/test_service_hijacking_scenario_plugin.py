#!/usr/bin/env python3

"""
Test suite for ServiceHijackingScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_service_hijacking_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest

from krkn.scenario_plugins.service_hijacking.service_hijacking_scenario_plugin import ServiceHijackingScenarioPlugin


class TestServiceHijackingScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ServiceHijackingScenarioPlugin
        """
        self.plugin = ServiceHijackingScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["service_hijacking_scenarios"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
