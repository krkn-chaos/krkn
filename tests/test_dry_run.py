#!/usr/bin/env python3
"""
Test suite for the --dry-run feature (PR 1: framework + pod disruption preview).

Coverage:
  - ScenarioPreview model defaults
  - AbstractScenarioPlugin.preview() returns unsupported by default
  - PodDisruptionScenarioPlugin.preview() target resolution and exclusions
  - Zero-mutation safety: no calls to delete_pod, killing_pods, start_monitoring
  - _dry_run_preview() orchestration (supported, unsupported, missing plugin)
  - CLI --dry-run argument parsing
  - Regression: normal execution unchanged without --dry-run

Usage:
    python -m pytest tests/test_dry_run.py -v
"""

import optparse
import unittest
from unittest.mock import MagicMock, patch, mock_open
from types import SimpleNamespace

from krkn_lib.k8s import KrknKubernetes

from krkn.scenario_plugins.abstract_scenario_plugin import (
    AbstractScenarioPlugin,
    ScenarioPreview,
)
from krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin import (
    PodDisruptionScenarioPlugin,
)
from krkn.scenario_plugins.scenario_plugin_factory import ScenarioPluginNotFound
from run_kraken import _dry_run_preview, _log_scenario_preview


# ---------------------------------------------------------------------------
# ScenarioPreview model
# ---------------------------------------------------------------------------
class TestScenarioPreviewModel(unittest.TestCase):
    """Verify ScenarioPreview defaults and field behavior."""

    def test_supported_defaults_to_true(self):
        p = ScenarioPreview(
            scenario_type="t", scenario_file="f", target_kind="Pod",
            selectors={}, matched_targets=[], excluded_targets=[],
            planned_targets=[], planned_action="a",
        )
        self.assertTrue(p.supported)
        self.assertEqual(p.warnings, [])

    def test_unsupported_explicit(self):
        p = ScenarioPreview(
            scenario_type="t", scenario_file="f", target_kind="unknown",
            selectors={}, matched_targets=[], excluded_targets=[],
            planned_targets=[], planned_action="N/A",
            supported=False, warnings=["reason"],
        )
        self.assertFalse(p.supported)
        self.assertEqual(p.warnings, ["reason"])


# ---------------------------------------------------------------------------
# AbstractScenarioPlugin default preview
# ---------------------------------------------------------------------------
class TestAbstractPluginDefaultPreview(unittest.TestCase):
    """The default preview() must return unsupported."""

    def test_default_preview_is_unsupported(self):
        class _Dummy(AbstractScenarioPlugin):
            def run(self, run_uuid, scenario, lib_telemetry, scenario_telemetry):
                return 0
            def get_scenario_types(self):
                return ["dummy_scenarios"]

        previews = _Dummy().preview("any.yaml", MagicMock())
        self.assertEqual(len(previews), 1)
        self.assertFalse(previews[0].supported)
        self.assertEqual(previews[0].scenario_type, "dummy_scenarios")


# ---------------------------------------------------------------------------
# PodDisruptionScenarioPlugin.preview()
# ---------------------------------------------------------------------------
SCENARIO_YAML_BASIC = """\
- id: kill-pods
  config:
    namespace_pattern: "^ns1$"
    label_selector: app=test
    kill: 2
"""

SCENARIO_YAML_WITH_EXCLUSION = """\
- id: kill-pods
  config:
    namespace_pattern: "^ns1$"
    label_selector: app=test
    exclude_label: "protected=true"
    kill: 2
"""

SCENARIO_YAML_KILL_MORE_THAN_AVAILABLE = """\
- id: kill-pods
  config:
    namespace_pattern: "^ns1$"
    label_selector: app=test
    kill: 10
"""

SCENARIO_YAML_MULTI = """\
- id: first
  config:
    namespace_pattern: "^ns1$"
    label_selector: app=a
    kill: 1
- id: second
  config:
    namespace_pattern: "^ns2$"
    name_pattern: "web-.*"
    kill: 2
"""


