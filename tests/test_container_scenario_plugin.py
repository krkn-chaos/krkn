#!/usr/bin/env python3

"""
Test suite for ContainerScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_container_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.container.container_scenario_plugin import ContainerScenarioPlugin


class TestContainerScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ContainerScenarioPlugin
        """
        self.plugin = ContainerScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["container_scenarios"])
        self.assertEqual(len(result), 1)

    def test_distroless_container_bug(self):
        """
        Reproduce the distroless container bug and verify the fallback.
        """
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_kubecli.exec_cmd_in_pod.side_effect = Exception("impossible to determine the shell to run command")

        # Mock the fallback _kill_container_via_node directly on the plugin
        self.plugin._kill_container_via_node = MagicMock()

        self.plugin.retry_container_killing(
            kill_action="kill 15",
            podname="noobaa-db-pg-cluster-2",
            namespace="openshift-storage",
            container_name="postgres",
            kubecli=mock_kubecli
        )
        self.plugin._kill_container_via_node.assert_called_once_with(
            "noobaa-db-pg-cluster-2", "openshift-storage", "postgres", mock_kubecli
        )

if __name__ == "__main__":
    unittest.main()
