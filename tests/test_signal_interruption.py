"""
Test suite for signal interruption behaviour in AbstractScenarioPlugin.run_scenarios()

Tests cover:
- STOP signal during inter-scenario sleep aborts remaining scenarios
- STOP signal before a scenario starts aborts remaining scenarios
- No get_signal_fn (None) behaves like original unconditional sleep
- PAUSE is intentionally NOT handled here; it is delegated to the
  outer loop in run_kraken.py

Run individually with:
  python -m unittest tests/test_signal_interruption.py -v
"""

import unittest
from unittest.mock import patch, Mock
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


_COMMON_PATCHES = [
    patch("krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status"),
    patch("krkn.scenario_plugins.abstract_scenario_plugin.cleanup_rollback_version_files"),
    patch("krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs"),
    patch("krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context"),
    patch("krkn.scenario_plugins.abstract_scenario_plugin.os.path.exists", return_value=True),
    patch("time.sleep"),
]


def _apply_patches(test_fn):
    for p in reversed(_COMMON_PATCHES):
        test_fn = p(test_fn)
    return test_fn


class TestSignalInterruption(unittest.TestCase):

    def setUp(self):
        self.plugin = ConcretePlugin()
        self.mock_telemetry = Mock(spec=KrknTelemetryOpenshift)
        self.mock_telemetry.set_parameters_base64.return_value = {"test": "config"}
        self.mock_telemetry.get_telemetry_request_id.return_value = "test-request-id"
        self.mock_telemetry.get_lib_kubernetes.return_value = Mock()

        self.krkn_config = {
            "tunings": {"wait_duration": 3},
            "telemetry": {"events_backup": False},
        }

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
        """STOP on the first tick of the sleep loop aborts the batch."""
        self._setup_signal_ctx(mock_signal_ctx)

        signals = iter(["STOP"])
        get_signal_fn = lambda: next(signals, "STOP")

        scenarios_list = ["scenario1.yaml", "scenario2.yaml", "scenario3.yaml"]
        failed, telemetries = self.plugin.run_scenarios(
            "test-uuid", scenarios_list, self.krkn_config,
            self.mock_telemetry, get_signal_fn=get_signal_fn,
        )

        self.assertEqual(len(telemetries), 1)
        self.assertEqual(len(failed), 0)
        self.assertEqual(telemetries[0].scenario, "scenario1.yaml")

    @_apply_patches
    def test_stop_mid_sleep_aborts_remaining_scenarios(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """STOP after a few RUN ticks still aborts the batch."""
        self._setup_signal_ctx(mock_signal_ctx)

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
    # STOP before a scenario starts (pre-scenario check)
    # ------------------------------------------------------------------

    @_apply_patches
    def test_stop_before_second_scenario_aborts(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """STOP in the pre-scenario check prevents the next scenario from running."""
        self._setup_signal_ctx(mock_signal_ctx)

        config_no_wait = {
            "tunings": {"wait_duration": 0},
            "telemetry": {"events_backup": False},
        }

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
    # No signal function — backward compatibility
    # ------------------------------------------------------------------

    @_apply_patches
    def test_no_signal_fn_all_scenarios_complete(
        self, mock_sleep, mock_exists, mock_signal_ctx,
        mock_collect_logs, mock_cleanup, mock_cerberus
    ):
        """When get_signal_fn is None, all scenarios run to completion."""
        self._setup_signal_ctx(mock_signal_ctx)

        scenarios_list = ["scenario1.yaml", "scenario2.yaml", "scenario3.yaml"]
        failed, telemetries = self.plugin.run_scenarios(
            "test-uuid", scenarios_list, self.krkn_config,
            self.mock_telemetry,
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
