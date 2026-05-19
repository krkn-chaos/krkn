"""
Test suite for signal interruption behaviour in AbstractScenarioPlugin.run_scenarios()

Tests cover:
- STOP signal during inter-scenario sleep aborts remaining scenarios
- PAUSE signal during inter-scenario sleep waits until RUN is received
- STOP signal before a scenario starts aborts remaining scenarios
- PAUSE signal before a scenario starts waits until RUN is received
- No get_signal_fn (None) behaves like original unconditional sleep

Run individually with:
  python -m unittest tests/test_signal_interruption.py -v
"""

import unittest
from unittest.mock import patch, Mock, call
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift


class ConcretePlugin(AbstractScenarioPlugin):
    """Minimal concrete plugin for testing."""

    def __init__(self):
        super().__init__("test_scenario")

    def run(self, run_uuid, scenario, lib_telemetry, scenario_telemetry):
        return 0

    def get_scenario_types(self):
        return ["test_scenario"]


# ---------------------------------------------------------------------------
# Shared patch decorators used across most tests
# ---------------------------------------------------------------------------
_COMMON_PATCHES = [
    patch("krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status"),
    patch("krkn.scenario_plugins.abstract_scenario_plugin.cleanup_rollback_version_files"),
    patch("krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs"),
    patch("krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context"),
    patch("krkn.scenario_plugins.abstract_scenario_plugin.os.path.exists", return_value=True),
    patch("time.sleep"),
]


def _apply_patches(test_fn):
    """Apply all common patches to a test method."""
    for p in reversed(_COMMON_PATCHES):
        test_fn = p(test_fn)
    return test_fn


