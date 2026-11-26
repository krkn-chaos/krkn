#!/usr/bin/env python3

"""
Test suite for NetworkChaosNgScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_network_chaos_ng_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import patch

from krkn.scenario_plugins.network_chaos_ng.network_chaos_ng_scenario_plugin import NetworkChaosNgScenarioPlugin
from krkn.scenario_plugins.network_chaos_ng.modules import utils
from unittest.mock import MagicMock

from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosConfig,
    NetworkFilterConfig,
)
from krkn.scenario_plugins.network_chaos_ng.network_chaos_factory import (
    NetworkChaosFactory,
)


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

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils.logging.info")
    def test_log_info_non_parallel(self, mock_logging_info):
        """
        Test log_info function with parallel=False
        """
        utils.log_info("Test message")
        mock_logging_info.assert_called_once_with("Test message")

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils.logging.info")
    def test_log_info_parallel(self, mock_logging_info):
        """
        Test log_info function with parallel=True
        """
        utils.log_info("Test message", parallel=True, node_name="node1")
        mock_logging_info.assert_called_once_with("[node1]: Test message")

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils.logging.info")
    def test_log_info_parallel_missing_node_name(self, mock_logging_info):
        """
        Test log_info with parallel=True and missing node_name
        """
        utils.log_info("Test message", parallel=True)
        mock_logging_info.assert_called_once_with("[]: Test message")

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils.logging.error")
    def test_log_error_non_parallel(self, mock_logging_error):
        """
        Test log_error function with parallel=False
        """
        utils.log_error("Error message")
        mock_logging_error.assert_called_once_with("Error message")

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils.logging.error")
    def test_log_error_parallel(self, mock_logging_error):
        """
        Test log_error function with parallel=True
        """
        utils.log_error("Error message", parallel=True, node_name="node2")
        mock_logging_error.assert_called_once_with("[node2]: Error message")

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils.logging.error")
    def test_log_error_parallel_missing_node_name(self, mock_logging_error):
        """
        Test log_error with parallel=True and missing node_name
        """
        utils.log_error("Error message", parallel=True)
        mock_logging_error.assert_called_once_with("[]: Error message")

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils.logging.warning")
    def test_log_warning_non_parallel(self, mock_logging_warning):
        """
        Test log_warning function with parallel=False
        """
        utils.log_warning("Warning message")
        mock_logging_warning.assert_called_once_with("Warning message")

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils.logging.warning")
    def test_log_warning_parallel(self, mock_logging_warning):
        """
        Test log_warning function with parallel=True
        """
        utils.log_warning("Warning message", parallel=True, node_name="node3")
        mock_logging_warning.assert_called_once_with("[node3]: Warning message")

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils.logging.warning")
    def test_log_warning_parallel_missing_node_name(self, mock_logging_warning):
        """
        Test log_warning with parallel=True and missing node_name
        """
        utils.log_warning("Warning message", parallel=True)
        mock_logging_warning.assert_called_once_with("[]: Warning message")



class TestNetworkChaosConfigValidation(unittest.TestCase):
    """
    Tests that configs which cannot resolve a target are rejected at
    config-load time (issue #1710).
    """

    def _base_config(self, **overrides):
        config = {
            "id": "pod_network_filter",
            "image": "test-image",
            "wait_duration": 1,
            "test_duration": 30,
            "label_selector": "",
            "service_account": "",
            "taints": [],
            "namespace": "default",
            "instance_count": 1,
            "execution": "serial",
            "interfaces": [],
            "target": "some-pod",
            "ingress": False,
            "egress": True,
            "ports": [443],
            "protocols": ["tcp"],
        }
        config.update(overrides)
        return config

    def test_pod_scenario_without_target_or_selector_fails(self):
        errors = NetworkFilterConfig(
            **self._base_config(target="", label_selector="")
        ).validate()
        self.assertTrue(
            any(
                "pod_network_filter: no target specified" in e
                and "pod name" in e
                for e in errors
            ),
            f"errors={errors}",
        )

    def test_node_scenario_without_target_or_selector_fails(self):
        errors = NetworkFilterConfig(
            **self._base_config(
                id="node_network_filter", target="", label_selector=""
            )
        ).validate()
        self.assertTrue(
            any(
                "node_network_filter: no target specified" in e
                and "node name" in e
                for e in errors
            ),
            f"errors={errors}",
        )

    def test_pod_scenario_with_selector_only_passes(self):
        errors = NetworkFilterConfig(
            **self._base_config(target="", label_selector="app=myapp")
        ).validate()
        self.assertFalse(
            [e for e in errors if "no target specified" in e], f"errors={errors}"
        )

    def test_pod_scenario_without_namespace_fails(self):
        errors = NetworkFilterConfig(
            **self._base_config(target="", label_selector="app=myapp", namespace="")
        ).validate()
        self.assertTrue(
            any("namespace not specified" in e for e in errors), f"errors={errors}"
        )

    def test_vmi_scenario_does_not_require_target(self):
        config = {
            k: v
            for k, v in self._base_config(
                id="vmi_network_chaos",
                target="",
                label_selector="",
                latency="100ms",
                loss="0",
                bandwidth="1gbit",
            ).items()
            if k not in ("ports", "protocols")
        }
        errors = NetworkChaosConfig(**config).validate()
        self.assertFalse(
            [e for e in errors if "no target specified" in e], f"errors={errors}"
        )

    def test_factory_rejects_pod_scenario_without_target(self):
        with self.assertRaises(Exception) as context:
            NetworkChaosFactory.get_instance(
                self._base_config(target="", label_selector=""), MagicMock()
            )
        self.assertIn("config validation errors:", str(context.exception))
        self.assertIn(
            "pod_network_filter: no target specified", str(context.exception)
        )

if __name__ == "__main__":
    unittest.main()
