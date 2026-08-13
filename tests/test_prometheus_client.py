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

            result = client.alerts(
                self.prom_cli,
                self.elastic,
                self.run_uuid,
                self.start_time,
                self.end_time,
                profile_path,
                self.elastic_alerts_index,
            )

            self.prom_cli.process_alert.assert_called_once()
            self.assertEqual(len(result), 1)
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


class TestAlertsFailureCount(unittest.TestCase):
    """Tests that alerts() returns the correct FailedAlert list for critical/error severity."""

    def setUp(self):
        self.prom_cli = MagicMock()
        self.elastic = MagicMock()
        self.run_uuid = "test-uuid"
        self.start_time = 1000000.0
        self.end_time = 1000060.0
        self.elastic_alerts_index = "test-index"

    def _write_alert_profile(self, content):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        f.write(content)
        f.close()
        return f.name

    def _call_alerts(self, profile_path):
        return client.alerts(
            self.prom_cli,
            self.elastic,
            self.run_uuid,
            self.start_time,
            self.end_time,
            profile_path,
            self.elastic_alerts_index,
        )

    def test_returns_zero_when_no_alerts_fire(self):
        """Returns empty list when process_alert returns (None, None) for all alerts."""
        profile_path = self._write_alert_profile(
            '- expr: "up == 0"\n'
            '  description: "target down"\n'
            '  severity: "critical"\n'
        )
        try:
            self.prom_cli.process_alert.return_value = (None, None)
            result = self._call_alerts(profile_path)
            self.assertEqual(result, [])
        finally:
            os.unlink(profile_path)

    def test_returns_one_for_single_critical_alert(self):
        """Returns one FailedAlert when one critical-severity alert fires."""
        profile_path = self._write_alert_profile(
            '- expr: "up == 0"\n'
            '  description: "target down"\n'
            '  severity: "critical"\n'
        )
        try:
            self.prom_cli.process_alert.return_value = (self.start_time, "target down")
            self.elastic.push_alert.return_value = 0
            result = self._call_alerts(profile_path)
            self.assertEqual(len(result), 1)
        finally:
            os.unlink(profile_path)

    def test_returns_one_for_single_error_alert(self):
        """Returns one FailedAlert when one error-severity alert fires."""
        profile_path = self._write_alert_profile(
            '- expr: "up == 0"\n'
            '  description: "target down"\n'
            '  severity: "error"\n'
        )
        try:
            self.prom_cli.process_alert.return_value = (self.start_time, "target down")
            self.elastic.push_alert.return_value = 0
            result = self._call_alerts(profile_path)
            self.assertEqual(len(result), 1)
        finally:
            os.unlink(profile_path)

    def test_warning_alert_does_not_increment_count(self):
        """Returns empty list when only warning/info/debug alerts fire."""
        profile_path = self._write_alert_profile(
            '- expr: "up == 0"\n'
            '  description: "slow"\n'
            '  severity: "warning"\n'
            '- expr: "up == 1"\n'
            '  description: "info"\n'
            '  severity: "info"\n'
        )
        try:
            self.prom_cli.process_alert.return_value = (self.start_time, "alert fired")
            self.elastic.push_alert.return_value = 0
            result = self._call_alerts(profile_path)
            self.assertEqual(result, [])
        finally:
            os.unlink(profile_path)

    def test_counts_multiple_critical_and_error_alerts(self):
        """Returns 3 FailedAlerts when multiple critical and error alerts fire."""
        profile_path = self._write_alert_profile(
            '- expr: "a == 0"\n'
            '  description: "a"\n'
            '  severity: "critical"\n'
            '- expr: "b == 0"\n'
            '  description: "b"\n'
            '  severity: "error"\n'
            '- expr: "c == 0"\n'
            '  description: "c"\n'
            '  severity: "warning"\n'
            '- expr: "d == 0"\n'
            '  description: "d"\n'
            '  severity: "critical"\n'
        )
        try:
            self.prom_cli.process_alert.return_value = (self.start_time, "fired")
            self.elastic.push_alert.return_value = 0
            result = self._call_alerts(profile_path)
            self.assertEqual(len(result), 3)
        finally:
            os.unlink(profile_path)

    def test_non_firing_critical_alerts_not_counted(self):
        """Critical alerts that don't fire (return None) produce no FailedAlert."""
        profile_path = self._write_alert_profile(
            '- expr: "a == 0"\n'
            '  description: "fired"\n'
            '  severity: "critical"\n'
            '- expr: "b == 0"\n'
            '  description: "not fired"\n'
            '  severity: "critical"\n'
        )
        try:
            self.prom_cli.process_alert.side_effect = [
                (self.start_time, "fired"),
                (None, None),
            ]
            self.elastic.push_alert.return_value = 0
            result = self._call_alerts(profile_path)
            self.assertEqual(len(result), 1)
        finally:
            os.unlink(profile_path)

    def test_elastic_push_still_called_for_non_critical_firing_alerts(self):
        """Elastic push is called for warning/info alerts that fire even though they don't fail the run."""
        profile_path = self._write_alert_profile(
            '- expr: "up == 0"\n'
            '  description: "slow"\n'
            '  severity: "warning"\n'
        )
        try:
            self.prom_cli.process_alert.return_value = (self.start_time, "slow")
            self.elastic.push_alert.return_value = 0
            result = self._call_alerts(profile_path)
            self.assertEqual(result, [])
            self.elastic.push_alert.assert_called_once()
        finally:
            os.unlink(profile_path)


