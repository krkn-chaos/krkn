#!/usr/bin/env python3

"""
Test suite for HogsScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_hogs_scenario_plugin.py -v

Assisted By: Claude Code
"""

import queue
import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.hogs.hogs_scenario_plugin import HogsScenarioPlugin


class TestHogsScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for HogsScenarioPlugin
        """
        self.plugin = HogsScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["hog_scenarios"])
        self.assertEqual(len(result), 1)

    def _stub_config(self):
        config = MagicMock()
        config.type.value = "cpu"
        return config

    def test_run_scenario_drains_all_exceptions(self):
        """Multiple worker failures are aggregated into one exception."""
        q = queue.Queue()
        q.put(Exception("node-a failed"))
        q.put(Exception("node-b failed"))
        with self.assertRaises(Exception) as ctx:
            self.plugin.run_scenario(self._stub_config(), MagicMock(), [], q)
        msg = str(ctx.exception)
        self.assertIn("2 node(s)", msg)
        self.assertIn("node-a failed", msg)
        self.assertIn("node-b failed", msg)
        self.assertTrue(q.empty())

    def test_run_scenario_single_exception(self):
        """A single worker failure propagates in the combined exception."""
        q = queue.Queue()
        q.put(Exception("only failure"))
        with self.assertRaises(Exception) as ctx:
            self.plugin.run_scenario(self._stub_config(), MagicMock(), [], q)
        self.assertIn("only failure", str(ctx.exception))

    def test_run_scenario_no_exception(self):
        """Empty exception queue means run_scenario does not raise."""
        q = queue.Queue()
        # should not raise when queue is empty
        self.plugin.run_scenario(self._stub_config(), MagicMock(), [], q)


if __name__ == "__main__":
    unittest.main()
