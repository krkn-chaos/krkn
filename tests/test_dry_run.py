#!/usr/bin/env python3

"""
Test suite for `--dry-run` (krkn/dry_run.py, PodDisruptionScenarioPlugin.preview_targets
and the dry-run branch of run_kraken.main)

Usage:
    python -m unittest tests/test_dry_run.py -v
"""

import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import yaml
from krkn_lib.k8s import KrknKubernetes
from kubernetes.client.rest import ApiException

import run_kraken
from krkn.dry_run import run_dry_run
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin import (
    PodDisruptionScenarioPlugin,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CLUSTER = {
    "staging": ["nginx-1", "nginx-2", "redis-0"],
    "testing": ["nginx-3"],
    "kube-system": ["nginx-proxy", "etcd-0"],
}


def fake_kubecli(cluster=CLUSTER):
    """A real KrknKubernetes whose only cluster access is mocked list calls,
    so krkn-lib's own regex selection runs unchanged. Every write is a mock
    we can assert was never called."""
    kubecli = KrknKubernetes.__new__(KrknKubernetes)
    kubecli.list_namespaces = MagicMock(return_value=list(cluster))
    kubecli.list_pods = MagicMock(
        side_effect=lambda namespace, **_: list(cluster.get(namespace, []))
    )
    for write in ("delete_pod", "create_pod", "delete_namespace", "apply_yaml"):
        setattr(kubecli, write, MagicMock())
    return kubecli


class FakeFactory:
    def __init__(self, plugin):
        self.plugin = plugin

    def create_plugin(self, scenario_type):
        return self.plugin


class DryRunTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def scenario_file(self, *configs):
        path = os.path.join(self.tmp.name, f"scenario{len(os.listdir(self.tmp.name))}.yml")
        with open(path, "w") as f:
            yaml.safe_dump([{"id": "kill-pods", "config": c} for c in configs], f)
        return path

    def dry_run(self, path, kubecli=None, plugin=None):
        plugin = plugin or PodDisruptionScenarioPlugin()
        kubecli = kubecli or fake_kubecli()
        with self.assertLogs(level="INFO") as logs:
            rc = run_dry_run(
                [{"pod_disruption_scenarios": [path]}], kubecli, FakeFactory(plugin)
            )
        return rc, "\n".join(logs.output), kubecli


class TestPreviewTargets(DryRunTestCase):

    def targets(self, **config):
        path = self.scenario_file(config)
        return PodDisruptionScenarioPlugin().preview_targets(path, fake_kubecli())[0]

    def test_namespace_regex_matching(self):
        preview = self.targets(namespace_pattern="^(staging|testing)$", name_pattern=".*")
        self.assertCountEqual(
            preview["targets"],
            [("nginx-1", "staging"), ("nginx-2", "staging"), ("redis-0", "staging"), ("nginx-3", "testing")],
        )

    def test_name_regex_matching(self):
        preview = self.targets(namespace_pattern=".*", name_pattern="^nginx-[0-9]+$", kill=2)
        self.assertCountEqual(
            preview["targets"],
            [("nginx-1", "staging"), ("nginx-2", "staging"), ("nginx-3", "testing")],
        )
        self.assertEqual(preview["count"], 2)
        self.assertEqual(preview["issues"], [])
        self.assertEqual(preview["criteria"]["name_pattern"], "^nginx-[0-9]+$")

    def test_label_selector_and_exclude_label_use_production_selection(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.side_effect = [
            [("a", "staging"), ("b", "staging")],  # label_selector
            [("b", "staging")],  # exclude_label
        ]
        path = self.scenario_file(
            {"namespace_pattern": "^staging$", "label_selector": "app=web", "exclude_label": "keep=true"}
        )
        preview = PodDisruptionScenarioPlugin().preview_targets(path, kubecli)[0]
        self.assertEqual(preview["targets"], [("a", "staging")])
        kubecli.delete_pod.assert_not_called()

    def test_invalid_regex_raises_value_error(self):
        path = self.scenario_file({"namespace_pattern": "^(staging$", "name_pattern": ".*"})
        with self.assertRaisesRegex(ValueError, "invalid regex in namespace_pattern"):
            PodDisruptionScenarioPlugin().preview_targets(path, fake_kubecli())

    def test_non_string_pattern_raises_value_error(self):
        path = self.scenario_file({"namespace_pattern": 123, "name_pattern": ".*"})
        with self.assertRaisesRegex(ValueError, "invalid regex in namespace_pattern"):
            PodDisruptionScenarioPlugin().preview_targets(path, fake_kubecli())

    def test_entry_without_config_raises_value_error(self):
        path = os.path.join(self.tmp.name, "noconfig.yml")
        with open(path, "w") as f:
            yaml.safe_dump([{"id": "no-config"}], f)
        with self.assertRaisesRegex(ValueError, "'config' mapping"):
            PodDisruptionScenarioPlugin().preview_targets(path, fake_kubecli())

    def test_missing_namespace_pattern_raises_value_error(self):
        path = self.scenario_file({"name_pattern": ".*"})
        with self.assertRaisesRegex(ValueError, "namespace_pattern"):
            PodDisruptionScenarioPlugin().preview_targets(path, fake_kubecli())

    def test_not_enough_targets_is_reported(self):
        preview = self.targets(namespace_pattern="^testing$", name_pattern=".*", kill=3)
        self.assertEqual(preview["count"], 1)
        self.assertIn("real run would fail", preview["issues"][0])

    def test_base_plugin_preview_is_unsupported(self):
        with self.assertRaises(NotImplementedError):
            AbstractScenarioPlugin.preview_targets(MagicMock(), "x.yml", MagicMock())


class TestRunDryRun(DryRunTestCase):

    def test_reports_matched_targets_and_never_disrupts(self):
        path = self.scenario_file({"namespace_pattern": "^staging$", "name_pattern": "^nginx-"})
        plugin = PodDisruptionScenarioPlugin()
        with patch.object(plugin, "run") as run, \
                patch.object(plugin, "run_scenarios") as run_scenarios, \
                patch.object(plugin, "killing_pods") as killing_pods, \
                patch.object(plugin, "start_monitoring") as start_monitoring:
            rc, out, kubecli = self.dry_run(path, plugin=plugin)

        self.assertEqual(rc, 0)
        self.assertIn("DRY RUN", out)
        self.assertIn("Namespace: staging", out)
        self.assertIn("- nginx-1", out)
        self.assertIn("- nginx-2", out)
        self.assertNotIn("redis-0", out)
        self.assertIn("Total matched workloads: 2", out)
        self.assertIn("No chaos actions were executed.", out)
        for mock in (run, run_scenarios, killing_pods, start_monitoring, kubecli.delete_pod,
                     kubecli.create_pod, kubecli.delete_namespace, kubecli.apply_yaml):
            mock.assert_not_called()

    def test_no_matching_workloads(self):
        path = self.scenario_file({"namespace_pattern": "^prod$", "name_pattern": ".*"})
        rc, out, _ = self.dry_run(path)
        self.assertEqual(rc, 1)
        self.assertIn("No workloads matched", out)
        self.assertIn("Total matched workloads: 0", out)

    def test_invalid_regex_fails_explicitly(self):
        path = self.scenario_file({"namespace_pattern": ".*", "name_pattern": "nginx-[0-9"})
        rc, out, _ = self.dry_run(path)
        self.assertEqual(rc, 1)
        self.assertIn("invalid regex in name_pattern", out)

    def test_kubernetes_api_failure_fails_explicitly(self):
        kubecli = fake_kubecli()
        kubecli.list_namespaces.side_effect = ApiException(status=403, reason="Forbidden")
        path = self.scenario_file({"namespace_pattern": ".*", "name_pattern": ".*"})
        rc, out, _ = self.dry_run(path, kubecli=kubecli)
        self.assertEqual(rc, 1)
        self.assertIn("target discovery failed", out)
        self.assertIn("Forbidden", out)

    def test_unsupported_plugin_is_reported_not_executed(self):
        plugin = MagicMock()
        plugin.preview_targets.side_effect = NotImplementedError
        path = self.scenario_file({})
        rc, out, _ = self.dry_run(path, plugin=plugin)
        self.assertEqual(rc, 1)
        self.assertIn("UNSUPPORTED", out)
        plugin.run.assert_not_called()
        plugin.run_scenarios.assert_not_called()

    def test_missing_scenario_file(self):
        rc, out, _ = self.dry_run(os.path.join(self.tmp.name, "missing.yml"))
        self.assertEqual(rc, 1)
        self.assertIn("scenario file not found", out)

    def test_unknown_scenario_type(self):
        with self.assertLogs(level="INFO") as logs:
            rc = run_dry_run(
                [{"made_up_scenarios": ["x.yml"]}],
                fake_kubecli(),
                run_kraken.ScenarioPluginFactory(),
            )
        self.assertEqual(rc, 1)
        self.assertIn("no plugin found", "\n".join(logs.output))

    def test_malformed_scenario_entries_fail_cleanly(self):
        for entry in ({}, {"scenario_type": "pod_disruption_scenarios", "files": None}):
            with self.subTest(entry=entry), self.assertLogs(level="INFO") as logs:
                rc = run_dry_run([entry], fake_kubecli(), FakeFactory(PodDisruptionScenarioPlugin()))
            self.assertEqual(rc, 1)
            self.assertIn("ERROR", "\n".join(logs.output))

    def test_empty_scenario_list_is_skipped_like_real_run(self):
        factory = MagicMock()
        with self.assertLogs(level="INFO") as logs:
            rc = run_dry_run([{"made_up_scenarios": []}], fake_kubecli(), factory)
        self.assertEqual(rc, 0)
        factory.create_plugin.assert_not_called()
        self.assertIn("DRY RUN exit code: 0", "\n".join(logs.output))

    def test_exit_code_is_logged_on_failure(self):
        rc, out, _ = self.dry_run(os.path.join(self.tmp.name, "missing.yml"))
        self.assertEqual(rc, 1)
        self.assertIn("DRY RUN exit code: 1", out)


class TestMainDryRunBranch(unittest.TestCase):
    CONFIG = {
        "kraken": {
            "kubeconfig_path": "/fake/kubeconfig",
            "chaos_scenarios": [{"pod_disruption_scenarios": ["s.yml"]}],
            "publish_kraken_status": True,
        },
        "tunings": {"iterations": 1},
        "performance_monitoring": {"enable_alerts": True},
        "elastic": {},
        "cerberus": {},
        "telemetry": {},
        "triggers": {"some": "trigger"},
    }

    def run_main(self, options, command=None, kubecli_error=None):
        with patch("run_kraken.os.path.isfile", return_value=True), \
                patch("builtins.open", mock_open()), \
                patch("run_kraken.yaml.safe_load", return_value=self.CONFIG), \
                patch("run_kraken.RollbackConfig.register"), \
                patch("run_kraken.KrknKubernetes", side_effect=kubecli_error) as kube, \
                patch("run_kraken.KrknOpenshift") as ocp, \
                patch("run_kraken.server.start_server") as start_server, \
                patch("run_kraken.KrknTelemetryOpenshift") as telemetry, \
                patch("run_kraken.KrknPrometheus") as prometheus, \
                patch("run_kraken.TriggerManager") as triggers, \
                patch("run_kraken.HealthCheckFactory") as health, \
                patch("run_kraken.SafeLogger"), \
                patch("run_kraken.ScenarioPluginFactory") as factory, \
                patch("run_kraken.run_dry_run", return_value=0) as dry_run:
            rc = run_kraken.main(options, command)
        return rc, SimpleNamespace(
            kube=kube, ocp=ocp, start_server=start_server, telemetry=telemetry,
            prometheus=prometheus, triggers=triggers, health=health,
            factory=factory, dry_run=dry_run,
        )

    def test_dry_run_branches_out_before_side_effects(self):
        rc, m = self.run_main(SimpleNamespace(cfg="/fake/config.yaml", dry_run=True))
        self.assertEqual(rc, 0)
        m.dry_run.assert_called_once_with(
            self.CONFIG["kraken"]["chaos_scenarios"], m.kube.return_value, m.factory.return_value
        )
        for mock in (m.ocp, m.start_server, m.telemetry, m.prometheus, m.triggers, m.health):
            mock.assert_not_called()
        m.factory.return_value.create_plugin.assert_not_called()

    def test_dry_run_skips_rollback_and_history_window(self):
        options = SimpleNamespace(cfg="/fake/config.yaml", dry_run=True, past_resiliency_score="1h")
        with patch("run_kraken.os.path.isfile", return_value=True), \
                patch("builtins.open", mock_open()), \
                patch("run_kraken.yaml.safe_load", return_value=self.CONFIG), \
                patch("run_kraken.os.makedirs") as makedirs, \
                patch("run_kraken.RollbackConfig.register") as register, \
                patch("run_kraken.KrknKubernetes"), \
                patch("run_kraken.ScenarioPluginFactory"), \
                patch("run_kraken.run_dry_run", return_value=0) as dry_run:
            rc = run_kraken.main(options, None)
        self.assertEqual(rc, 0)
        register.assert_not_called()
        makedirs.assert_not_called()
        # The historical window must not empty the scenarios being previewed.
        self.assertEqual(dry_run.call_args.args[0], self.CONFIG["kraken"]["chaos_scenarios"])

    def test_dry_run_propagates_failure_exit_code(self):
        with patch("run_kraken.os.path.isfile", return_value=True), \
                patch("builtins.open", mock_open()), \
                patch("run_kraken.yaml.safe_load", return_value=self.CONFIG), \
                patch("run_kraken.RollbackConfig.register"), \
                patch("run_kraken.KrknKubernetes"), \
                patch("run_kraken.ScenarioPluginFactory"), \
                patch("run_kraken.run_dry_run", return_value=1):
            rc = run_kraken.main(SimpleNamespace(cfg="/fake/config.yaml", dry_run=True), None)
        self.assertEqual(rc, 1)

    def test_kubernetes_client_failure_does_not_fall_back(self):
        rc, m = self.run_main(
            SimpleNamespace(cfg="/fake/config.yaml", dry_run=True),
            kubecli_error=Exception("bad kubeconfig"),
        )
        self.assertEqual(rc, 1)
        m.dry_run.assert_not_called()
        m.ocp.assert_not_called()

    def test_dry_run_rejects_commands(self):
        rc, m = self.run_main(
            SimpleNamespace(cfg="/fake/config.yaml", dry_run=True), command="execute-rollback"
        )
        self.assertEqual(rc, -1)
        m.dry_run.assert_not_called()
        m.kube.assert_not_called()

    def test_without_flag_dry_run_is_not_used(self):
        # Options objects built without the attribute (older callers) keep the normal path.
        options = SimpleNamespace(cfg="/fake/config.yaml")
        with patch("run_kraken.os.path.isfile", return_value=True), \
                patch("builtins.open", mock_open()), \
                patch("run_kraken.yaml.safe_load", return_value={**self.CONFIG, "triggers": None}), \
                patch("run_kraken.RollbackConfig.register"), \
                patch("run_kraken.SafeLogger"), \
                patch("run_kraken.KrknKubernetes"), \
                patch("run_kraken.KrknOpenshift") as ocp, \
                patch("run_kraken.server.start_server"), \
                patch("run_kraken.KrknTelemetryKubernetes"), \
                patch("run_kraken.KrknTelemetryOpenshift"), \
                patch("run_kraken.KrknPrometheus"), \
                patch("run_kraken.ScenarioPluginFactory"), \
                patch("run_kraken.HealthCheckFactory") as health, \
                patch("run_kraken.collect_health_check_telemetry", return_value=([], [])), \
                patch("run_kraken.run_dry_run") as dry_run:
            ocp.return_value.is_openshift.return_value = False
            health.return_value.run_all_once.return_value = {
                "passed": False, "failures": [{}], "details": {}, "exit_on_failure": True,
            }
            rc = run_kraken.main(options, None)
        # Normal path reached the pre-chaos health check gate.
        self.assertEqual(rc, 4)
        dry_run.assert_not_called()


class TestCli(unittest.TestCase):
    def test_cli_accepts_dry_run(self):
        proc = subprocess.run(
            [sys.executable, "run_kraken.py", "--dry-run", "--config", "/nonexistent/config.yaml",
             "--output", os.devnull],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertNotIn("no such option", proc.stderr)
        self.assertIn("Cannot find a config", proc.stderr)
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