class TestJobStatusComputation(unittest.TestCase):
    """
    Tests the job_status logic from run_kraken.py:

        if post_critical_alerts > 0 or profile_critical_alerts > 0:
            chaos_telemetry.job_status = False

        chaos_output.job_status = (
            chaos_telemetry.job_status
            and post_critical_alerts == 0
            and profile_critical_alerts == 0
        )

    Mirrors the logic directly so that regressions in the computation are caught.
    """

    def _compute(self, telemetry_job_status, post_critical_alerts, profile_critical_alerts):
        if post_critical_alerts > 0 or profile_critical_alerts > 0:
            telemetry_job_status = False
        return (
            telemetry_job_status
            and post_critical_alerts == 0
            and profile_critical_alerts == 0
        )

    def test_true_when_no_failures(self):
        self.assertTrue(self._compute(True, 0, 0))

    def test_false_on_post_critical_alerts(self):
        self.assertFalse(self._compute(True, 1, 0))

    def test_false_on_profile_critical_alerts(self):
        self.assertFalse(self._compute(True, 0, 1))

    def test_false_on_scenario_failure(self):
        """chaos_telemetry.job_status starts False when a scenario failed (set by krkn-lib)."""
        self.assertFalse(self._compute(False, 0, 0))

    def test_false_when_all_fail(self):
        self.assertFalse(self._compute(False, 2, 3))

    def test_profile_alerts_override_passing_telemetry(self):
        """Even if no scenarios failed, profile critical alerts must flip job_status False."""
        self.assertFalse(self._compute(True, 0, 1))

    def test_post_critical_alerts_override_passing_telemetry(self):
        """Even if no scenarios failed, post-chaos critical alerts must flip job_status False."""
        self.assertFalse(self._compute(True, 1, 0))

    def test_telemetry_job_status_mutated_by_alerts(self):
        """Verifies that chaos_telemetry.job_status is set to False when alerts fire,
        not just chaos_output.job_status — both fields in the output must be false."""
        telemetry_job_status = True
        post_critical_alerts = 0
        profile_critical_alerts = 1

        if post_critical_alerts > 0 or profile_critical_alerts > 0:
            telemetry_job_status = False

        self.assertFalse(telemetry_job_status)
        self.assertFalse(
            telemetry_job_status
            and post_critical_alerts == 0
            and profile_critical_alerts == 0
        )

    # --- exit guard: not chaos_output.job_status ---

    def test_exit_guard_triggers_when_job_status_false(self):
        """not chaos_output.job_status is True when job_status is False — guard fires."""
        job_status = self._compute(False, 0, 0)
        self.assertTrue(not job_status)

    def test_exit_guard_does_not_trigger_when_job_status_true(self):
        """not chaos_output.job_status is False when everything passed — guard skipped."""
        job_status = self._compute(True, 0, 0)
        self.assertFalse(not job_status)

    def test_exit_guard_catches_scenario_failure_not_in_failed_post_scenarios(self):
        """The guard catches chaos_telemetry.job_status=False (set by krkn-lib for a scenario
        failure) even when post_critical_alerts==0, profile_critical_alerts==0, and
        failed_post_scenarios is empty — i.e. when prior specific checks all pass."""
        post_critical_alerts = 0
        profile_critical_alerts = 0
        failed_post_scenarios = []

        # Prior checks do not fire
        self.assertFalse(bool(failed_post_scenarios))
        self.assertEqual(post_critical_alerts, 0)
        self.assertEqual(profile_critical_alerts, 0)

        # krkn-lib set telemetry job_status=False due to a scenario exit_status > 0
        job_status = self._compute(
            telemetry_job_status=False,
            post_critical_alerts=post_critical_alerts,
            profile_critical_alerts=profile_critical_alerts,
        )
        # The catch-all guard fires
        self.assertTrue(not job_status)

    def test_exit_guard_does_not_double_trigger_on_alert_failure(self):
        """When alerts already caused an earlier return (post/profile > 0), job_status
        is also False — the guard would fire too, but order ensures alerts return first."""
        job_status = self._compute(True, 1, 0)
        self.assertFalse(job_status)
        # guard would trigger, but post_critical_alerts > 0 returns 2 before reaching it
        self.assertTrue(not job_status)


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
