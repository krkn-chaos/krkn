#!/usr/bin/env python3

"""
Test suite for PodDisruptionScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_pod_disruption_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin import PodDisruptionScenarioPlugin
from krkn.scenario_plugins.pod_disruption.models.models import InputParams


class TestPodDisruptionScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for PodDisruptionScenarioPlugin
        """
        self.plugin = PodDisruptionScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pod_disruption_scenarios"])
        self.assertEqual(len(result), 1)

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
        import threading
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

    # --- force deletion tests ---

    def test_force_defaults_to_false(self):
        """force defaults to False when not specified in config."""
        params = InputParams({"kill": 1})
        self.assertFalse(params.force)

    def test_force_invalid_type_raises_value_error(self):
        """force raises ValueError when given a non-boolean value like a string."""
        with self.assertRaises(ValueError) as context:
            InputParams({"kill": 1, "force": "false"})

        self.assertIn("Must be a boolean", str(context.exception))

    def test_serial_mode_force_passes_grace_period_zero(self):
        """Serial mode with force=True calls delete_pod with grace_period_seconds=0."""
        config = InputParams({"kill": 2, "execution": "serial", "force": True})
        self.plugin.get_pods.return_value = [("pod1", "ns1"), ("pod2", "ns1")]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 0)
        self.assertEqual(self.kubecli.delete_pod.call_count, 2)
        self.kubecli.delete_pod.assert_any_call("pod1", "ns1", grace_period_seconds=0)
        self.kubecli.delete_pod.assert_any_call("pod2", "ns1", grace_period_seconds=0)

    def test_serial_mode_graceful_no_grace_period_kwarg(self):
        """Serial mode with force=False (default) calls delete_pod without grace_period_seconds."""
        config = InputParams({"kill": 1, "execution": "serial", "force": False})
        self.plugin.get_pods.return_value = [("pod1", "ns1")]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 0)
        self.kubecli.delete_pod.assert_called_once_with("pod1", "ns1")

    def test_parallel_mode_force_passes_grace_period_zero(self):
        """Parallel mode with force=True calls delete_pod with grace_period_seconds=0."""
        config = InputParams({"kill": 2, "execution": "parallel", "force": True})
        self.plugin.get_pods.return_value = [("pod1", "ns1"), ("pod2", "ns1")]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 0)
        self.assertEqual(self.kubecli.delete_pod.call_count, 2)
        self.kubecli.delete_pod.assert_any_call("pod1", "ns1", grace_period_seconds=0)
        self.kubecli.delete_pod.assert_any_call("pod2", "ns1", grace_period_seconds=0)

    def test_parallel_mode_graceful_no_grace_period_kwarg(self):
        """Parallel mode with force=False (default) calls delete_pod without grace_period_seconds."""
        config = InputParams({"kill": 2, "execution": "parallel", "force": False})
        self.plugin.get_pods.return_value = [("pod1", "ns1"), ("pod2", "ns1")]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 0)
        self.assertEqual(self.kubecli.delete_pod.call_count, 2)
        self.kubecli.delete_pod.assert_any_call("pod1", "ns1")
        self.kubecli.delete_pod.assert_any_call("pod2", "ns1")


if __name__ == "__main__":
    unittest.main()
