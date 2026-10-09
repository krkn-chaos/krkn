#!/usr/bin/env python3

"""
Test suite for HogsScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_hogs_scenario_plugin.py -v

Assisted By: Claude Code
"""

import os
import queue
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml

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

    def _targeted_nodes(self, scenario_overrides, listed_nodes,
                        schedulable_nodes=None, ready_nodes=None, expected_ret=0):
        """Run the plugin and return (lib_k8s mock, nodes passed to run_scenario or None)."""
        scenario = {"hog-type": "cpu", "duration": 10, **scenario_overrides}
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump(scenario, f)
        self.addCleanup(os.unlink, f.name)
        lib_telemetry = MagicMock()
        lib_k8s = lib_telemetry.get_lib_kubernetes.return_value
        lib_k8s.list_nodes.return_value = list(listed_nodes)
        lib_k8s.list_schedulable_nodes.return_value = list(
            listed_nodes if schedulable_nodes is None else schedulable_nodes
        )
        lib_k8s.list_ready_nodes.return_value = list(
            listed_nodes if ready_nodes is None else ready_nodes
        )
        with patch.object(self.plugin, "run_scenario") as run_scenario:
            ret = self.plugin.run(
                run_uuid="run-uuid",
                scenario=f.name,
                lib_telemetry=lib_telemetry,
                scenario_telemetry=MagicMock(),
            )
        self.assertEqual(ret, expected_ret)
        if not run_scenario.called:
            return lib_k8s, None
        return lib_k8s, run_scenario.call_args.args[2]

    def test_run_empty_selector_targets_one_schedulable_node(self):
        """Empty node-selector picks exactly one random node out of the schedulable ones."""
        lib_k8s, targeted = self._targeted_nodes(
            {"node-selector": ""},
            ["control-plane", "worker-1", "worker-2"],
            schedulable_nodes=["worker-1", "worker-2"],
        )
        lib_k8s.list_schedulable_nodes.assert_called_once_with()
        self.assertEqual(len(targeted), 1)
        self.assertIn(targeted[0], ["worker-1", "worker-2"])

    def test_run_malformed_selector_targets_one_schedulable_node(self):
        """Malformed node-selector logs a warning and falls back to one random schedulable node."""
        with self.assertLogs(level="WARNING") as logs:
            lib_k8s, targeted = self._targeted_nodes(
                {"node-selector": "worker"},
                ["control-plane", "worker-1", "worker-2"],
                schedulable_nodes=["worker-1", "worker-2"],
            )
        self.assertIn("not in right format", "\n".join(logs.output))
        lib_k8s.list_schedulable_nodes.assert_called_once_with()
        self.assertEqual(len(targeted), 1)
        self.assertIn(targeted[0], ["worker-1", "worker-2"])

    def test_run_empty_selector_with_taints_picks_from_all_nodes(self):
        """With tolerations configured, tainted nodes stay eligible for the random pick."""
        nodes = ["control-plane", "worker-1", "worker-2"]
        lib_k8s, targeted = self._targeted_nodes(
            {
                "node-selector": "",
                "taints": ["node-role.kubernetes.io/control-plane:NoSchedule"],
            },
            nodes,
            schedulable_nodes=["worker-1", "worker-2"],
        )
        lib_k8s.list_schedulable_nodes.assert_not_called()
        self.assertEqual(len(targeted), 1)
        self.assertIn(targeted[0], nodes)

    def test_run_empty_selector_no_schedulable_nodes_fails(self):
        """Empty node-selector with no schedulable nodes fails instead of deploying an unschedulable hog."""
        _, targeted = self._targeted_nodes(
            {"node-selector": ""},
            ["control-plane"],
            schedulable_nodes=[],
            expected_ret=1,
        )
        self.assertIsNone(targeted)

    def test_run_empty_selector_skips_not_ready_nodes(self):
        """Empty node-selector never picks a schedulable node that is NotReady."""
        _, targeted = self._targeted_nodes(
            {"node-selector": ""},
            ["control-plane", "worker-1", "worker-2"],
            schedulable_nodes=["worker-1", "worker-2"],
            ready_nodes=["control-plane", "worker-2"],
        )
        self.assertEqual(targeted, ["worker-2"])

    def test_run_valid_selector_targets_all_matching_nodes(self):
        """A valid node-selector targets every matching node."""
        nodes = ["worker-1", "worker-2", "worker-3"]
        lib_k8s, targeted = self._targeted_nodes(
            {"node-selector": "node-role.kubernetes.io/worker="}, nodes
        )
        lib_k8s.list_nodes.assert_called_once_with("node-role.kubernetes.io/worker=")
        lib_k8s.list_schedulable_nodes.assert_not_called()
        self.assertEqual(targeted, nodes)

    def test_run_empty_selector_honors_number_of_nodes(self):
        """Empty node-selector with number-of-nodes samples that many nodes."""
        nodes = ["node-1", "node-2", "node-3", "node-4", "node-5"]
        _, targeted = self._targeted_nodes(
            {"node-selector": "", "number-of-nodes": 2}, nodes
        )
        self.assertEqual(len(targeted), 2)
        self.assertEqual(len(set(targeted)), 2)
        self.assertTrue(set(targeted).issubset(nodes))

if __name__ == "__main__":
    unittest.main()
