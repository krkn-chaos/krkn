#!/usr/bin/env python3

"""
Test suite for PodDisruptionScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_pod_disruption_scenario_plugin.py -v

Assisted By: Claude Code
"""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import yaml

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin import PodDisruptionScenarioPlugin
from krkn.scenario_plugins.pod_disruption.models.models import InputParams


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scenario_file(scenarios: list) -> str:
    """Write *scenarios* to a temp YAML file and return the path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(scenarios, f)
        return f.name


def _minimal_config(**overrides) -> dict:
    """Return the minimum valid config dict for InputParams, with optional overrides."""
    base = {
        "kill": 1,
        "timeout": 30,
        "duration": 5,
        "krkn_pod_recovery_time": 30,
        "label_selector": "app=test",
        "namespace_pattern": "default",
        "name_pattern": "",
        "node_label_selector": "",
        "node_names": [],
        "exclude_label": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Basic plugin tests
# ---------------------------------------------------------------------------

class TestPodDisruptionScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures for PodDisruptionScenarioPlugin."""
        self.plugin = PodDisruptionScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage."""
        self.plugin = None

    def test_get_scenario_types(self):
        """Test get_scenario_types returns correct scenario type."""
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pod_disruption_scenarios"])
        self.assertEqual(len(result), 1)

    def _make_scenario_config(self, namespace_pattern="default", **kwargs):
        """Helper to build a minimal scenario config dict."""
        config = {
            "namespace_pattern": namespace_pattern,
            "label_selector": "app=test",
            "name_pattern": "",
            "kill": 1,
            "duration": 1,
            "timeout": 180,
            "krkn_pod_recovery_time": 180,
            "exclude_label": None,
            "node_label_selector": None,
            "node_names": None,
        }
        config.update(kwargs)
        return config

    @patch("builtins.open", new_callable=mock_open)
    def test_run_skips_scenario_with_empty_namespace_pattern(self, mock_file):
        """
        When namespace_pattern is empty, the scenario should be skipped
        (continue) without launching a monitoring future.  If ALL entries are
        skipped run() returns 1 (no chaos was executed).
        """
        scenario_data = [{"config": self._make_scenario_config(namespace_pattern="")}]
        mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(scenario_data)

        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_scenario_telemetry = MagicMock()

        with patch("yaml.safe_load", return_value=scenario_data):
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

        # start_monitoring should NOT have been called
        mock_telemetry.get_lib_kubernetes.assert_not_called()
        # run() returns 1 — all scenarios were skipped, no chaos was executed
        self.assertEqual(result, 1)

    @patch("builtins.open", new_callable=mock_open)
    def test_run_skips_scenario_with_none_namespace_pattern(self, mock_file):
        """
        When namespace_pattern is None, the scenario should be skipped
        without launching a monitoring future.  If ALL entries are skipped
        run() returns 1.
        """
        scenario_data = [{"config": self._make_scenario_config(namespace_pattern=None)}]
        mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(scenario_data)

        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_scenario_telemetry = MagicMock()

        with patch("yaml.safe_load", return_value=scenario_data):
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

        mock_telemetry.get_lib_kubernetes.assert_not_called()
        self.assertEqual(result, 1)


# ---------------------------------------------------------------------------
# Execution-mode tests (serial / parallel)
# ---------------------------------------------------------------------------

class TestKillingPodsMode(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures for killing_pods mode tests."""
        self.plugin = PodDisruptionScenarioPlugin()
        self.kubecli = MagicMock(spec=KrknKubernetes)
        self.plugin.get_pods = MagicMock()
        self.plugin.wait_for_pods = MagicMock(return_value=0)

    def tearDown(self):
        """Clean up after each test to prevent state leakage."""
        self.plugin = None
        self.kubecli = None

    # --- InputParams.execution parsing ---

    def test_execution_defaults_to_serial(self):
        """execution defaults to 'serial' when not specified in config."""
        params = InputParams({"kill": 2})
        self.assertEqual(params.execution, "serial")

    def test_execution_serial_explicit(self):
        """execution is correctly parsed when explicitly set to 'serial'."""
        params = InputParams({"kill": 2, "execution": "serial"})
        self.assertEqual(params.execution, "serial")

    def test_execution_parallel_explicit(self):
        """execution is correctly parsed when explicitly set to 'parallel'."""
        params = InputParams({"kill": 2, "execution": "parallel"})
        self.assertEqual(params.execution, "parallel")

    def test_execution_invalid_raises_value_error(self):
        """execution raises ValueError on unknown values."""
        with self.assertRaises(ValueError) as context:
            InputParams({"kill": 2, "execution": "invalid_mode"})

        self.assertIn("Unknown execution 'invalid_mode'", str(context.exception))

    # --- killing_pods() behaviour ---

    def test_not_enough_pods_returns_error(self):
        """Returns 1 and never calls delete_pod when fewer pods exist than kill count."""
        config = InputParams({"kill": 3, "execution": "serial"})
        self.plugin.get_pods.return_value = [("pod1", "ns1"), ("pod2", "ns1")]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 1)
        self.kubecli.delete_pod.assert_not_called()

    def test_serial_mode_calls_delete_in_order(self):
        """Serial mode deletes all selected pods one at a time."""
        config = InputParams({"kill": 2, "execution": "serial"})
        self.plugin.get_pods.return_value = [("pod1", "ns1"), ("pod2", "ns1")]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 0)
        self.assertEqual(self.kubecli.delete_pod.call_count, 2)
        self.kubecli.delete_pod.assert_any_call("pod1", "ns1")
        self.kubecli.delete_pod.assert_any_call("pod2", "ns1")

    def test_parallel_mode_calls_delete_concurrently(self):
        """Parallel mode deletes all selected pods and calls delete_pod for each concurrently."""
        config = InputParams({"kill": 2, "execution": "parallel"})
        pods = [("pod1", "ns1"), ("pod2", "ns1")]
        self.plugin.get_pods.return_value = pods

        # Use a barrier to prove threads run concurrently. If they run serially,
        # the first thread will block forever waiting for the second.
        barrier = threading.Barrier(2, timeout=5)

        def side_effect(name, namespace):
            barrier.wait()

        self.kubecli.delete_pod.side_effect = side_effect

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 0)
        self.assertEqual(self.kubecli.delete_pod.call_count, 2)
        self.kubecli.delete_pod.assert_any_call("pod1", "ns1")
        self.kubecli.delete_pod.assert_any_call("pod2", "ns1")

    def test_parallel_mode_propagates_delete_exception(self):
        """Exceptions raised during parallel deletion bubble up correctly."""
        config = InputParams({"kill": 2, "execution": "parallel"})
        self.plugin.get_pods.return_value = [("pod1", "ns1"), ("pod2", "ns1")]

        def side_effect(name, namespace):
            if name == "pod1":
                raise RuntimeError("failed to delete")

        self.kubecli.delete_pod.side_effect = side_effect

        with self.assertRaises(Exception) as context:
            self.plugin.killing_pods(config, self.kubecli)

        self.assertIn("parallel pod deletion failed", str(context.exception))
        self.assertIn("failed to delete", str(context.exception))

    def test_excluded_pods_are_not_deleted_in_serial_mode(self):
        """Pods matched by exclude_label are skipped and never passed to delete_pod (serial)."""
        config = InputParams({"kill": 2, "execution": "serial", "exclude_label": "protected=true"})
        # get_pods is called twice: first for target pods, then for excluded pods
        self.plugin.get_pods.side_effect = [
            [("pod1", "ns1"), ("pod2", "ns1")],  # target pods
            [("pod1", "ns1")],                    # excluded pods
        ]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 0)
        # Only pod2 should be deleted; pod1 is excluded
        self.kubecli.delete_pod.assert_called_once_with("pod2", "ns1")

    def test_excluded_pods_are_not_deleted_in_parallel_mode(self):
        """Pods matched by exclude_label are skipped and never passed to delete_pod (parallel)."""
        config = InputParams({"kill": 2, "execution": "parallel", "exclude_label": "protected=true"})
        self.plugin.get_pods.side_effect = [
            [("pod1", "ns1"), ("pod2", "ns1")],  # target pods
            [("pod1", "ns1")],                    # excluded pods
        ]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 0)
        # Only pod2 should be deleted; pod1 is excluded
        self.kubecli.delete_pod.assert_called_once_with("pod2", "ns1")


