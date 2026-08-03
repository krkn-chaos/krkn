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

    # --- InputParams.kill_mode parsing ---

    def test_kill_mode_defaults_to_sequential(self):
        """kill_mode defaults to 'sequential' when not specified in config."""
        params = InputParams({"kill": 2})
        self.assertEqual(params.kill_mode, "sequential")

    def test_kill_mode_sequential_explicit(self):
        """kill_mode is correctly parsed when explicitly set to 'sequential'."""
        params = InputParams({"kill": 2, "kill_mode": "sequential"})
        self.assertEqual(params.kill_mode, "sequential")

    def test_kill_mode_parallel_explicit(self):
        """kill_mode is correctly parsed when explicitly set to 'parallel'."""
        params = InputParams({"kill": 2, "kill_mode": "parallel"})
        self.assertEqual(params.kill_mode, "parallel")

    def test_kill_mode_invalid_defaults_to_sequential(self):
        """kill_mode defaults to 'sequential' and logs warning on unknown values."""
        with self.assertLogs(level='WARNING') as cm:
            params = InputParams({"kill": 2, "kill_mode": "invalid_mode"})
        
        self.assertEqual(params.kill_mode, "sequential")
        self.assertTrue(any("Unknown kill_mode 'invalid_mode'" in log for log in cm.output))

    # --- killing_pods() behaviour ---

    def test_not_enough_pods_returns_error(self):
        """Returns 1 and never calls delete_pod when fewer pods exist than kill count."""
        config = InputParams({"kill": 3, "kill_mode": "sequential"})
        self.plugin.get_pods.return_value = [("pod1", "ns1"), ("pod2", "ns1")]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 1)
        self.kubecli.delete_pod.assert_not_called()

    def test_sequential_mode_calls_delete_in_order(self):
        """Sequential mode deletes all selected pods one at a time."""
        config = InputParams({"kill": 2, "kill_mode": "sequential"})
        self.plugin.get_pods.return_value = [("pod1", "ns1"), ("pod2", "ns1")]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 0)
        self.assertEqual(self.kubecli.delete_pod.call_count, 2)
        self.kubecli.delete_pod.assert_any_call("pod1", "ns1")
        self.kubecli.delete_pod.assert_any_call("pod2", "ns1")

    def test_parallel_mode_calls_delete_concurrently(self):
        """Parallel mode deletes all selected pods and calls delete_pod for each concurrently."""
        config = InputParams({"kill": 2, "kill_mode": "parallel"})
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
        config = InputParams({"kill": 2, "kill_mode": "parallel"})
        self.plugin.get_pods.return_value = [("pod1", "ns1"), ("pod2", "ns1")]

        def side_effect(name, namespace):
            if name == "pod1":
                raise RuntimeError("failed to delete")

        self.kubecli.delete_pod.side_effect = side_effect

        with self.assertRaises(Exception) as context:
            self.plugin.killing_pods(config, self.kubecli)

        self.assertIn("parallel pod deletion failed", str(context.exception))
        self.assertIn("failed to delete", str(context.exception))

    def test_excluded_pods_are_not_deleted_in_sequential_mode(self):
        """Pods matched by exclude_label are skipped and never passed to delete_pod (sequential)."""
        config = InputParams({"kill": 2, "kill_mode": "sequential", "exclude_label": "protected=true"})
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
        config = InputParams({"kill": 2, "kill_mode": "parallel", "exclude_label": "protected=true"})
        self.plugin.get_pods.side_effect = [
            [("pod1", "ns1"), ("pod2", "ns1")],  # target pods
            [("pod1", "ns1")],                    # excluded pods
        ]

        result = self.plugin.killing_pods(config, self.kubecli)

        self.assertEqual(result, 0)
        # Only pod2 should be deleted; pod1 is excluded
        self.kubecli.delete_pod.assert_called_once_with("pod2", "ns1")


if __name__ == "__main__":
    unittest.main()
