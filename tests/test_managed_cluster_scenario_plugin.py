#!/usr/bin/env python3

"""
Test suite for ManagedClusterScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_managed_cluster_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.managed_cluster.managed_cluster_scenario_plugin import ManagedClusterScenarioPlugin


class TestManagedClusterScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ManagedClusterScenarioPlugin
        """
        self.plugin = ManagedClusterScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["managedcluster_scenarios"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
