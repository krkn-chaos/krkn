import logging
import unittest
from types import SimpleNamespace

from krkn.scenario_plugins.node_actions.recovery_time_summary import (
    RecoveryTimeStats,
    _stats_for,
    build_recovery_time_summary,
    log_recovery_time_summary,
)


def make_node(not_ready=0.0, ready=0.0, stopped=0.0, running=0.0):
    return SimpleNamespace(
        not_ready_time=not_ready,
        ready_time=ready,
        stopped_time=stopped,
        running_time=running,
    )


class TestStatsFor(unittest.TestCase):

    def test_empty_returns_zero_stats(self):
        result = _stats_for("ready_time", [])
        self.assertEqual(result.count, 0)
        self.assertEqual(result.min_seconds, 0.0)
        self.assertEqual(result.max_seconds, 0.0)
        self.assertEqual(result.avg_seconds, 0.0)

    def test_all_zeros_treated_as_no_data(self):
        result = _stats_for("stopped_time", [0.0, 0.0])
        self.assertEqual(result.count, 0)

    def test_single_value(self):
        result = _stats_for("ready_time", [42.5])
        self.assertEqual(result.count, 1)
        self.assertAlmostEqual(result.min_seconds, 42.5)
        self.assertAlmostEqual(result.max_seconds, 42.5)
        self.assertAlmostEqual(result.avg_seconds, 42.5)

    def test_multiple_values(self):
        result = _stats_for("ready_time", [10.0, 20.0, 30.0])
        self.assertEqual(result.count, 3)
        self.assertAlmostEqual(result.min_seconds, 10.0)
        self.assertAlmostEqual(result.max_seconds, 30.0)
        self.assertAlmostEqual(result.avg_seconds, 20.0)

    def test_zeros_excluded_from_aggregation(self):
        result = _stats_for("running_time", [0.0, 15.0, 0.0, 25.0])
        self.assertEqual(result.count, 2)
        self.assertAlmostEqual(result.min_seconds, 15.0)
        self.assertAlmostEqual(result.max_seconds, 25.0)
        self.assertAlmostEqual(result.avg_seconds, 20.0)

    def test_values_rounded_to_three_decimal_places(self):
        result = _stats_for("ready_time", [1.0 / 3.0])
        self.assertEqual(result.avg_seconds, round(1.0 / 3.0, 3))

    def test_metric_name_preserved(self):
        result = _stats_for("stopped_time", [5.0])
        self.assertEqual(result.metric, "stopped_time")


class TestBuildRecoveryTimeSummary(unittest.TestCase):

    def test_empty_list_returns_none(self):
        self.assertIsNone(build_recovery_time_summary([]))

    def test_none_returns_none(self):
        self.assertIsNone(build_recovery_time_summary(None))

    def test_stop_scenario_only_stopped_and_not_ready_populated(self):
        nodes = [make_node(not_ready=0.18, stopped=140.74)]
        result = build_recovery_time_summary(nodes)
        self.assertIsNotNone(result)
        self.assertEqual(result.stopped_time.count, 1)
        self.assertAlmostEqual(result.stopped_time.avg_seconds, 140.74)
        self.assertEqual(result.ready_time.count, 0)
        self.assertEqual(result.running_time.count, 0)

    def test_start_scenario_only_ready_and_running_populated(self):
        nodes = [make_node(ready=43.52, running=12.31)]
        result = build_recovery_time_summary(nodes)
        self.assertEqual(result.ready_time.count, 1)
        self.assertAlmostEqual(result.ready_time.avg_seconds, 43.52)
        self.assertAlmostEqual(result.running_time.avg_seconds, 12.31)
        self.assertEqual(result.stopped_time.count, 0)

    def test_multiple_nodes_aggregated(self):
        # mirrors the example from the official krkn docs
        nodes = [
            make_node(not_ready=0.182, stopped=140.741),
            make_node(not_ready=0.161, stopped=146.721),
            make_node(ready=43.521, running=12.306),
            make_node(ready=48.333, running=12.052),
        ]
        result = build_recovery_time_summary(nodes)
        self.assertEqual(result.stopped_time.count, 2)
        self.assertAlmostEqual(result.stopped_time.min_seconds, 140.741, places=2)
        self.assertAlmostEqual(result.stopped_time.max_seconds, 146.721, places=2)
        self.assertEqual(result.ready_time.count, 2)
        expected_avg = round((43.521 + 48.333) / 2, 3)
        self.assertAlmostEqual(result.ready_time.avg_seconds, expected_avg, places=2)

    def test_missing_attribute_defaults_to_zero(self):
        bare = SimpleNamespace(ready_time=30.0)
        result = build_recovery_time_summary([bare])
        self.assertEqual(result.ready_time.count, 1)
        self.assertEqual(result.stopped_time.count, 0)

    def test_none_attribute_treated_as_zero(self):
        node = make_node(ready=None, stopped=50.0)
        result = build_recovery_time_summary([node])
        self.assertEqual(result.ready_time.count, 0)
        self.assertEqual(result.stopped_time.count, 1)

    def test_to_dict_is_json_serializable(self):
        import json
        nodes = [make_node(ready=10.0, running=5.0)]
        result = build_recovery_time_summary(nodes)
        try:
            json.dumps(result.to_dict())
        except TypeError as e:
            self.fail(f"to_dict() produced non-serializable output: {e}")

    def test_to_dict_has_all_four_keys(self):
        nodes = [make_node(ready=1.0)]
        result = build_recovery_time_summary(nodes)
        self.assertEqual(
            set(result.to_dict().keys()),
            {"not_ready_time", "ready_time", "stopped_time", "running_time"},
        )


class TestLogRecoveryTimeSummary(unittest.TestCase):

    def _sample_summary(self):
        nodes = [
            make_node(stopped=120.0, not_ready=0.2),
            make_node(ready=45.0, running=10.0),
        ]
        return build_recovery_time_summary(nodes)

    def test_logs_at_info_level(self):
        summary = self._sample_summary()
        with self.assertLogs(level=logging.INFO):
            log_recovery_time_summary("node_stop_start_scenario", summary)

    def test_log_has_prefix(self):
        summary = self._sample_summary()
        with self.assertLogs(level=logging.INFO) as ctx:
            log_recovery_time_summary("node_stop_start_scenario", summary)
        self.assertTrue(any("[recovery_time_summary]" in line for line in ctx.output))

    def test_log_contains_action_name(self):
        summary = self._sample_summary()
        with self.assertLogs(level=logging.INFO) as ctx:
            log_recovery_time_summary("node_reboot_scenario", summary)
        self.assertTrue(any("node_reboot_scenario" in line for line in ctx.output))

    def test_log_contains_numeric_values(self):
        summary = self._sample_summary()
        with self.assertLogs(level=logging.INFO) as ctx:
            log_recovery_time_summary("node_stop_scenario", summary)
        combined = "\n".join(ctx.output)
        self.assertIn("120.000", combined)


class TestRecoveryTimeStatsToDict(unittest.TestCase):

    def test_all_fields_present(self):
        stats = RecoveryTimeStats(
            metric="ready_time",
            count=2,
            min_seconds=10.0,
            max_seconds=20.0,
            avg_seconds=15.0,
        )
        d = stats.to_dict()
        self.assertEqual(d["metric"], "ready_time")
        self.assertEqual(d["count"], 2)
        self.assertAlmostEqual(d["min_seconds"], 10.0)
        self.assertAlmostEqual(d["max_seconds"], 20.0)
        self.assertAlmostEqual(d["avg_seconds"], 15.0)


if __name__ == "__main__":
    unittest.main()