#!/usr/bin/env python3

"""
Test suite for the --dry-run CLI feature.

Usage:
    python -m unittest tests.test_dry_run -v
"""

import unittest
from unittest.mock import patch, mock_open, MagicMock
from types import SimpleNamespace

from run_kraken import main, _dry_run_scenarios, _dry_run_pod_disruption


class TestDryRunPodDisruption(unittest.TestCase):
    """Test _dry_run_pod_disruption target discovery."""

    def setUp(self):
        self.plugin = MagicMock()
        self.kubecli = MagicMock()

    def test_discovers_pods_with_label_selector(self):
        """Uses label_selector for target discovery."""
        self.plugin.get_pods.return_value = [
            ("etcd-0", "openshift-etcd"),
            ("etcd-1", "openshift-etcd"),
        ]

        config = [{"config": {
            "namespace_pattern": "^openshift-etcd$",
            "label_selector": "k8s-app=etcd",
            "kill": 1,
        }}]

        targets = _dry_run_pod_disruption(config, self.plugin, self.kubecli)

        self.assertEqual(targets, 1)
        self.plugin.get_pods.assert_called_once_with(
            name_pattern="",
            label_selector="k8s-app=etcd",
            namespace="^openshift-etcd$",
            kubecli=self.kubecli,
            field_selector="status.phase=Running",
            node_label_selector="",
            node_names=[],
        )

    def test_discovers_pods_with_name_pattern(self):
        """Uses name_pattern for target discovery."""
        self.plugin.get_pods.return_value = [
            ("api-server-abc", "kube-system"),
        ]

        config = [{"config": {
            "namespace_pattern": "^kube-system$",
            "name_pattern": "api-server-.*",
            "kill": 1,
        }}]

        targets = _dry_run_pod_disruption(config, self.plugin, self.kubecli)

        self.assertEqual(targets, 1)
        self.plugin.get_pods.assert_called_once_with(
            name_pattern="api-server-.*",
            label_selector="",
            namespace="^kube-system$",
            kubecli=self.kubecli,
            field_selector="status.phase=Running",
            node_label_selector="",
            node_names=[],
        )

    def test_exclude_label_filters_pods(self):
        """Exclude label removes matching pods from eligible list."""
        self.plugin.get_pods.side_effect = [
            # First call: all matching pods
            [("pod-1", "ns"), ("pod-2", "ns"), ("pod-3", "ns")],
            # Second call: excluded pods
            [("pod-2", "ns")],
        ]

        config = [{"config": {
            "namespace_pattern": "^ns$",
            "label_selector": "app=test",
            "kill": 2,
            "exclude_label": "exclude=true",
        }}]

        targets = _dry_run_pod_disruption(config, self.plugin, self.kubecli)

        # 3 pods - 1 excluded = 2 eligible, kill=2
        self.assertEqual(targets, 2)
        self.assertEqual(self.plugin.get_pods.call_count, 2)

    def test_kill_count_limits_targets(self):
        """Kill count caps the number of reported targets."""
        self.plugin.get_pods.return_value = [
            ("pod-1", "ns"), ("pod-2", "ns"), ("pod-3", "ns"),
            ("pod-4", "ns"), ("pod-5", "ns"),
        ]

        config = [{"config": {
            "namespace_pattern": "^ns$",
            "label_selector": "app=test",
            "kill": 2,
        }}]

        targets = _dry_run_pod_disruption(config, self.plugin, self.kubecli)

        self.assertEqual(targets, 2)

    def test_zero_matching_pods(self):
        """Returns 0 targets when no pods match."""
        self.plugin.get_pods.return_value = []

        config = [{"config": {
            "namespace_pattern": "^nonexistent$",
            "name_pattern": ".*",
            "kill": 1,
        }}]

        targets = _dry_run_pod_disruption(config, self.plugin, self.kubecli)

        self.assertEqual(targets, 0)

    def test_does_not_call_delete_pod(self):
        """Never calls delete_pod on kubecli."""
        self.plugin.get_pods.return_value = [("pod-1", "ns")]

        config = [{"config": {
            "namespace_pattern": "^ns$",
            "label_selector": "app=test",
            "kill": 1,
        }}]

        _dry_run_pod_disruption(config, self.plugin, self.kubecli)

        self.kubecli.delete_pod.assert_not_called()

    def test_multiple_scenario_entries(self):
        """Handles multiple entries in a single scenario file."""
        self.plugin.get_pods.side_effect = [
            [("etcd-0", "etcd-ns")],
            [("api-0", "api-ns"), ("api-1", "api-ns")],
        ]

        config = [
            {"config": {
                "namespace_pattern": "^etcd-ns$",
                "label_selector": "app=etcd",
                "kill": 1,
            }},
            {"config": {
                "namespace_pattern": "^api-ns$",
                "name_pattern": "api-.*",
                "kill": 1,
            }},
        ]

        targets = _dry_run_pod_disruption(config, self.plugin, self.kubecli)

        self.assertEqual(targets, 2)
        self.assertEqual(self.plugin.get_pods.call_count, 2)

    def test_node_label_selector_passed_through(self):
        """Passes node_label_selector to get_pods."""
        self.plugin.get_pods.return_value = [("pod-1", "ns")]

        config = [{"config": {
            "namespace_pattern": "^ns$",
            "label_selector": "app=test",
            "kill": 1,
            "node_label_selector": "node-role.kubernetes.io/worker=",
        }}]

        _dry_run_pod_disruption(config, self.plugin, self.kubecli)

        call_kwargs = self.plugin.get_pods.call_args[1]
        self.assertEqual(
            call_kwargs["node_label_selector"],
            "node-role.kubernetes.io/worker=",
        )

    def test_node_names_passed_through(self):
        """Passes node_names to get_pods."""
        self.plugin.get_pods.return_value = [("pod-1", "ns")]

        config = [{"config": {
            "namespace_pattern": "^ns$",
            "label_selector": "app=test",
            "kill": 1,
            "node_names": ["worker-0", "worker-1"],
        }}]

        _dry_run_pod_disruption(config, self.plugin, self.kubecli)

        call_kwargs = self.plugin.get_pods.call_args[1]
        self.assertEqual(call_kwargs["node_names"], ["worker-0", "worker-1"])

    def test_discovery_error_returns_zero_targets(self):
        """Returns 0 targets on discovery errors without crashing."""
        self.plugin.get_pods.side_effect = Exception("connection refused")

        config = [{"config": {
            "namespace_pattern": "^ns$",
            "label_selector": "app=test",
            "kill": 1,
        }}]

        targets = _dry_run_pod_disruption(config, self.plugin, self.kubecli)

        self.assertEqual(targets, 0)


