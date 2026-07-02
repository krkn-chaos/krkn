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
import sys
import tempfile
import os
import unittest
from unittest.mock import patch, MagicMock

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin

# ---------------------------------------------------------------------------
# Minimal concrete plugin used across all tests in this module
# ---------------------------------------------------------------------------


class _SuccessPlugin(AbstractScenarioPlugin):
    """Plugin that always returns 0 (success)."""

    def run(self, run_uuid, scenario, lib_telemetry, scenario_telemetry) -> int:
        return 0

    def get_scenario_types(self) -> list[str]:
        return ["_success_plugin"]


class _FailurePlugin(AbstractScenarioPlugin):
    """Plugin that returns 1 (failure) without raising."""

    def run(self, run_uuid, scenario, lib_telemetry, scenario_telemetry) -> int:
        return 1

    def get_scenario_types(self) -> list[str]:
        return ["_failure_plugin"]


class _SysExitPlugin(AbstractScenarioPlugin):
    """Plugin that calls sys.exit(1) — reproduces the rollback bypass bug."""

    def run(self, run_uuid, scenario, lib_telemetry, scenario_telemetry) -> int:
        sys.exit(1)

    def get_scenario_types(self) -> list[str]:
        return ["_sysexit_plugin"]


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_krkn_config(wait_duration=0, events_backup=False):
    return {
        "tunings": {"wait_duration": wait_duration},
        "telemetry": {"events_backup": events_backup},
    }


def _make_telemetry():
    t = MagicMock(spec=KrknTelemetryOpenshift)
    t.set_parameters_base64.return_value = {}
    t.get_telemetry_request_id.return_value = "test-req-id"
    t.get_lib_kubernetes.return_value = MagicMock()
    return t


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestAbstractScenarioPluginRunScenarios(unittest.TestCase):
    """
    Unit tests for AbstractScenarioPlugin.run_scenarios().

    All external I/O is patched at the module level so tests are hermetic.
    """

    # Patch targets — all resolved relative to where the names are *used*,
    # not where they are defined.
    _PATCH_ROLLBACK = (
        "krkn.scenario_plugins.abstract_scenario_plugin.execute_rollback_version_files"
    )
    _PATCH_CLEANUP = (
        "krkn.scenario_plugins.abstract_scenario_plugin.cleanup_rollback_version_files"
    )
    _PATCH_CERBERUS = "krkn.scenario_plugins.abstract_scenario_plugin.cerberus"
    _PATCH_UTILS = "krkn.scenario_plugins.abstract_scenario_plugin.utils"
    _PATCH_SIGNAL = "krkn.scenario_plugins.abstract_scenario_plugin.signal_handler"

    def _run(self, plugin, scenario_file, config=None):
        """Run a single scenario file through plugin.run_scenarios() with all I/O mocked."""
        if config is None:
            config = _make_krkn_config()
        telemetry = _make_telemetry()

        with patch(self._PATCH_ROLLBACK) as mock_rollback, patch(
            self._PATCH_CLEANUP
        ) as mock_cleanup, patch(self._PATCH_CERBERUS), patch(self._PATCH_UTILS), patch(
            self._PATCH_SIGNAL
        ) as mock_signal:

            # signal_handler.signal_context is a context manager
            mock_signal.signal_context.return_value.__enter__ = MagicMock(
                return_value=None
            )
            mock_signal.signal_context.return_value.__exit__ = MagicMock(
                return_value=False
            )

            failed, telemetries = plugin.run_scenarios(
                "run-uuid-test", [scenario_file], config, telemetry
            )

        return failed, telemetries, mock_rollback, mock_cleanup

    # ------------------------------------------------------------------
    # Test: sys.exit(1) inside run() must NOT bypass rollback (regression)
    # ------------------------------------------------------------------

    def test_sysexit_triggers_rollback_not_cleanup(self):
        """
        Regression test: sys.exit(1) inside a plugin's run() must be intercepted
        at the base class level so that execute_rollback_version_files() is called
        and cleanup_rollback_version_files() is NOT called.

        This test FAILS on the unfixed code because SystemExit escapes the
        `except Exception` handler in run_scenarios(), preventing rollback.
        """
        plugin = _SysExitPlugin("_sysexit_plugin")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("test: true\n")
            scenario_file = f.name

        try:
            failed, telemetries, mock_rollback, mock_cleanup = self._run(
                plugin, scenario_file
            )
        finally:
            os.unlink(scenario_file)

        # Rollback MUST have been invoked
        mock_rollback.assert_called_once()

        # Cleanup (success path) MUST NOT have been invoked
        mock_cleanup.assert_not_called()

        # Scenario MUST appear in the failed list
        self.assertIn(scenario_file, failed)

        # Telemetry exit_status MUST reflect failure
        self.assertEqual(len(telemetries), 1)
        self.assertEqual(telemetries[0].exit_status, 1)

    # ------------------------------------------------------------------
    # Regression guard: normal success path must be unaffected
    # ------------------------------------------------------------------

    def test_success_triggers_cleanup_not_rollback(self):
        """
        The existing success path must be unaffected by the fix:
        cleanup is called, rollback is not.
        """
        plugin = _SuccessPlugin("_success_plugin")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("test: true\n")
            scenario_file = f.name

        try:
            failed, telemetries, mock_rollback, mock_cleanup = self._run(
                plugin, scenario_file
            )
        finally:
            os.unlink(scenario_file)

        mock_cleanup.assert_called_once()
        mock_rollback.assert_not_called()
        self.assertNotIn(scenario_file, failed)
        self.assertEqual(telemetries[0].exit_status, 0)

    # ------------------------------------------------------------------
    # Regression guard: normal failure path (return 1) must be unaffected
    # ------------------------------------------------------------------

    def test_return_failure_triggers_rollback_not_cleanup(self):
        """
        The existing explicit-failure path must be unaffected:
        rollback is called, cleanup is not.
        """
        plugin = _FailurePlugin("_failure_plugin")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("test: true\n")
            scenario_file = f.name

        try:
            failed, telemetries, mock_rollback, mock_cleanup = self._run(
                plugin, scenario_file
            )
        finally:
            os.unlink(scenario_file)

        mock_rollback.assert_called_once()
        mock_cleanup.assert_not_called()
        self.assertIn(scenario_file, failed)
        self.assertEqual(telemetries[0].exit_status, 1)


if __name__ == "__main__":
    unittest.main()
