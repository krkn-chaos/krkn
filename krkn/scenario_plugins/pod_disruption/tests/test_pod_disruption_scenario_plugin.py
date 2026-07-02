# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry

from krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin import (
    PodDisruptionScenarioPlugin,
)


def _make_scenario_file(scenarios: list) -> str:
    """Write *scenarios* to a temp YAML file and return the path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
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


class TestPodDisruptionRunAllNamespacesEmpty(unittest.TestCase):
    """run() must return 1 when every scenario entry has an empty namespace_pattern."""

    def test_run_skips_scenarios_with_empty_namespace_pattern(self):
        """If all scenarios have empty namespace_pattern, run() must return 1 (not 0)."""
        plugin = PodDisruptionScenarioPlugin()

        # Two entries, both missing namespace_pattern
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
            # First entry has empty namespace — will be skipped
            {"config": _minimal_config(namespace_pattern="")},
            # Second entry is valid — will be executed
            {"config": _minimal_config(namespace_pattern="default")},
        ]
        scenario_file = _make_scenario_file(scenarios)

        mock_lib_telemetry = MagicMock()
        mock_scenario_telemetry = MagicMock(spec=ScenarioTelemetry)

        # Patch the methods that require a live cluster
        with patch.object(
            plugin, "start_monitoring"
        ) as mock_start_monitoring, patch.object(
            plugin, "killing_pods", return_value=0
        ):
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

        self.assertEqual(result, 0, "run() must return 0 when at least one scenario executes successfully")

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

        self.assertEqual(result, 1, "run() must return 1 when scenario file is empty")


if __name__ == "__main__":
    unittest.main()