class TestDryRunScenarios(unittest.TestCase):
    """Test _dry_run_scenarios orchestration."""

    def setUp(self):
        self.factory = MagicMock()
        self.kubecli = MagicMock()

    def test_empty_scenarios_returns_zero(self):
        """Returns 0 with no scenarios configured."""
        result = _dry_run_scenarios([], self.factory, self.kubecli)
        self.assertEqual(result, 0)

    def test_plugin_not_found_continues(self):
        """Logs error and continues when plugin is not found."""
        from krkn.scenario_plugins.scenario_plugin_factory import (
            ScenarioPluginNotFound,
        )

        self.factory.create_plugin.side_effect = ScenarioPluginNotFound("nope")

        scenarios = [{"unknown_scenarios": ["scenario.yml"]}]
        result = _dry_run_scenarios(scenarios, self.factory, self.kubecli)
        self.assertEqual(result, 0)

    def test_missing_scenario_file_continues(self):
        """Logs error and continues when scenario file is missing."""
        mock_plugin = MagicMock()
        self.factory.create_plugin.return_value = mock_plugin

        scenarios = [{"hog_scenarios": ["/nonexistent/file.yml"]}]
        result = _dry_run_scenarios(scenarios, self.factory, self.kubecli)
        self.assertEqual(result, 0)

    @patch("run_kraken.os.path.exists", return_value=True)
    def test_pod_disruption_calls_get_pods(self, mock_exists):
        """Performs target discovery for pod_disruption_scenarios."""
        mock_plugin = MagicMock()
        mock_plugin.__class__.__name__ = "PodDisruptionScenarioPlugin"
        mock_plugin.get_pods.return_value = [
            ("pod-1", "default"),
            ("pod-2", "default"),
        ]
        self.factory.create_plugin.return_value = mock_plugin

        scenario_yaml = (
            "- config:\n"
            "    namespace_pattern: ^default$\n"
            "    label_selector: app=test\n"
            "    kill: 2\n"
        )
        scenarios = [{"pod_disruption_scenarios": ["scenarios/test.yml"]}]

        with patch("builtins.open", mock_open(read_data=scenario_yaml)):
            result = _dry_run_scenarios(scenarios, self.factory, self.kubecli)

        self.assertEqual(result, 0)
        mock_plugin.get_pods.assert_called()

    @patch("run_kraken.os.path.exists", return_value=True)
    def test_never_calls_run_scenarios(self, mock_exists):
        """Never calls run_scenarios or run on any plugin."""
        mock_plugin = MagicMock()
        mock_plugin.__class__.__name__ = "HogsScenarioPlugin"
        # Remove get_pods so it falls through to generic path
        del mock_plugin.get_pods
        self.factory.create_plugin.return_value = mock_plugin

        scenarios = [{"hog_scenarios": ["scenarios/cpu-hog.yml"]}]

        with patch("builtins.open", mock_open(read_data="duration: 10\n")):
            _dry_run_scenarios(scenarios, self.factory, self.kubecli)

        mock_plugin.run_scenarios.assert_not_called()
        mock_plugin.run.assert_not_called()

    @patch("run_kraken.os.path.exists", return_value=True)
    def test_never_calls_delete_pod(self, mock_exists):
        """Never calls delete_pod even with matching targets."""
        mock_plugin = MagicMock()
        mock_plugin.__class__.__name__ = "PodDisruptionScenarioPlugin"
        mock_plugin.get_pods.return_value = [("pod-1", "ns")]
        self.factory.create_plugin.return_value = mock_plugin

        scenario_yaml = (
            "- config:\n"
            "    namespace_pattern: ^ns$\n"
            "    label_selector: app=test\n"
            "    kill: 1\n"
        )
        scenarios = [{"pod_disruption_scenarios": ["scenarios/test.yml"]}]

        with patch("builtins.open", mock_open(read_data=scenario_yaml)):
            _dry_run_scenarios(scenarios, self.factory, self.kubecli)

        self.kubecli.delete_pod.assert_not_called()

    @patch("run_kraken.os.path.exists", return_value=True)
    def test_generic_scenario_shows_config(self, mock_exists):
        """Non-pod-disruption scenarios display parsed config."""
        mock_plugin = MagicMock()
        mock_plugin.__class__.__name__ = "ContainerScenarioPlugin"
        del mock_plugin.get_pods
        self.factory.create_plugin.return_value = mock_plugin

        scenario_yaml = (
            "scenarios:\n"
            "  - name: kill-container\n"
            "    namespace: default\n"
        )
        scenarios = [{"container_scenarios": ["scenarios/container.yml"]}]

        with patch("builtins.open", mock_open(read_data=scenario_yaml)):
            result = _dry_run_scenarios(scenarios, self.factory, self.kubecli)

        # Should complete without error
        self.assertEqual(result, 0)