class TestSignalInterruption(unittest.TestCase):
    """Tests for STOP/PAUSE signal handling inside run_scenarios()."""

    def setUp(self):
        self.plugin = ConcretePlugin()
        self.mock_telemetry = Mock(spec=KrknTelemetryOpenshift)
        self.mock_telemetry.set_parameters_base64.return_value = {"test": "config"}
        self.mock_telemetry.get_telemetry_request_id.return_value = "test-request-id"
        self.mock_telemetry.get_lib_kubernetes.return_value = Mock()

        # wait_duration=3 so the polling loop runs 3 ticks — enough to test
        # signal detection without making tests slow.
        self.krkn_config = {
            "tunings": {"wait_duration": 3},
            "telemetry": {"events_backup": False},
        }

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    def _setup_signal_ctx(self, mock_signal_ctx):
        mock_signal_ctx.return_value.__enter__ = Mock()
        mock_signal_ctx.return_value.__exit__ = Mock(return_value=False)

    # ------------------------------------------------------------------
    # STOP during inter-scenario sleep
    # ------------------------------------------------------------------
    @_apply_patches
    def test_stop_during_sleep_aborts_remaining_scenarios(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """STOP received on the first tick of the sleep loop aborts the batch."""
        self._setup_signal_ctx(mock_signal_ctx)

        # Signal sequence: first scenario runs fine, then STOP arrives on the
        # very first tick of the inter-scenario wait.
        signals = iter(["STOP"])
        get_signal_fn = lambda: next(signals, "STOP")

        scenarios_list = ["scenario1.yaml", "scenario2.yaml", "scenario3.yaml"]
        failed, telemetries = self.plugin.run_scenarios(
            "test-uuid", scenarios_list, self.krkn_config,
            self.mock_telemetry, get_signal_fn=get_signal_fn,
        )

        # Only the first scenario ran; the other two were aborted.
        self.assertEqual(len(telemetries), 1)
        self.assertEqual(len(failed), 0)
        self.assertEqual(telemetries[0].scenario, "scenario1.yaml")

    @_apply_patches
    def test_stop_mid_sleep_aborts_remaining_scenarios(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """STOP received after a few RUN ticks still aborts the batch."""
        self._setup_signal_ctx(mock_signal_ctx)

        # Two RUN ticks, then STOP
        signals = iter(["RUN", "RUN", "STOP"])
        get_signal_fn = lambda: next(signals, "STOP")

        scenarios_list = ["scenario1.yaml", "scenario2.yaml"]
        failed, telemetries = self.plugin.run_scenarios(
            "test-uuid", scenarios_list, self.krkn_config,
            self.mock_telemetry, get_signal_fn=get_signal_fn,
        )

        self.assertEqual(len(telemetries), 1)
        self.assertEqual(telemetries[0].scenario, "scenario1.yaml")

    # ------------------------------------------------------------------
    # PAUSE during inter-scenario sleep
    # ------------------------------------------------------------------
    @_apply_patches
    def test_pause_during_sleep_waits_then_resumes(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """PAUSE during sleep blocks until RUN is received, then all scenarios complete."""
        self._setup_signal_ctx(mock_signal_ctx)

        # After first scenario: PAUSE for 2 ticks, then RUN, then RUN for
        # the pre-scenario check before scenario2.
        signals = iter(["PAUSE", "PAUSE", "RUN", "RUN"])
        get_signal_fn = lambda: next(signals, "RUN")

        scenarios_list = ["scenario1.yaml", "scenario2.yaml"]
        failed, telemetries = self.plugin.run_scenarios(
            "test-uuid", scenarios_list, self.krkn_config,
            self.mock_telemetry, get_signal_fn=get_signal_fn,
        )

        # Both scenarios should have completed.
        self.assertEqual(len(telemetries), 2)
        self.assertEqual(len(failed), 0)

    # ------------------------------------------------------------------
    # STOP before a scenario starts (pre-scenario check)
    # ------------------------------------------------------------------
    @_apply_patches
    def test_stop_before_second_scenario_aborts(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """STOP received in the pre-scenario check prevents the next scenario from running."""
        self._setup_signal_ctx(mock_signal_ctx)

        # wait_duration=0 so the sleep loop never runs; STOP is only seen in
        # the pre-scenario check at the top of the second iteration.
        config_no_wait = {
            "tunings": {"wait_duration": 0},
            "telemetry": {"events_backup": False},
        }

        # First pre-scenario check: RUN (scenario1 starts).
        # Second pre-scenario check: STOP (scenario2 is aborted).
        signals = iter(["RUN", "STOP"])
        get_signal_fn = lambda: next(signals, "STOP")

        scenarios_list = ["scenario1.yaml", "scenario2.yaml", "scenario3.yaml"]
        failed, telemetries = self.plugin.run_scenarios(
            "test-uuid", scenarios_list, config_no_wait,
            self.mock_telemetry, get_signal_fn=get_signal_fn,
        )

        self.assertEqual(len(telemetries), 1)
        self.assertEqual(telemetries[0].scenario, "scenario1.yaml")

    @_apply_patches
    def test_stop_before_first_scenario_aborts_all(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """STOP on the very first pre-scenario check means no scenarios run."""
        self._setup_signal_ctx(mock_signal_ctx)

        config_no_wait = {
            "tunings": {"wait_duration": 0},
            "telemetry": {"events_backup": False},
        }

        get_signal_fn = lambda: "STOP"

        scenarios_list = ["scenario1.yaml", "scenario2.yaml"]
        failed, telemetries = self.plugin.run_scenarios(
            "test-uuid", scenarios_list, config_no_wait,
            self.mock_telemetry, get_signal_fn=get_signal_fn,
        )

        self.assertEqual(len(telemetries), 0)
        self.assertEqual(len(failed), 0)

    # ------------------------------------------------------------------
    # PAUSE before a scenario starts (pre-scenario check)
    # ------------------------------------------------------------------
    @_apply_patches
    def test_pause_before_scenario_waits_then_runs(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """PAUSE in the pre-scenario check blocks until RUN, then the scenario runs."""
        self._setup_signal_ctx(mock_signal_ctx)

        config_no_wait = {
            "tunings": {"wait_duration": 0},
            "telemetry": {"events_backup": False},
        }

        # scenario1 pre-check: RUN
        # scenario2 pre-check: PAUSE x2, then RUN
        signals = iter(["RUN", "PAUSE", "PAUSE", "RUN"])
        get_signal_fn = lambda: next(signals, "RUN")

        scenarios_list = ["scenario1.yaml", "scenario2.yaml"]
        failed, telemetries = self.plugin.run_scenarios(
            "test-uuid", scenarios_list, config_no_wait,
            self.mock_telemetry, get_signal_fn=get_signal_fn,
        )

        self.assertEqual(len(telemetries), 2)
        self.assertEqual(len(failed), 0)

    # ------------------------------------------------------------------
    # No signal function — backward compatibility
    # ------------------------------------------------------------------
    @_apply_patches
    def test_no_signal_fn_all_scenarios_complete(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """When get_signal_fn is None, all scenarios run to completion (original behaviour)."""
        self._setup_signal_ctx(mock_signal_ctx)

        scenarios_list = ["scenario1.yaml", "scenario2.yaml", "scenario3.yaml"]
        failed, telemetries = self.plugin.run_scenarios(
            "test-uuid", scenarios_list, self.krkn_config,
            self.mock_telemetry,
            # no get_signal_fn passed
        )

        self.assertEqual(len(telemetries), 3)
        self.assertEqual(len(failed), 0)

    @_apply_patches
    def test_no_signal_fn_sleep_called_for_each_scenario(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """When get_signal_fn is None, time.sleep(1) is called wait_duration times per scenario."""
        self._setup_signal_ctx(mock_signal_ctx)

        scenarios_list = ["scenario1.yaml", "scenario2.yaml"]
        self.plugin.run_scenarios(
            "test-uuid", scenarios_list, self.krkn_config,
            self.mock_telemetry,
        )

        # wait_duration=3, 2 scenarios → 3*2 = 6 sleep(1) calls
        self.assertEqual(mock_sleep.call_count, 6)
        mock_sleep.assert_called_with(1)


if __name__ == "__main__":
    unittest.main()
