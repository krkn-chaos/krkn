#!/usr/bin/env python3

"""
Test suite for NetworkChaosNgScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_network_chaos_ng_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.network_chaos_ng.network_chaos_ng_scenario_plugin import NetworkChaosNgScenarioPlugin
from krkn.scenario_plugins.network_chaos_ng.modules import utils


class TestNetworkChaosNgScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for NetworkChaosNgScenarioPlugin
        """
        self.plugin = NetworkChaosNgScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["network_chaos_ng_scenarios"])
        self.assertEqual(len(result), 1)


class TestNetworkChaosNgUtils(unittest.TestCase):

    @patch("logging.info")
    def test_log_info_non_parallel(self, mock_logging_info):
        """
        Test log_info function with parallel=False
        """
        utils.log_info("Test message")
        mock_logging_info.assert_called_once_with("Test message")

    @patch("logging.info")
    def test_log_info_parallel(self, mock_logging_info):
        """
        Test log_info function with parallel=True
        """
        utils.log_info("Test message", parallel=True, node_name="node1")
        mock_logging_info.assert_called_once_with("[node1]: Test message")

    @patch("logging.error")
    def test_log_error_non_parallel(self, mock_logging_error):
        """
        Test log_error function with parallel=False
        """
        utils.log_error("Error message")
        mock_logging_error.assert_called_once_with("Error message")

    @patch("logging.error")
    def test_log_error_parallel(self, mock_logging_error):
        """
        Test log_error function with parallel=True
        """
        utils.log_error("Error message", parallel=True, node_name="node2")
        mock_logging_error.assert_called_once_with("[node2]: Error message")

    @patch("logging.warning")
    def test_log_warning_non_parallel(self, mock_logging_warning):
        """
        Test log_warning function with parallel=False
        """
        utils.log_warning("Warning message")
        mock_logging_warning.assert_called_once_with("Warning message")

    @patch("logging.warning")
    def test_log_warning_parallel(self, mock_logging_warning):
        """
        Test log_warning function with parallel=True
        """
        utils.log_warning("Warning message", parallel=True, node_name="node3")
        mock_logging_warning.assert_called_once_with("[node3]: Warning message")


if __name__ == "__main__":
    unittest.main()
