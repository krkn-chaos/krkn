#!/usr/bin/env python3

"""
Test suite for krkn.prometheus.client module

Validates that alert key validation and metric query routing
use sorted() correctly (fixes #1182).

Usage:
    python -m unittest tests/test_prometheus_client.py -v
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from krkn.prometheus import client


class TestAlertsKeyValidation(unittest.TestCase):
    """Tests for alert key validation in the alerts() function."""

    def setUp(self):
        self.prom_cli = MagicMock()
        self.elastic = MagicMock()
        self.run_uuid = "test-uuid"
        self.start_time = 1000000.0
        self.end_time = 1000060.0
        self.elastic_alerts_index = "test-index"

    def _write_alert_profile(self, content):
        """Write a YAML alert profile to a temp file and return its path."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        f.write(content)
        f.close()
        return f.name

    def test_valid_alert_keys_are_processed(self):
        """Alerts with correct keys (expr, description, severity) should be processed."""
        profile_path = self._write_alert_profile(
            '- expr: "up == 0"\n'
            '  description: "target down"\n'
            '  severity: "critical"\n'
        )
        try:
            self.prom_cli.process_alert.return_value = (
                self.start_time,
                "test-alert",
            )
            self.elastic.push_alert.return_value = 0

            client.alerts(
                self.prom_cli,
                self.elastic,
                self.run_uuid,
                self.start_time,
                self.end_time,
                profile_path,
                self.elastic_alerts_index,
            )

            self.prom_cli.process_alert.assert_called_once()
        finally:
            os.unlink(profile_path)

    def test_invalid_alert_keys_are_skipped(self):
        """Alerts with wrong keys should be skipped and not processed."""
        profile_path = self._write_alert_profile(
            '- wrong_key: "up == 0"\n'
            '  another_bad_key: "test"\n'
            '  third_bad_key: "info"\n'
        )
        try:
            client.alerts(
                self.prom_cli,
                self.elastic,
                self.run_uuid,
                self.start_time,
                self.end_time,
                profile_path,
                self.elastic_alerts_index,
            )

            self.prom_cli.process_alert.assert_not_called()
        finally:
            os.unlink(profile_path)

    def test_mixed_valid_and_invalid_alerts(self):
        """Only alerts with correct keys should be processed; invalid ones skipped."""
        profile_path = self._write_alert_profile(
            '- wrong_key: "bad"\n'
            '  other: "bad"\n'
            '  extra: "bad"\n'
            '- expr: "up == 0"\n'
            '  description: "target down"\n'
            '  severity: "critical"\n'
        )
        try:
            self.prom_cli.process_alert.return_value = (None, None)

            client.alerts(
                self.prom_cli,
                self.elastic,
                self.run_uuid,
                self.start_time,
                self.end_time,
                profile_path,
                self.elastic_alerts_index,
            )

            self.assertEqual(self.prom_cli.process_alert.call_count, 1)
        finally:
            os.unlink(profile_path)

    def test_alert_keys_different_count_are_skipped(self):
        """Alerts with too many or too few keys should be skipped."""
        profile_path = self._write_alert_profile(
            '- expr: "up == 0"\n'
            '  description: "target down"\n'
        )
        try:
            client.alerts(
                self.prom_cli,
                self.elastic,
                self.run_uuid,
                self.start_time,
                self.end_time,
                profile_path,
                self.elastic_alerts_index,
            )

            self.prom_cli.process_alert.assert_not_called()
        finally:
            os.unlink(profile_path)


class TestMetricsQueryRouting(unittest.TestCase):
    """Tests for metric query routing in the metrics() function."""

    def setUp(self):
        self.prom_cli = MagicMock()
        self.elastic = MagicMock()
        self.run_uuid = "test-uuid"
        self.start_time = 1000000.0
        self.end_time = 1000060.0
        self.elastic_metrics_index = "test-metrics-index"
        self.telemetry_json = json.dumps({
            "scenarios": [],
            "health_checks": [],
            "virt_checks": [],
        })

    def _write_metrics_profile(self, metrics_list):
        """Write a YAML metrics profile to a temp file and return its path."""
        import yaml
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        yaml.dump({"metrics": metrics_list}, f)
        f.close()
        return f.name

    def test_range_query_with_query_and_metricName_keys(self):
        """Metric with only 'query' and 'metricName' keys should use range query."""
        profile_path = self._write_metrics_profile([
            {"query": "up", "metricName": "target_up"},
        ])
        try:
            self.prom_cli.process_prom_query_in_range.return_value = []
            self.elastic.upload_metrics_to_elasticsearch.return_value = 0

            client.metrics(
                self.prom_cli,
                self.elastic,
                self.run_uuid,
                self.start_time,
                self.end_time,
                profile_path,
                self.elastic_metrics_index,
                self.telemetry_json,
            )

            self.prom_cli.process_prom_query_in_range.assert_called_once()
            self.prom_cli.process_query.assert_not_called()
        finally:
            os.unlink(profile_path)

    def test_instant_query_with_instant_flag(self):
        """Metric with 'instant: true' should use instant query."""
        profile_path = self._write_metrics_profile([
            {"query": "up", "metricName": "target_up", "instant": True},
        ])
        try:
            self.prom_cli.process_query.return_value = []
            self.elastic.upload_metrics_to_elasticsearch.return_value = 0

            client.metrics(
                self.prom_cli,
                self.elastic,
                self.run_uuid,
                self.start_time,
                self.end_time,
                profile_path,
                self.elastic_metrics_index,
                self.telemetry_json,
            )

            self.prom_cli.process_query.assert_called_once()
            self.prom_cli.process_prom_query_in_range.assert_not_called()
        finally:
            os.unlink(profile_path)

    def test_extra_keys_skip_range_query(self):
        """Metric with extra unknown keys should not match range query branch."""
        profile_path = self._write_metrics_profile([
            {"query": "up", "metricName": "target_up", "unknownKey": "val"},
        ])
        try:
            self.elastic.upload_metrics_to_elasticsearch.return_value = 0

            client.metrics(
                self.prom_cli,
                self.elastic,
                self.run_uuid,
                self.start_time,
                self.end_time,
                profile_path,
                self.elastic_metrics_index,
                self.telemetry_json,
            )

            self.prom_cli.process_prom_query_in_range.assert_not_called()
            self.prom_cli.process_query.assert_not_called()
        finally:
            os.unlink(profile_path)


if __name__ == "__main__":
    unittest.main()
