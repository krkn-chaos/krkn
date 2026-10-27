import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from krkn.prometheus import client


class TestMetricsQueryRouting(unittest.TestCase):
    def setUp(self):
        self.prom_cli = MagicMock()
        self.elastic = MagicMock()
        self.telemetry_json = json.dumps({"scenarios": [], "health_checks": [], "virt_checks": []})

    def _write_profile(self, metrics):
        profile = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        profile.write(json.dumps({"metrics": metrics}))
        profile.close()
        return profile.name

    def test_range_query(self):
        path = self._write_profile([{"query": "up", "metricName": "target_up"}])
        try:
            self.prom_cli.process_prom_query_in_range.return_value = []
            client.metrics(self.prom_cli, self.elastic, "run", 1000, 1060, path, "metrics", self.telemetry_json)
            self.prom_cli.process_prom_query_in_range.assert_called_once()
            self.prom_cli.process_query.assert_not_called()
        finally:
            os.unlink(path)

    def test_instant_query(self):
        path = self._write_profile([{"query": "up", "metricName": "target_up", "instant": True}])
        try:
            self.prom_cli.process_query.return_value = []
            client.metrics(self.prom_cli, self.elastic, "run", 1000, 1060, path, "metrics", self.telemetry_json)
            self.prom_cli.process_query.assert_called_once()
            self.prom_cli.process_prom_query_in_range.assert_not_called()
        finally:
            os.unlink(path)

    def test_elapsed_placeholder_uses_rounded_run_duration(self):
        path = self._write_profile([
            {"query": "rate(requests_total[.elapsed])", "metricName": "request_rate"}
        ])
        try:
            self.prom_cli.process_prom_query_in_range.return_value = []
            client.metrics(self.prom_cli, self.elastic, "run", 1000, 1432, path, "metrics", self.telemetry_json)
            query = self.prom_cli.process_prom_query_in_range.call_args.args[0]
            self.assertEqual(query, "rate(requests_total[8m])")
        finally:
            os.unlink(path)

    def test_missing_metrics_profile_exits(self):
        # Regression for #1607: missing import sys used to raise NameError
        # instead of logging and exiting with code 1.
        with self.assertRaises(SystemExit) as cm:
            client.metrics(
                self.prom_cli,
                self.elastic,
                "run",
                1000,
                1060,
                "/nao/existe.yaml",
                "metrics",
                self.telemetry_json,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_invalid_metrics_profile_exits(self):
        path = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        path.write("metrics: {}\n")
        path.close()
        try:
            with self.assertRaises(SystemExit) as cm:
                client.metrics(
                    self.prom_cli,
                    self.elastic,
                    "run",
                    1000,
                    1060,
                    path.name,
                    "metrics",
                    self.telemetry_json,
                )
            self.assertEqual(cm.exception.code, 1)
        finally:
            os.unlink(path.name)

    def test_critical_alert_range_query_uses_datetimes(self):
        summary = MagicMock()
        self.prom_cli.process_prom_query_in_range.return_value = []
        self.prom_cli.process_query.return_value = []

        client.critical_alerts(
            self.prom_cli,
            summary,
            self.elastic,
            "run",
            "scenario",
            1000,
            1060,
            "alerts",
        )

        call = self.prom_cli.process_prom_query_in_range.call_args
        self.assertIsInstance(call.kwargs["start_time"], datetime.datetime)
        self.assertIsInstance(call.kwargs["end_time"], datetime.datetime)
        self.assertEqual(call.kwargs["start_time"].timestamp(), 1000)
        self.assertEqual(call.kwargs["end_time"].timestamp(), 1060)

    def test_critical_alert_range_query_accepts_datetime_end_time(self):
        summary = MagicMock()
        self.prom_cli.process_prom_query_in_range.return_value = []
        self.prom_cli.process_query.return_value = []
        end_time = datetime.datetime(2026, 10, 2, 15, 3)

        client.critical_alerts(
            self.prom_cli,
            summary,
            self.elastic,
            "run",
            "scenario",
            1000,
            end_time,
            "alerts",
        )

        call = self.prom_cli.process_prom_query_in_range.call_args
        self.assertEqual(call.kwargs["end_time"], end_time.replace(tzinfo=datetime.timezone.utc))

    def test_critical_alert_range_query_keeps_start_before_end(self):
        summary = MagicMock()
        self.prom_cli.process_prom_query_in_range.return_value = []
        self.prom_cli.process_query.return_value = []
        end_time = datetime.datetime.now(datetime.timezone.utc)

        client.critical_alerts(
            self.prom_cli,
            summary,
            self.elastic,
            "run",
            "scenario",
            int(end_time.timestamp()) - 60,
            end_time,
            "alerts",
        )

        call = self.prom_cli.process_prom_query_in_range.call_args
        self.assertLess(call.kwargs["start_time"], call.kwargs["end_time"])


if __name__ == "__main__":
    unittest.main()
