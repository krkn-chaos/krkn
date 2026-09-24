import datetime
import queue
import unittest
from unittest.mock import Mock

from krkn.health_checks.prometheus_health_check_plugin import PrometheusHealthCheckPlugin


class TestPrometheusHealthCheckPlugin(unittest.TestCase):
    def setUp(self):
        self.prometheus = Mock()
        self.start = datetime.datetime(2026, 1, 1)
        self.end = datetime.datetime(2026, 1, 1, 0, 1)
        self.plugin = PrometheusHealthCheckPlugin(
            prometheus=self.prometheus,
            chaos_start_time=self.start,
            chaos_end_time=self.end,
        )

    def test_pre_and_post_use_one_instant_query(self):
        self.prometheus.process_query.return_value = [{"value": [1, "0"]}]
        config = {"enable_alerts": True, "config": [{"expr": "up == 0", "name": "down"}]}

        self.assertTrue(self.plugin.run_once(config, phase="pre")["passed"])
        result = self.plugin.run_once(config, phase="post")
        self.assertTrue(result["passed"])
        self.assertTrue(result["alerts"][0].status)
        self.assertEqual(self.prometheus.process_query.call_count, 2)
        self.prometheus.process_prom_query_in_range.assert_not_called()

    def test_during_uses_one_range_query_for_full_window(self):
        self.prometheus.process_prom_query_in_range.return_value = [{"values": [[1, "0"]]}]
        config = {"enable_alerts": True, "config": [{"expr": "up == 0", "name": "down"}]}

        result = self.plugin.run_once(config, telemetry_queue=queue.Queue(), phase="during")

        self.assertTrue(result["passed"])
        self.prometheus.process_prom_query_in_range.assert_called_once_with(
            "up == 0", start_time=self.start, end_time=self.end
        )
        self.prometheus.process_query.assert_not_called()

    def test_failed_alert_is_pushed_to_elastic_with_phase(self):
        elastic = Mock()
        self.plugin.elastic = elastic
        self.plugin.run_uuid = "run-1"
        self.plugin.elastic_alerts_index = "alerts"
        self.prometheus.process_query.return_value = [{"value": [1, "1"]}]
        config = {
            "enable_alerts": True,
            "config": [{
                "expr": "up == 0",
                "name": "down",
                "description": "Target is down",
                "severity": "critical",
            }],
        }

        result = self.plugin.run_once(config, phase="post")

        self.assertFalse(result["passed"])
        self.assertEqual(result["alerts"][0].phase, "post")
        self.assertFalse(result["alerts"][0].status)
        elastic.push_alert.assert_called_once()
        pushed_alert = elastic.push_alert.call_args.args[0]
        self.assertEqual(pushed_alert.phase, "post")
        self.assertEqual(elastic.push_alert.call_args.args[1], "alerts")

    def test_warning_alert_is_recorded_but_does_not_fail(self):
        self.prometheus.process_query.return_value = [{"value": [1, "1"]}]
        config = {
            "enable_alerts": True,
            "config": [{"expr": "up == 0", "name": "warning", "severity": "warning"}],
        }

        result = self.plugin.run_once(config, phase="post")

        self.assertTrue(result["passed"])
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["alerts"][0].status, False)


if __name__ == "__main__":
    unittest.main()
