#!/usr/bin/env python3
"""
Test suite for GpuHealthCheckPlugin.

Covers:
- Factory discovery, health check type, and config key
- Early-return guards (no kube client, no GPU nodes)
- Allocatable-based outage detection and recovery telemetry
- exit_on_failure return-code behavior
- Optional nvidia-smi validation
- Probe exception handling

Run:
    python -m unittest tests.test_gpu_health_check_plugin -v
"""

import os
import queue
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)

from krkn.health_checks import HealthCheckFactory

PLUGIN_MODULE = "krkn.health_checks.gpu_health_check_plugin"


class _CountingAllocatable:
    """Side effect that returns queued allocatable values while advancing the
    plugin's iteration counter so the monitoring loop terminates."""

    def __init__(self, plugin, values):
        self.plugin = plugin
        self.values = list(values)
        self.calls = 0

    def __call__(self, kubecli, node_name):
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        self.plugin.current_iterations += 1
        return value


class TestGpuHealthCheckPlugin(unittest.TestCase):
    def setUp(self):
        self.factory = HealthCheckFactory()
        if "gpu_health_check" not in self.factory.loaded_plugins:
            self.skipTest("GPU health check plugin not loaded")
        self.kubecli = object()  # opaque; all cluster calls are mocked
        self.queue = queue.Queue()

    def _plugin(self, iterations=1):
        return self.factory.create_plugin(
            "gpu_health_check", iterations=iterations, krkn_lib=self.kubecli
        )

    def _drain(self):
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return None

    # --- discovery / contract -------------------------------------------
    def test_factory_discovery(self):
        self.assertIn("gpu_health_check", self.factory.loaded_plugins)
        # config_key wiring is verified end-to-end in a single-factory run;
        # assert the plugin's own declaration here (loaded_plugins is a
        # class-level cache shared across factory instances in-process).
        self.assertEqual(self._plugin().get_config_key(), "gpu_health_checks")

    def test_types_and_config_key(self):
        plugin = self._plugin()
        self.assertEqual(plugin.get_health_check_types(), ["gpu_health_check"])
        self.assertEqual(plugin.get_config_key(), "gpu_health_checks")

    def test_increment_iterations(self):
        plugin = self._plugin(iterations=5)
        plugin.increment_iterations()
        self.assertEqual(plugin.current_iterations, 1)

    # --- guards ----------------------------------------------------------

    def test_no_kube_client_returns_early(self):
        plugin = self.factory.create_plugin(
            "gpu_health_check", iterations=1, krkn_lib=None
        )
        plugin.run_health_check({}, self.queue)
        self.assertIsNone(self._drain())

    def test_no_gpu_nodes_returns_early(self):
        plugin = self._plugin()
        with patch(f"{PLUGIN_MODULE}.discover_gpu_nodes", return_value=[]):
            plugin.run_health_check({}, self.queue)
        self.assertIsNone(self._drain())

    # --- monitoring behavior --------------------------------------------

    def test_healthy_throughout(self):
        plugin = self._plugin(iterations=2)
        with patch(
            f"{PLUGIN_MODULE}.discover_gpu_nodes",
            return_value=[{"name": "gpu-node", "gpu_count": 1}],
        ), patch(
            f"{PLUGIN_MODULE}.get_node_gpu_allocatable",
            side_effect=_CountingAllocatable(plugin, [1, 1]),
        ), patch(f"{PLUGIN_MODULE}.time.sleep"):
            plugin.run_health_check({"interval": 0}, self.queue)

        telemetry = self._drain()
        self.assertIsNotNone(telemetry)
        self.assertTrue(all(rec.status for rec in telemetry))
        self.assertEqual(plugin.get_return_value(), 0)

    def test_outage_detected_and_recovered(self):
        plugin = self._plugin(iterations=3)
        with patch(
            f"{PLUGIN_MODULE}.discover_gpu_nodes",
            return_value=[{"name": "gpu-node", "gpu_count": 1}],
        ), patch(
            f"{PLUGIN_MODULE}.get_node_gpu_allocatable",
            side_effect=_CountingAllocatable(plugin, [1, 0, 1]),
        ), patch(f"{PLUGIN_MODULE}.time.sleep"):
            plugin.run_health_check({"interval": 0}, self.queue)

        telemetry = self._drain()
        self.assertIsNotNone(telemetry)
        outages = [rec for rec in telemetry if not rec.status]
        self.assertEqual(len(outages), 1, "expected exactly one outage window")
        self.assertEqual(outages[0].url, "gpu://gpu-node")
        self.assertEqual(outages[0].status_code, "0")
        # exit_on_failure defaults to False -> run is not failed
        self.assertEqual(plugin.get_return_value(), 0)

    def test_exit_on_failure_sets_return_value(self):
        plugin = self._plugin(iterations=2)
        with patch(
            f"{PLUGIN_MODULE}.discover_gpu_nodes",
            return_value=[{"name": "gpu-node", "gpu_count": 1}],
        ), patch(
            f"{PLUGIN_MODULE}.get_node_gpu_allocatable",
            side_effect=_CountingAllocatable(plugin, [1, 0]),
        ), patch(f"{PLUGIN_MODULE}.time.sleep"):
            plugin.run_health_check(
                {"interval": 0, "exit_on_failure": True}, self.queue
            )

        self.assertEqual(plugin.get_return_value(), 3)

    def test_validate_gpu_health_invoked(self):
        plugin = self._plugin(iterations=1)
        with patch(
            f"{PLUGIN_MODULE}.discover_gpu_nodes",
            return_value=[{"name": "gpu-node", "gpu_count": 1}],
        ), patch(
            f"{PLUGIN_MODULE}.get_node_gpu_allocatable",
            side_effect=_CountingAllocatable(plugin, [1]),
        ), patch(
            f"{PLUGIN_MODULE}.validate_gpu_health_on_node", return_value=False
        ) as mock_smi, patch(f"{PLUGIN_MODULE}.time.sleep"):
            plugin.run_health_check(
                {"interval": 0, "validate_gpu_health": True}, self.queue
            )

        mock_smi.assert_called_with(
            self.kubecli, "gpu-node", namespace="nvidia-gpu-operator"
        )
        telemetry = self._drain()
        # allocatable healthy but nvidia-smi failed -> node reported unhealthy
        self.assertTrue(any(not rec.status for rec in telemetry))

    def test_probe_exception_marks_unhealthy(self):
        plugin = self._plugin(iterations=1)

        def boom(kubecli, node_name):
            plugin.current_iterations += 1
            raise RuntimeError("api error")

        with patch(
            f"{PLUGIN_MODULE}.discover_gpu_nodes",
            return_value=[{"name": "gpu-node", "gpu_count": 1}],
        ), patch(
            f"{PLUGIN_MODULE}.get_node_gpu_allocatable", side_effect=boom
        ), patch(f"{PLUGIN_MODULE}.time.sleep"):
            plugin.run_health_check({"interval": 0}, self.queue)

        telemetry = self._drain()
        self.assertIsNotNone(telemetry)
        self.assertTrue(any(rec.status_code == "error" for rec in telemetry))


if __name__ == "__main__":
    unittest.main()
