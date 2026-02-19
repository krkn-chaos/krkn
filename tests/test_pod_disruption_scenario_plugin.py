#!/usr/bin/env python3

"""
Test suite for PodDisruptionScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_pod_disruption_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock
from unittest.mock import patch
from asyncio import Future

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry

from krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin import PodDisruptionScenarioPlugin
from types import SimpleNamespace


class TestPodDisruptionScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for PodDisruptionScenarioPlugin
        """
        self.plugin = PodDisruptionScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pod_disruption_scenarios"])
        self.assertEqual(len(result), 1)
    
    def test_start_monitoring_with_label_selector_uses_correct_monitor(self):
        kill = SimpleNamespace(namespace_pattern="ns-x", label_selector="app=foo", name_pattern=None, krkn_pod_recovery_time=5)
        lib_tel = MagicMock(spec=KrknTelemetryOpenshift)
        lib_kube = MagicMock()
        lib_kube.cli = "cli-obj"
        lib_tel.get_lib_kubernetes.return_value = lib_kube

        fut = Future()
        fut.set_result("snapshot")

        with patch("krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin.select_and_monitor_by_namespace_pattern_and_label", return_value=fut) as sel:
            ret = self.plugin.start_monitoring(kill, lib_tel)
            self.assertIs(ret, fut)
            sel.assert_called_once_with(namespace_pattern="ns-x", label_selector="app=foo", max_timeout=5, v1_client="cli-obj")

    def test_start_monitoring_with_name_pattern_uses_correct_monitor(self):
        kill = SimpleNamespace(namespace_pattern="ns-y", label_selector=None, name_pattern="pod-.*", krkn_pod_recovery_time=7)
        lib_tel = MagicMock(spec=KrknTelemetryOpenshift)
        lib_kube = MagicMock()
        lib_kube.cli = "cli-obj"
        lib_tel.get_lib_kubernetes.return_value = lib_kube

        fut = Future()
        fut.set_result("snapshot2")

        with patch("krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin.select_and_monitor_by_name_pattern_and_namespace_pattern", return_value=fut) as sel:
            ret = self.plugin.start_monitoring(kill, lib_tel)
            self.assertIs(ret, fut)
            sel.assert_called_once_with(pod_name_pattern="pod-.*", namespace_pattern="ns-y", max_timeout=7, v1_client="cli-obj")

    def test__select_pods_with_field_selector_combines_field_and_node(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = [("p1","ns")]

        pods = self.plugin._select_pods_with_field_selector(name_pattern=None, label_selector="app=test", namespace="ns", kubecli=kubecli, field_selector="status.phase=Running", node_name="node-a")

        kubecli.select_pods_by_namespace_pattern_and_label.assert_called_once_with(label_selector="app=test", namespace_pattern="ns", field_selector="status.phase=Running,spec.nodeName=node-a")
        self.assertEqual(pods, [("p1","ns")])

    def test__select_pods_with_field_selector_name_path(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_name_pattern_and_namespace_pattern.return_value = [("pX","ns")]

        pods = self.plugin._select_pods_with_field_selector(name_pattern="p.*", label_selector=None, namespace="ns", kubecli=kubecli, field_selector=None, node_name=None)

        kubecli.select_pods_by_name_pattern_and_namespace_pattern.assert_called_once_with(pod_name_pattern="p.*", namespace_pattern="ns", field_selector=None)
        self.assertEqual(pods, [("pX","ns")])

    def test_get_pods_with_label_selector(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        # simulate pods as tuples (name, namespace)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = [("pod-a", "ns-a"), ("pod-b", "ns-a")]

        pods = self.plugin.get_pods(name_pattern=None, label_selector="app=test", namespace="ns-a", kubecli=kubecli)

        self.assertEqual(len(pods), 2)
        kubecli.select_pods_by_namespace_pattern_and_label.assert_called_once()

    def test_get_pods_with_name_pattern(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_name_pattern_and_namespace_pattern.return_value = [("pod-x", "ns-x")]

        pods = self.plugin.get_pods(name_pattern="pod-.*", label_selector=None, namespace="ns-x", kubecli=kubecli)

        self.assertEqual(pods, [("pod-x", "ns-x")])
        kubecli.select_pods_by_name_pattern_and_namespace_pattern.assert_called_once()

    def test_get_pods_with_both_name_and_label_returns_empty(self):
        kubecli = MagicMock(spec=KrknKubernetes)

        pods = self.plugin.get_pods(name_pattern="p.*", label_selector="app=test", namespace="ns", kubecli=kubecli)

        self.assertEqual(pods, [])

    def test_get_pods_with_no_selector_returns_empty(self):
        kubecli = MagicMock(spec=KrknKubernetes)

        pods = self.plugin.get_pods(name_pattern=None, label_selector=None, namespace="ns", kubecli=kubecli)

        self.assertEqual(pods, [])

    def test_get_pods_with_node_names_combines_results(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        # return different results per node
        kubecli.select_pods_by_namespace_pattern_and_label.side_effect = [[("p1","ns")], [("p2","ns")]]

        pods = self.plugin.get_pods(name_pattern=None, label_selector="app=test", namespace="ns", kubecli=kubecli, node_names=["node-a","node-b"])

        self.assertEqual(len(pods), 2)

    def test_killing_pods_not_enough(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = [("p1","ns")]

        cfg = SimpleNamespace(
            namespace_pattern="ns",
            name_pattern=None,
            label_selector="app=test",
            exclude_label=None,
            kill=2,
            node_label_selector=None,
            node_names=None,
            duration=1,
            timeout=5
        )

        ret = self.plugin.killing_pods(cfg, kubecli)
        self.assertEqual(ret, 1)

    def test_killing_pods_deletes_requested_number(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = [("p1","ns"),("p2","ns")]

        cfg = SimpleNamespace(
            namespace_pattern="ns",
            name_pattern=None,
            label_selector="app=test",
            exclude_label=None,
            kill=1,
            node_label_selector=None,
            node_names=None,
            duration=0,
            timeout=1
        )

        # stub wait_for_pods to avoid blocking
        self.plugin.wait_for_pods = MagicMock(return_value=0)

        with patch("krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin.random.shuffle") as mock_shuffle:
            # don't actually shuffle, keep pods in original order
            mock_shuffle.side_effect = lambda x: None
            ret = self.plugin.killing_pods(cfg, kubecli)

        self.assertEqual(ret, 0)
        kubecli.delete_pod.assert_called_once_with("p1", "ns")

    def test_wait_for_pods_succeeds_when_pods_recover(self):
        # first call returns empty, second call returns the expected pod list
        self.plugin.get_pods = MagicMock(side_effect=[[], [("p1","ns")]])

        ret = self.plugin.wait_for_pods(label_selector=None, pod_name=None, namespace="ns", pod_count=1, duration=0, wait_timeout=5, kubecli=MagicMock(), node_label_selector=None, node_names=None)
        self.assertEqual(ret, 0)

    def test_wait_for_pods_times_out(self):
        # always returns empty so it will timeout quickly when wait_timeout is negative
        self.plugin.get_pods = MagicMock(return_value=[])

        ret = self.plugin.wait_for_pods(label_selector=None, pod_name=None, namespace="ns", pod_count=1, duration=0, wait_timeout=-1, kubecli=MagicMock(), node_label_selector=None, node_names=None)
        self.assertEqual(ret, 1)

    def test_start_monitoring_raises_exception_no_config(self):
        kill = SimpleNamespace(namespace_pattern=None, label_selector=None, name_pattern=None, krkn_pod_recovery_time=5)
        lib_tel = MagicMock(spec=KrknTelemetryOpenshift)

        with self.assertRaises(Exception):
            self.plugin.start_monitoring(kill, lib_tel)

    def test_get_pods_with_node_label_selector(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.list_nodes.return_value = ["node-a", "node-b"]
        kubecli.select_pods_by_namespace_pattern_and_label.side_effect = [[("p1","ns")], [("p2","ns")]]

        pods = self.plugin.get_pods(name_pattern=None, label_selector="app=test", namespace="ns", kubecli=kubecli, node_label_selector="node-type=worker")

        self.assertEqual(len(pods), 2)
        kubecli.list_nodes.assert_called_once_with(label_selector="node-type=worker")

    def test_get_pods_with_node_label_selector_no_nodes_found(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.list_nodes.return_value = []

        pods = self.plugin.get_pods(name_pattern=None, label_selector="app=test", namespace="ns", kubecli=kubecli, node_label_selector="node-type=worker")

        self.assertEqual(pods, [])

    def test_killing_pods_with_exclude_label(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.side_effect = [
            [("p1","ns"), ("p2","ns"), ("p3","ns")],  # pods to kill
            [("p3","ns")]  # excluded pods
        ]

        cfg = SimpleNamespace(
            namespace_pattern="ns",
            name_pattern=None,
            label_selector="app=test",
            exclude_label="reserved=true",
            kill=2,
            node_label_selector=None,
            node_names=None,
            duration=0,
            timeout=1
        )

        self.plugin.wait_for_pods = MagicMock(return_value=0)

        with patch("krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin.random.shuffle") as mock_shuffle:
            mock_shuffle.side_effect = lambda x: None
            ret = self.plugin.killing_pods(cfg, kubecli)

        self.assertEqual(ret, 0)
        # Should delete p1 and p2, but not p3 (excluded)
        self.assertEqual(kubecli.delete_pod.call_count, 2)

    def test_killing_pods_exception_handling(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.side_effect = RuntimeError("K8s error")

        cfg = SimpleNamespace(
            namespace_pattern="ns",
            name_pattern=None,
            label_selector="app=test",
            exclude_label=None,
            kill=1,
            node_label_selector=None,
            node_names=None,
            duration=0,
            timeout=1
        )

        with self.assertRaises(RuntimeError):
            self.plugin.killing_pods(cfg, kubecli)

    def test_run_success(self):
        yaml_content = """
- config:
    namespace_pattern: "default"
    name_pattern: "pod-.*"
    label_selector: null
    exclude_label: null
    kill: 1
    node_label_selector: null
    node_names: null
    duration: 0
    timeout: 1
    krkn_pod_recovery_time: 5
"""
        with patch("builtins.open", MagicMock()):
            with patch("yaml.full_load", return_value=[{"config": {
                "namespace_pattern": "default",
                "name_pattern": "pod-.*",
                "label_selector": None,
                "exclude_label": None,
                "kill": 1,
                "node_label_selector": None,
                "node_names": None,
                "duration": 0,
                "timeout": 1,
                "krkn_pod_recovery_time": 5
            }}]):
                with patch.object(self.plugin, "start_monitoring") as mock_start:
                    with patch.object(self.plugin, "killing_pods", return_value=0):
                        future = MagicMock()
                        snapshot = MagicMock()
                        pods_status = MagicMock()
                        pods_status.unrecovered = []
                        snapshot.get_pods_status.return_value = pods_status
                        future.result.return_value = snapshot
                        mock_start.return_value = future

                        lib_tel = MagicMock(spec=KrknTelemetryOpenshift)
                        scenario_tel = MagicMock(spec=ScenarioTelemetry)

                        ret = self.plugin.run("uuid", "scenario.yaml", {}, lib_tel, scenario_tel)
                        self.assertEqual(ret, 0)

    def test_run_killing_pods_fails(self):
        with patch("builtins.open", MagicMock()):
            with patch("yaml.full_load", return_value=[{"config": {
                "namespace_pattern": "default",
                "name_pattern": "pod-.*",
                "label_selector": None,
                "exclude_label": None,
                "kill": 1,
                "node_label_selector": None,
                "node_names": None,
                "duration": 0,
                "timeout": 1,
                "krkn_pod_recovery_time": 5
            }}]):
                with patch.object(self.plugin, "start_monitoring") as mock_start:
                    with patch.object(self.plugin, "killing_pods", return_value=1):
                        future = MagicMock()
                        snapshot = MagicMock()
                        pods_status = MagicMock()
                        pods_status.unrecovered = []
                        snapshot.get_pods_status.return_value = pods_status
                        future.result.return_value = snapshot
                        mock_start.return_value = future

                        lib_tel = MagicMock(spec=KrknTelemetryOpenshift)
                        scenario_tel = MagicMock(spec=ScenarioTelemetry)

                        ret = self.plugin.run("uuid", "scenario.yaml", {}, lib_tel, scenario_tel)
                        self.assertEqual(ret, 1)

    def test_run_killing_pods_config_error(self):
        with patch("builtins.open", MagicMock()):
            with patch("yaml.full_load", return_value=[{"config": {
                "namespace_pattern": "default",
                "name_pattern": "pod-.*",
                "label_selector": None,
                "exclude_label": None,
                "kill": 1,
                "node_label_selector": None,
                "node_names": None,
                "duration": 0,
                "timeout": 1,
                "krkn_pod_recovery_time": 5
            }}]):
                with patch.object(self.plugin, "start_monitoring") as mock_start:
                    with patch.object(self.plugin, "killing_pods", return_value=2):
                        future = MagicMock()
                        snapshot = MagicMock()
                        pods_status = MagicMock()
                        pods_status.unrecovered = []
                        snapshot.get_pods_status.return_value = pods_status
                        future.result.return_value = snapshot
                        future.done.return_value = True
                        mock_start.return_value = future

                        lib_tel = MagicMock(spec=KrknTelemetryOpenshift)
                        scenario_tel = MagicMock(spec=ScenarioTelemetry)

                        ret = self.plugin.run("uuid", "scenario.yaml", {}, lib_tel, scenario_tel)
                        self.assertEqual(ret, 1)
                        future.cancel.assert_called_once()

    def test_run_unrecovered_pods(self):
        with patch("builtins.open", MagicMock()):
            with patch("yaml.full_load", return_value=[{"config": {
                "namespace_pattern": "default",
                "name_pattern": "pod-.*",
                "label_selector": None,
                "exclude_label": None,
                "kill": 1,
                "node_label_selector": None,
                "node_names": None,
                "duration": 0,
                "timeout": 1,
                "krkn_pod_recovery_time": 5
            }}]):
                with patch.object(self.plugin, "start_monitoring") as mock_start:
                    with patch.object(self.plugin, "killing_pods", return_value=0):
                        future = MagicMock()
                        snapshot = MagicMock()
                        pods_status = MagicMock()
                        pods_status.unrecovered = ["pod1"]
                        snapshot.get_pods_status.return_value = pods_status
                        future.result.return_value = snapshot
                        mock_start.return_value = future

                        lib_tel = MagicMock(spec=KrknTelemetryOpenshift)
                        scenario_tel = MagicMock(spec=ScenarioTelemetry)

                        ret = self.plugin.run("uuid", "scenario.yaml", {}, lib_tel, scenario_tel)
                        self.assertEqual(ret, 1)

    def test_run_exception(self):
        with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
            lib_tel = MagicMock(spec=KrknTelemetryOpenshift)
            scenario_tel = MagicMock(spec=ScenarioTelemetry)

            ret = self.plugin.run("uuid", "nonexistent.yaml", {}, lib_tel, scenario_tel)
            self.assertEqual(ret, 1)

    def test_run_killing_pods_config_error_waits_and_sets_affected_pods(self):
        # This exercises the branch where killing_pods returns >1 and the plugin
        # cancels the monitoring future and retrieves a partial snapshot.
        with patch("builtins.open", MagicMock()):
            with patch("yaml.full_load", return_value=[{"config": {
                "namespace_pattern": "default",
                "name_pattern": "pod-.*",
                "label_selector": None,
                "exclude_label": None,
                "kill": 1,
                "node_label_selector": None,
                "node_names": None,
                "duration": 0,
                "timeout": 1,
                "krkn_pod_recovery_time": 5
            }}]):
                future = MagicMock()
                # First call to done() returns False so the code enters the wait loop,
                # then True to break the loop.
                future.done.side_effect = [False, True]
                snapshot = MagicMock()
                pods_status = MagicMock()
                pods_status.unrecovered = []
                snapshot.get_pods_status.return_value = pods_status
                future.result.return_value = snapshot

                with patch.object(self.plugin, "start_monitoring", return_value=future):
                    with patch.object(self.plugin, "killing_pods", return_value=2):
                        lib_tel = MagicMock(spec=KrknTelemetryOpenshift)
                        scenario_tel = MagicMock(spec=ScenarioTelemetry)

                        # patch time.sleep so the test doesn't actually wait
                        with patch("time.sleep", return_value=None):
                            ret = self.plugin.run("uuid", "scenario.yaml", {}, lib_tel, scenario_tel)

                        self.assertEqual(ret, 1)
                        future.cancel.assert_called_once()
                        # scenario_telemetry.affected_pods should be set to the snapshot result
                        self.assertIs(scenario_tel.affected_pods, pods_status)
    


if __name__ == "__main__":
    unittest.main()