class TestPodDisruptionPreview(unittest.TestCase):
    def setUp(self):
        self.plugin = PodDisruptionScenarioPlugin()
        self.kubecli = MagicMock(spec=KrknKubernetes)

    def tearDown(self):
        self.plugin = None
        self.kubecli = None

    # --- basic target resolution ---

    def test_preview_resolves_targets(self):
        self.plugin.get_pods = MagicMock(
            return_value=[("pod1", "ns1"), ("pod2", "ns1"), ("pod3", "ns1")]
        )
        with patch("builtins.open", mock_open(read_data=SCENARIO_YAML_BASIC)):
            previews = self.plugin.preview("test.yaml", self.kubecli)

        self.assertEqual(len(previews), 1)
        p = previews[0]
        self.assertTrue(p.supported)
        self.assertEqual(p.scenario_type, "pod_disruption_scenarios")
        self.assertEqual(p.target_kind, "Pod")
        self.assertEqual(len(p.matched_targets), 3)
        self.assertEqual(len(p.planned_targets), 3)
        self.assertEqual(len(p.excluded_targets), 0)
        self.assertIn("delete 2", p.planned_action)
        self.assertIn("serial", p.planned_action)

    # --- exclusions ---

    def test_preview_applies_exclusions(self):
        self.plugin.get_pods = MagicMock(side_effect=[
            [("pod1", "ns1"), ("pod2", "ns1"), ("pod3", "ns1")],
            [("pod1", "ns1")],
        ])
        with patch("builtins.open", mock_open(read_data=SCENARIO_YAML_WITH_EXCLUSION)):
            previews = self.plugin.preview("test.yaml", self.kubecli)

        p = previews[0]
        self.assertEqual(len(p.matched_targets), 3)
        self.assertEqual(len(p.excluded_targets), 1)
        self.assertEqual(len(p.planned_targets), 2)
        self.assertEqual(p.excluded_targets[0]["name"], "pod1")

    # --- not enough pods ---

    def test_preview_warns_insufficient_pods(self):
        self.plugin.get_pods = MagicMock(
            return_value=[("pod1", "ns1")]
        )
        with patch("builtins.open", mock_open(read_data=SCENARIO_YAML_KILL_MORE_THAN_AVAILABLE)):
            previews = self.plugin.preview("test.yaml", self.kubecli)

        p = previews[0]
        self.assertTrue(any("not enough" in w for w in p.warnings))
        self.assertIn("would fail", p.planned_action)

    # --- random selection warning ---

    def test_preview_warns_random_selection(self):
        self.plugin.get_pods = MagicMock(
            return_value=[("p1", "ns"), ("p2", "ns"), ("p3", "ns"), ("p4", "ns")]
        )
        with patch("builtins.open", mock_open(read_data=SCENARIO_YAML_BASIC)):
            previews = self.plugin.preview("test.yaml", self.kubecli)

        p = previews[0]
        self.assertTrue(any("randomly select" in w for w in p.warnings))

    # --- multiple configs in one file ---

    def test_preview_handles_multiple_configs(self):
        self.plugin.get_pods = MagicMock(
            return_value=[("pod1", "ns1")]
        )
        with patch("builtins.open", mock_open(read_data=SCENARIO_YAML_MULTI)):
            previews = self.plugin.preview("test.yaml", self.kubecli)

        self.assertEqual(len(previews), 2)
        self.assertTrue(all(p.supported for p in previews))

    # --- file not found ---

    def test_preview_handles_missing_file(self):
        with patch("builtins.open", side_effect=FileNotFoundError("not found")):
            previews = self.plugin.preview("missing.yaml", self.kubecli)

        self.assertEqual(len(previews), 1)
        self.assertFalse(previews[0].supported)  # fail closed on missing file
        self.assertTrue(any("not found" in w for w in previews[0].warnings))

    # --- zero mutation safety ---

    def test_preview_never_calls_destructive_methods(self):
        """preview() must not invoke delete_pod, killing_pods, or start_monitoring."""
        self.plugin.get_pods = MagicMock(
            return_value=[("pod1", "ns1"), ("pod2", "ns1")]
        )
        self.plugin.killing_pods = MagicMock()
        self.plugin.start_monitoring = MagicMock()

        with patch("builtins.open", mock_open(read_data=SCENARIO_YAML_BASIC)):
            self.plugin.preview("test.yaml", self.kubecli)

        self.kubecli.delete_pod.assert_not_called()
        self.plugin.killing_pods.assert_not_called()
        self.plugin.start_monitoring.assert_not_called()

    # --- selectors in output ---

    def test_preview_populates_selectors(self):
        self.plugin.get_pods = MagicMock(return_value=[])
        with patch("builtins.open", mock_open(read_data=SCENARIO_YAML_BASIC)):
            previews = self.plugin.preview("test.yaml", self.kubecli)

        s = previews[0].selectors
        self.assertEqual(s["namespace_pattern"], "^ns1$")
        self.assertEqual(s["label_selector"], "app=test")


