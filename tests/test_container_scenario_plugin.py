#!/usr/bin/env python3

"""
Test suite for ContainerScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_container_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch

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

    @staticmethod
    def _container_obj(name):
        """Build a mock container object exposing a ``name`` attribute."""
        container = MagicMock()
        container.name = name
        return container

    def _make_kubecli(self, pod_containers, namespace="test-ns"):
        """
        Build a mocked KrknKubernetes whose ``list_pods``/``get_pod_info``
        reflect the given ``{pod_name: [container_names]}`` mapping.
        """
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.list_pods.return_value = list(pod_containers.keys())

        def _get_pod_info(pod, ns):
            info = MagicMock()
            info.containers = [
                self._container_obj(name) for name in pod_containers[pod]
            ]
            return info

        kubecli.get_pod_info.side_effect = _get_pod_info
        kubecli.exec_cmd_in_pod.return_value = ""
        return kubecli

    @staticmethod
    def _scenario(container_name="", count=1, namespace="test-ns"):
        return {
            "name": "test-container-scenario",
            "namespace": namespace,
            "label_selector": "app=test",
            "container_name": container_name,
            "count": count,
            "action": 1,
        }

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["container_scenarios"])
        self.assertEqual(len(result), 1)

    def test_invalid_container_name_raises(self):
        """Invalid container name (absent in all pods) must raise RuntimeError."""
        kubecli = self._make_kubecli(
            {"pod1": ["c1", "c2"], "pod2": ["c1", "c2"]}
        )
        scenario = self._scenario(container_name="nonexistent", count=1)

        with patch.object(self.plugin, "retry_container_killing") as mock_kill:
            with self.assertRaises(RuntimeError) as ctx:
                self.plugin.container_killing_in_pod(scenario, kubecli)

        self.assertIn("nonexistent", str(ctx.exception))
        self.assertIn("not found in any matching pod", str(ctx.exception))
        mock_kill.assert_not_called()

    def test_valid_container_name_kills(self):
        """Valid container name present in all pods kills the right containers."""
        kubecli = self._make_kubecli(
            {
                "pod1": ["target", "sidecar"],
                "pod2": ["target", "sidecar"],
                "pod3": ["target", "sidecar"],
            }
        )
        scenario = self._scenario(container_name="target", count=2)

        with patch.object(self.plugin, "retry_container_killing") as mock_kill:
            killed = self.plugin.container_killing_in_pod(scenario, kubecli)

        self.assertEqual(len(killed), 2)
        self.assertEqual(mock_kill.call_count, 2)
        for entry in killed:
            self.assertEqual(entry[2], "target")

    def test_empty_container_name_kills_first(self):
        """Empty container name kills the first container of each selected pod."""
        kubecli = self._make_kubecli(
            {"pod1": ["c1", "c2"], "pod2": ["c1", "c2"]}
        )
        scenario = self._scenario(container_name="", count=2)

        with patch.object(self.plugin, "retry_container_killing") as mock_kill:
            killed = self.plugin.container_killing_in_pod(scenario, kubecli)

        self.assertEqual(len(killed), 2)
        self.assertEqual(mock_kill.call_count, 2)
        for entry in killed:
            self.assertEqual(entry[2], "c1")

    @patch("krkn.scenario_plugins.container.container_scenario_plugin.random.randint")
    def test_heterogeneous_pods_skips_non_matching(self, mock_randint):
        """Pods without the target container are skipped; kill still succeeds."""
        mock_randint.return_value = 0
        kubecli = self._make_kubecli(
            {
                "other1": ["c1"],
                "other2": ["c1"],
                "target-pod": ["target"],
            }
        )
        scenario = self._scenario(container_name="target", count=1)

        with patch.object(self.plugin, "retry_container_killing") as mock_kill:
            killed = self.plugin.container_killing_in_pod(scenario, kubecli)

        self.assertEqual(len(killed), 1)
        self.assertEqual(killed[0][0], "target-pod")
        self.assertEqual(killed[0][2], "target")
        self.assertEqual(mock_kill.call_count, 1)

    @patch("krkn.scenario_plugins.container.container_scenario_plugin.random.randint")
    def test_count_exceeds_pods_with_target_raises(self, mock_randint):
        """count higher than pods containing the target exhausts list and raises."""
        mock_randint.return_value = 0
        kubecli = self._make_kubecli(
            {
                "target-pod": ["target"],
                "other1": ["c1"],
                "other2": ["c1"],
            }
        )
        scenario = self._scenario(container_name="target", count=2)

        with patch.object(self.plugin, "retry_container_killing") as mock_kill:
            with self.assertRaises(RuntimeError):
                self.plugin.container_killing_in_pod(scenario, kubecli)

        self.assertEqual(mock_kill.call_count, 1)

    @patch("krkn.scenario_plugins.container.container_scenario_plugin.select_and_monitor_by_namespace_pattern_and_label")
    def test_start_monitoring_defaults_recovery_time_to_60(self, mock_monitor):
        """Missing expected_recovery_time waits 60 seconds, as documented."""
        scenario = {"namespace": "kube-system", "label_selector": "k8s-app=kube-dns"}

        self.plugin.start_monitoring(scenario, MagicMock())

        self.assertEqual(mock_monitor.call_args.kwargs["max_timeout"], 60)

    @patch("krkn.scenario_plugins.container.container_scenario_plugin.select_and_monitor_by_namespace_pattern_and_label")
    def test_start_monitoring_uses_expected_recovery_time(self, mock_monitor):
        """expected_recovery_time from the scenario is passed to the monitor."""
        scenario = {
            "namespace": "kube-system",
            "label_selector": "k8s-app=kube-dns",
            "expected_recovery_time": 120,
        }

        self.plugin.start_monitoring(scenario, MagicMock())

        self.assertEqual(mock_monitor.call_args.kwargs["max_timeout"], 120)


    @patch(
        "krkn.scenario_plugins.container.container_scenario_plugin."
        "select_and_monitor_by_namespace_pattern_and_label"
    )
    def test_start_monitoring_wildcard_namespace_matches_all(self, mock_monitor):
        """
        namespace "*" (documented as all namespaces) gives a valid pattern
        that matches any namespace
        """
        import re

        scenario = {
            "namespace": "*",
            "label_selector": "k8s-app=kube-dns",
            "expected_recovery_time": 60,
        }
        self.plugin.start_monitoring(scenario, MagicMock())

        pattern = mock_monitor.call_args.kwargs["namespace_pattern"]
        self.assertTrue(re.match(pattern, "kube-system"))
        self.assertTrue(re.match(pattern, "openshift-etcd"))

    @patch(
        "krkn.scenario_plugins.container.container_scenario_plugin."
        "select_and_monitor_by_namespace_pattern_and_label"
    )
    def test_start_monitoring_named_namespace_matches_exactly(self, mock_monitor):
        """
        A named namespace still matches only itself
        """
        import re

        scenario = {
            "namespace": "kube-system",
            "label_selector": "k8s-app=kube-dns",
            "expected_recovery_time": 60,
        }
        self.plugin.start_monitoring(scenario, MagicMock())

        pattern = mock_monitor.call_args.kwargs["namespace_pattern"]
        self.assertTrue(re.match(pattern, "kube-system"))
        self.assertFalse(re.match(pattern, "kube-system-2"))
        self.assertFalse(re.match(pattern, "kubexsystem"))

    @patch(
        "krkn.scenario_plugins.container.container_scenario_plugin."
        "select_and_monitor_by_namespace_pattern_and_label"
    )
    def test_start_monitoring_defaults_namespace_and_label_selector(self, mock_monitor):
        """
        Missing namespace and label_selector use the same defaults as
        container_killing_in_pod: all namespaces, no label filter
        """
        import re

        self.plugin.start_monitoring({"expected_recovery_time": 60}, MagicMock())

        kwargs = mock_monitor.call_args.kwargs
        self.assertTrue(re.match(kwargs["namespace_pattern"], "kube-system"))
        self.assertTrue(re.match(kwargs["namespace_pattern"], "default"))
        self.assertIsNone(kwargs["label_selector"])

    @patch(
        "krkn.scenario_plugins.container.container_scenario_plugin."
        "select_and_monitor_by_namespace_pattern_and_label"
    )
    def test_start_monitoring_dot_star_namespace_matches_all(self, mock_monitor):
        """
        namespace ".*" also means all namespaces
        """
        import re

        scenario = {"namespace": ".*", "expected_recovery_time": 60}
        self.plugin.start_monitoring(scenario, MagicMock())

        pattern = mock_monitor.call_args.kwargs["namespace_pattern"]
        self.assertTrue(re.match(pattern, "kube-system"))
        self.assertTrue(re.match(pattern, "default"))

    def _kill_all_namespaces(self, scenario):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.get_all_pods.return_value = [["pod1", "ns1"]]
        info = MagicMock()
        info.containers = [self._container_obj("c1")]
        kubecli.get_pod_info.return_value = info
        with patch.object(self.plugin, "retry_container_killing") as mock_kill:
            killed = self.plugin.container_killing_in_pod(scenario, kubecli)
        kubecli.get_all_pods.assert_called_once_with("app=test")
        kubecli.list_pods.assert_not_called()
        self.assertEqual(killed, [["pod1", "ns1", "c1"]])
        self.assertEqual(mock_kill.call_count, 1)

    def test_kill_dot_star_namespace_uses_all_pods(self):
        """namespace ".*" kills from all namespaces, like "*"."""
        self._kill_all_namespaces(self._scenario(namespace=".*"))

    def test_kill_star_namespace_uses_all_pods(self):
        """namespace "*" still kills from all namespaces."""
        self._kill_all_namespaces(self._scenario(namespace="*"))

    def test_kill_missing_namespace_uses_all_pods(self):
        """A scenario without namespace kills from all namespaces."""
        scenario = self._scenario()
        del scenario["namespace"]
        self._kill_all_namespaces(scenario)

    def test_kill_pod_names_with_dot_star_namespace_raises(self):
        """pod_names need a real namespace; ".*" is rejected like "*"."""
        scenario = self._scenario(namespace=".*")
        scenario["pod_names"] = ["pod1"]
        kubecli = MagicMock(spec=KrknKubernetes)
        with self.assertRaises(RuntimeError):
            self.plugin.container_killing_in_pod(scenario, kubecli)
        kubecli.get_pod_info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