# ---------------------------------------------------------------------------
# Namespace-pattern skip + executed_scenarios counter tests
# ---------------------------------------------------------------------------

class TestPodDisruptionRunAllNamespacesEmpty(unittest.TestCase):
    """run() must return 1 when every scenario entry has an empty namespace_pattern."""

    def test_run_skips_scenarios_with_empty_namespace_pattern(self):
        """If all scenarios have empty namespace_pattern, run() must return 1 (not 0)."""
        plugin = PodDisruptionScenarioPlugin()

        scenarios = [
            {"config": _minimal_config(namespace_pattern="")},
            {"config": _minimal_config(namespace_pattern=None)},
        ]
        scenario_file = _make_scenario_file(scenarios)
        mock_lib_telemetry = MagicMock()
        mock_scenario_telemetry = MagicMock(spec=ScenarioTelemetry)

        try:
            result = plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_file,
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )
        finally:
            Path(scenario_file).unlink(missing_ok=True)

        self.assertEqual(
            result,
            1,
            "run() must return 1 when all scenarios are skipped due to missing namespace_pattern",
        )

    def test_run_returns_0_when_at_least_one_scenario_executes(self):
        """run() must return 0 when at least one scenario executes successfully."""
        plugin = PodDisruptionScenarioPlugin()

        scenarios = [
            {"config": _minimal_config(namespace_pattern="")},
            {"config": _minimal_config(namespace_pattern="default")},
        ]
        scenario_file = _make_scenario_file(scenarios)
        mock_lib_telemetry = MagicMock()
        mock_scenario_telemetry = MagicMock(spec=ScenarioTelemetry)

        with patch.object(plugin, "start_monitoring") as mock_start_monitoring, \
             patch.object(plugin, "killing_pods", return_value=0):
            mock_future = MagicMock()
            mock_snapshot = MagicMock()
            mock_pods_status = MagicMock()
            mock_pods_status.unrecovered = []
            mock_snapshot.get_pods_status.return_value = mock_pods_status
            mock_future.result.return_value = mock_snapshot
            mock_start_monitoring.return_value = mock_future

            try:
                result = plugin.run(
                    run_uuid="test-uuid",
                    scenario=scenario_file,
                    lib_telemetry=mock_lib_telemetry,
                    scenario_telemetry=mock_scenario_telemetry,
                )
            finally:
                Path(scenario_file).unlink(missing_ok=True)

        self.assertEqual(result, 0)

    def test_run_returns_1_when_no_scenarios_in_file(self):
        """run() must return 1 when the scenario file contains an empty list."""
        plugin = PodDisruptionScenarioPlugin()
        scenario_file = _make_scenario_file([])
        mock_lib_telemetry = MagicMock()
        mock_scenario_telemetry = MagicMock(spec=ScenarioTelemetry)

        try:
            result = plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_file,
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )
        finally:
            Path(scenario_file).unlink(missing_ok=True)

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