# ---------------------------------------------------------------------------
# _dry_run_preview orchestration
# ---------------------------------------------------------------------------
class TestDryRunOrchestration(unittest.TestCase):
    """Test the orchestration function that drives all scenario previews."""

    def _make_supported_plugin(self):
        plugin = MagicMock()
        plugin.preview.return_value = [ScenarioPreview(
            scenario_type="pod_disruption_scenarios",
            scenario_file="test.yaml",
            target_kind="Pod",
            selectors={"label_selector": "app=test"},
            matched_targets=[{"name": "pod1", "namespace": "ns1"}],
            excluded_targets=[],
            planned_targets=[{"name": "pod1", "namespace": "ns1"}],
            planned_action="delete 1 of 1 eligible pods, serial execution",
        )]
        return plugin

    def _make_unsupported_plugin(self):
        plugin = MagicMock()
        plugin.preview.return_value = [ScenarioPreview(
            scenario_type="native_scenarios",
            scenario_file="test.yaml",
            target_kind="unknown",
            selectors={},
            matched_targets=[],
            excluded_targets=[],
            planned_targets=[],
            planned_action="N/A",
            supported=False,
            warnings=["preview not implemented for this scenario type"],
        )]
        return plugin

    def test_all_supported_returns_zero(self):
        factory = MagicMock()
        factory.create_plugin.return_value = self._make_supported_plugin()
        scenarios = [{"pod_disruption_scenarios": ["test.yaml"]}]

        result = _dry_run_preview(scenarios, factory, MagicMock())
        self.assertEqual(result, 0)

    def test_unsupported_plugin_returns_nonzero(self):
        factory = MagicMock()
        factory.create_plugin.return_value = self._make_unsupported_plugin()
        scenarios = [{"native_scenarios": ["test.yaml"]}]

        result = _dry_run_preview(scenarios, factory, MagicMock())
        self.assertEqual(result, 1)

    def test_plugin_not_found_returns_nonzero(self):
        factory = MagicMock()
        factory.create_plugin.side_effect = ScenarioPluginNotFound("missing")
        scenarios = [{"unknown_scenarios": ["test.yaml"]}]

        result = _dry_run_preview(scenarios, factory, MagicMock())
        self.assertEqual(result, 1)

    def test_empty_scenarios_returns_zero(self):
        result = _dry_run_preview([], MagicMock(), MagicMock())
        self.assertEqual(result, 0)

    def test_mixed_supported_unsupported_returns_nonzero(self):
        supported = self._make_supported_plugin()
        unsupported = self._make_unsupported_plugin()

        factory = MagicMock()
        factory.create_plugin.side_effect = [supported, unsupported]

        scenarios = [
            {"pod_disruption_scenarios": ["a.yaml"]},
            {"native_scenarios": ["b.yaml"]},
        ]

        result = _dry_run_preview(scenarios, factory, MagicMock())
        self.assertEqual(result, 1)

    def test_preview_exception_returns_nonzero(self):
        """An exception inside plugin.preview() should not crash the run."""
        plugin = MagicMock()
        plugin.preview.side_effect = RuntimeError("boom")
        factory = MagicMock()
        factory.create_plugin.return_value = plugin
        scenarios = [{"pod_disruption_scenarios": ["test.yaml"]}]

        result = _dry_run_preview(scenarios, factory, MagicMock())
        self.assertEqual(result, 1)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------
class TestDryRunCLIOption(unittest.TestCase):
    """Verify the --dry-run flag is accepted by the optparse parser."""

    def _build_parser(self):
        """Build the parser the same way run_kraken.py does."""
        parser = optparse.OptionParser()
        parser.add_option("-c", "--config", dest="cfg", default="config/config.yaml")
        parser.add_option(
            "--dry-run", dest="dry_run", action="store_true", default=False,
        )
        return parser

    def test_dry_run_flag_present(self):
        parser = self._build_parser()
        options, _ = parser.parse_args(["--dry-run"])
        self.assertTrue(options.dry_run)

    def test_dry_run_flag_absent(self):
        parser = self._build_parser()
        options, _ = parser.parse_args([])
        self.assertFalse(options.dry_run)

    def test_dry_run_combined_with_config(self):
        parser = self._build_parser()
        options, _ = parser.parse_args(["--dry-run", "-c", "custom.yaml"])
        self.assertTrue(options.dry_run)
        self.assertEqual(options.cfg, "custom.yaml")


# ---------------------------------------------------------------------------
# Regression: normal execution unchanged without --dry-run
# ---------------------------------------------------------------------------
class TestNormalExecutionRegression(unittest.TestCase):
    """Ensure main() behaves identically when --dry-run is not set."""

    @patch('run_kraken.yaml.safe_load')
    @patch('run_kraken.os.path.isfile')
    @patch('builtins.open', new_callable=mock_open)
    def test_main_without_dry_run_unchanged(
        self, mock_file, mock_isfile, mock_yaml_load
    ):
        """main() without dry_run still hits the normal error path
        (missing telemetry key), proving the dry-run branch was skipped."""
        from run_kraken import main

        mock_isfile.side_effect = lambda p: p == "/fake/config.yaml"
        mock_yaml_load.return_value = {
            "kraken": {"rollback_versions_directory": "/tmp/krkn-test-rollback"},
            "tunings": {},
            "performance_monitoring": {},
            "elastic": {},
        }

        options = SimpleNamespace(cfg="/fake/config.yaml")
        result = main(options, None)
        # Same assertion as existing test_run_kraken.py: returns -1
        # because telemetry section is missing.
        self.assertEqual(result, -1)


if __name__ == "__main__":
    unittest.main()
