import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, mock_open
from types import SimpleNamespace

import yaml
from krkn_lib.models.krkn import ChaosRunAlert

import run_kraken
from run_kraken import main


class TestRunKraken(unittest.TestCase):

    @patch('run_kraken.yaml.safe_load')
    @patch('run_kraken.os.path.isfile')
    @patch('builtins.open', new_callable=mock_open)
    def test_main_without_telemetry_config(self, mock_file, mock_isfile, mock_yaml_load):
        """
        Test that main() doesn't crash when config has no telemetry section
        """
        mock_isfile.side_effect = lambda p: p == "/fake/config.yaml"
        mock_yaml_load.return_value = {
            "kraken": {"rollback_versions_directory": "/tmp/krkn-test-rollback"},
            "tunings": {},
            "performance_monitoring": {},
            "elastic": {},
        }

        options = SimpleNamespace(cfg="/fake/config.yaml")
        result = main(options, None)

        self.assertEqual(result, -1)

    def test_blocking_pre_check_exits_before_starting_during_checkers(self):
        """A blocking pre-check must not start continuous health checkers."""
        config = {
            "kraken": {"kubeconfig_path": "/fake/kubeconfig"},
            "tunings": {"iterations": 1},
            "performance_monitoring": {},
            "elastic": {},
            "cerberus": {},
            "telemetry": {},
        }

        class FakeHealthCheckFactory:
            loaded_plugins = {}
            failed_plugins = []

            def __init__(self):
                self.start_all_called = False

            def run_all_once(self, *args, **kwargs):
                return {
                    "passed": False,
                    "failures": [{"message": "unhealthy"}],
                    "details": {},
                    "exit_on_failure": True,
                }

            def start_all(self, *args, **kwargs):
                self.start_all_called = True
                return []

        factory = FakeHealthCheckFactory()
        options = SimpleNamespace(cfg="/fake/config.yaml")

        with patch("run_kraken.os.path.isfile", return_value=True), \
                patch("builtins.open", mock_open()), \
                patch("run_kraken.yaml.safe_load", return_value=config), \
                patch("run_kraken.RollbackConfig.register"), \
                patch("run_kraken.SafeLogger"), \
                patch("run_kraken.KrknKubernetes"), \
                patch("run_kraken.KrknOpenshift") as mock_ocp, \
                patch("run_kraken.KrknTelemetryKubernetes"), \
                patch("run_kraken.KrknTelemetryOpenshift"), \
                patch("run_kraken.ScenarioPluginFactory"), \
                patch("run_kraken.HealthCheckFactory", return_value=factory), \
                patch("run_kraken.collect_health_check_telemetry", return_value=([], [])):
            mock_ocp.return_value.is_openshift.return_value = False
            result = main(options, None)

        self.assertEqual(result, 4)
        self.assertFalse(factory.start_all_called)


class TestCriticalAlertsStopTheRun(unittest.TestCase):
    """check_critical_alerts: krkn must stop injecting chaos once post chaos
    critical alerts fire, and exit with 2."""

    def _run(self, iterations, alert_on_calls, daemon_mode=False):
        """Run main() with mocked clients. ``alert_on_calls`` holds the
        critical_alerts() call numbers (1-based) that find a firing alert.
        Returns (exit code, number of scenario batches run). More than 5
        batches raises, so a run that never stops fails instead of hanging."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        kubeconfig = os.path.join(tmp.name, "kubeconfig")
        scenario = os.path.join(tmp.name, "scenario.yaml")
        for path in (kubeconfig, scenario):
            with open(path, "w") as f:
                f.write("x: 1\n")
        config = {
            "kraken": {
                "kubeconfig_path": kubeconfig,
                "report_formats": [],
                "rollback_versions_directory": os.path.join(tmp.name, "rollback"),
                "chaos_scenarios": [{"pod_disruption_scenarios": [scenario]}],
            },
            "tunings": {"wait_duration": 0, "iterations": iterations, "daemon_mode": daemon_mode},
            "performance_monitoring": {
                "prometheus_url": "http://prometheus",
                "check_critical_alerts": True,
            },
            "resiliency": {"resiliency_run_mode": "disabled"},
            "elastic": {},
            "cerberus": {"cerberus_enabled": False},
            "telemetry": {"enabled": False, "archive_path": tmp.name},
        }
        config_file = os.path.join(tmp.name, "config.yaml")
        with open(config_file, "w") as f:
            yaml.safe_dump(config, f)

        plugin = MagicMock()

        def run_scenarios(*args, **kwargs):
            if plugin.run_scenarios.call_count > 5:
                raise RuntimeError("chaos kept running after critical alerts")
            return [], []

        plugin.run_scenarios.side_effect = run_scenarios
        plugin_factory = MagicMock(loaded_plugins={}, failed_plugins=[])
        plugin_factory.create_plugin.return_value = plugin
        health_checks = MagicMock(loaded_plugins={}, failed_plugins=[])
        health_checks.run_all_once.return_value = {"passed": True, "failures": [], "details": {}}
        health_checks.start_all.return_value = []
        health_checks._should_run_at_timing.return_value = False
        openshift = MagicMock()
        openshift.is_openshift.return_value = False

        calls = {"n": 0}

        def critical_alerts(prometheus, summary, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] in alert_on_calls:
                summary.post_chaos_alerts.append(
                    ChaosRunAlert("KubeAPIDown", "firing", "default", "critical")
                )

        with patch.object(run_kraken, "error_collection_handler",
                          MagicMock(**{"get_error_logs.return_value": []}), create=True), \
             patch.object(run_kraken, "RollbackConfig"), \
             patch.object(run_kraken, "KrknKubernetes"), \
             patch.object(run_kraken, "KrknOpenshift", return_value=openshift), \
             patch.object(run_kraken, "KrknPrometheus"), \
             patch.object(run_kraken, "KrknTelemetryKubernetes"), \
             patch.object(run_kraken, "KrknTelemetryOpenshift"), \
             patch.object(run_kraken, "SafeLogger"), \
             patch.object(run_kraken, "ScenarioPluginFactory", return_value=plugin_factory), \
             patch.object(run_kraken, "HealthCheckFactory", return_value=health_checks), \
             patch.object(run_kraken, "collect_health_check_telemetry", return_value=([], [])), \
             patch.object(run_kraken, "build_chaos_report", return_value=""), \
             patch.object(run_kraken.prometheus_plugin, "critical_alerts", side_effect=critical_alerts):
            result = main(SimpleNamespace(cfg=config_file), None)
        return result, plugin.run_scenarios.call_count

    def test_no_more_iterations_after_critical_alerts(self):
        result, batches = self._run(iterations=3, alert_on_calls={1})
        self.assertEqual(result, 2)
        self.assertEqual(batches, 1)

    def test_daemon_mode_stops_after_critical_alerts(self):
        result, batches = self._run(iterations=1, alert_on_calls={1}, daemon_mode=True)
        self.assertEqual(result, 2)
        self.assertEqual(batches, 1)

    def test_runs_all_iterations_without_critical_alerts(self):
        result, batches = self._run(iterations=3, alert_on_calls=set())
        self.assertEqual(result, 0)
        self.assertEqual(batches, 3)


if __name__ == "__main__":
    unittest.main()