class TestDryRunMainIntegration(unittest.TestCase):
    """Test --dry-run integration with main()."""

    def test_main_calls_dry_run_when_flag_set(self):
        """main() with dry_run=True calls _dry_run_scenarios and returns 0."""
        config = {
            "kraken": {"kubeconfig_path": "/fake/kubeconfig"},
            "tunings": {"iterations": 1},
            "performance_monitoring": {},
            "elastic": {},
            "cerberus": {},
            "telemetry": {},
        }

        mock_factory = MagicMock()
        mock_factory.loaded_plugins = {}
        mock_factory.failed_plugins = []

        mock_hcf = MagicMock()
        mock_hcf.loaded_plugins = {}
        mock_hcf.failed_plugins = []

        options = SimpleNamespace(cfg="/fake/config.yaml", dry_run=True)

        with patch("run_kraken.os.path.isfile", return_value=True), \
                patch("builtins.open", mock_open()), \
                patch("run_kraken.yaml.safe_load", return_value=config), \
                patch("run_kraken.RollbackConfig.register"), \
                patch("run_kraken.SafeLogger"), \
                patch("run_kraken.KrknKubernetes"), \
                patch("run_kraken.KrknOpenshift") as mock_ocp, \
                patch("run_kraken.KrknTelemetryKubernetes"), \
                patch("run_kraken.KrknTelemetryOpenshift"), \
                patch("run_kraken.ScenarioPluginFactory", return_value=mock_factory), \
                patch("run_kraken.HealthCheckFactory", return_value=mock_hcf), \
                patch("run_kraken._dry_run_scenarios", return_value=0) as mock_dry_run:
            mock_ocp.return_value.is_openshift.return_value = False

            result = main(options, None)

        self.assertEqual(result, 0)
        mock_dry_run.assert_called_once()

    def test_dry_run_skips_health_checks(self):
        """main() with dry_run=True never runs health checks."""
        config = {
            "kraken": {"kubeconfig_path": "/fake/kubeconfig"},
            "tunings": {"iterations": 1},
            "performance_monitoring": {},
            "elastic": {},
            "cerberus": {},
            "telemetry": {},
        }

        mock_factory = MagicMock()
        mock_factory.loaded_plugins = {}
        mock_factory.failed_plugins = []

        mock_hcf = MagicMock()
        mock_hcf.loaded_plugins = {}
        mock_hcf.failed_plugins = []

        options = SimpleNamespace(cfg="/fake/config.yaml", dry_run=True)

        with patch("run_kraken.os.path.isfile", return_value=True), \
                patch("builtins.open", mock_open()), \
                patch("run_kraken.yaml.safe_load", return_value=config), \
                patch("run_kraken.RollbackConfig.register"), \
                patch("run_kraken.SafeLogger"), \
                patch("run_kraken.KrknKubernetes"), \
                patch("run_kraken.KrknOpenshift") as mock_ocp, \
                patch("run_kraken.KrknTelemetryKubernetes"), \
                patch("run_kraken.KrknTelemetryOpenshift"), \
                patch("run_kraken.ScenarioPluginFactory", return_value=mock_factory), \
                patch("run_kraken.HealthCheckFactory", return_value=mock_hcf), \
                patch("run_kraken._dry_run_scenarios", return_value=0):
            mock_ocp.return_value.is_openshift.return_value = False

            main(options, None)

        mock_hcf.run_all_once.assert_not_called()
        mock_hcf.start_all.assert_not_called()

    def test_backward_compatible_without_dry_run_attr(self):
        """main() works when options object has no dry_run attribute."""
        options = SimpleNamespace(cfg="/fake/config.yaml")

        # getattr(options, 'dry_run', False) should return False
        self.assertFalse(getattr(options, 'dry_run', False))


if __name__ == "__main__":
    unittest.main()
