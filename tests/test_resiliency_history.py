#!/usr/bin/env python3
"""
Unit tests for krkn.resiliency.history.

Usage:
    python -m unittest tests/test_resiliency_history.py -v
"""

import datetime
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krkn.resiliency.history import (
    HistoryWindow,
    apply_historical_resiliency,
    parse_datetime,
    parse_duration,
    parse_history_window,
)


class TestParseDuration(unittest.TestCase):

    def test_minutes(self):
        self.assertEqual(parse_duration("5m"), datetime.timedelta(minutes=5))

    def test_hours(self):
        self.assertEqual(parse_duration("24h"), datetime.timedelta(hours=24))

    def test_days(self):
        self.assertEqual(parse_duration("7d"), datetime.timedelta(days=7))

    def test_seconds(self):
        self.assertEqual(parse_duration("30s"), datetime.timedelta(seconds=30))

    def test_weeks(self):
        self.assertEqual(parse_duration("2w"), datetime.timedelta(weeks=2))

    def test_uppercase_unit(self):
        self.assertEqual(parse_duration("1H"), datetime.timedelta(hours=1))

    def test_fractional_value(self):
        self.assertEqual(parse_duration("1.5h"), datetime.timedelta(hours=1.5))

    def test_unknown_unit_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_duration("5x")
        self.assertIn("Unknown duration unit", str(ctx.exception))

    def test_zero_value_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_duration("0h")
        self.assertIn("positive", str(ctx.exception))

    def test_negative_value_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_duration("-1h")
        self.assertIn("positive", str(ctx.exception))

    def test_non_numeric_value_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_duration("abch")
        self.assertIn("Invalid numeric value", str(ctx.exception))

    def test_too_short_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_duration("h")
        self.assertIn("expected a number", str(ctx.exception))


class TestParseDatetime(unittest.TestCase):

    def test_iso_with_time(self):
        result = parse_datetime("2026-05-25T08:00:00")
        self.assertEqual(result, datetime.datetime(2026, 5, 25, 8, 0, 0, tzinfo=datetime.timezone.utc))

    def test_space_separated(self):
        result = parse_datetime("2026-05-25 08:00:00")
        self.assertEqual(result, datetime.datetime(2026, 5, 25, 8, 0, 0, tzinfo=datetime.timezone.utc))

    def test_date_only(self):
        result = parse_datetime("2026-05-25")
        self.assertEqual(result, datetime.datetime(2026, 5, 25, 0, 0, 0, tzinfo=datetime.timezone.utc))

    def test_leading_trailing_whitespace(self):
        result = parse_datetime("  2026-05-25T10:30:00  ")
        self.assertEqual(result, datetime.datetime(2026, 5, 25, 10, 30, 0, tzinfo=datetime.timezone.utc))

    def test_invalid_format_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_datetime("25/05/2026")
        self.assertIn("Cannot parse datetime", str(ctx.exception))

    def test_invalid_date_raises(self):
        with self.assertRaises(ValueError):
            parse_datetime("2026-13-01")


class TestParseHistoryWindow(unittest.TestCase):

    def test_no_options_returns_none(self):
        self.assertIsNone(parse_history_window(None, None, None))

    def test_duration_mode(self):
        window = parse_history_window("1h", None, None)
        self.assertIsNotNone(window)
        self.assertEqual(window.label, "1h")
        expected_delta = datetime.timedelta(hours=1)
        self.assertAlmostEqual(
            (window.end - window.start).total_seconds(),
            expected_delta.total_seconds(),
            delta=2,
        )

    def test_explicit_range_requires_flag(self):
        with self.assertRaises(ValueError) as ctx:
            parse_history_window(None, "2026-05-25T08:00:00", "2026-05-25T09:00:00")
        self.assertIn("--resiliency-score", str(ctx.exception))

    def test_explicit_range_with_flag(self):
        window = parse_history_window(
            None, "2026-05-25T08:00:00", "2026-05-25T09:00:00",
            resiliency_score_flag=True,
        )
        self.assertIsNotNone(window)
        self.assertEqual(window.start, datetime.datetime(2026, 5, 25, 8, 0, 0, tzinfo=datetime.timezone.utc))
        self.assertEqual(window.end, datetime.datetime(2026, 5, 25, 9, 0, 0, tzinfo=datetime.timezone.utc))

    def test_explicit_range_label(self):
        window = parse_history_window(
            None, "2026-05-25", "2026-05-26", resiliency_score_flag=True,
        )
        self.assertIn("2026-05-25", window.label)
        self.assertIn("2026-05-26", window.label)

    def test_mutual_exclusivity_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_history_window(
                "1h", "2026-05-25T08:00:00", "2026-05-25T09:00:00",
                resiliency_score_flag=True,
            )
        self.assertIn("mutually exclusive", str(ctx.exception))

    def test_missing_end_time_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_history_window(None, "2026-05-25T08:00:00", None, resiliency_score_flag=True)
        self.assertIn("both be provided", str(ctx.exception))

    def test_missing_start_time_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_history_window(None, None, "2026-05-25T09:00:00", resiliency_score_flag=True)
        self.assertIn("both be provided", str(ctx.exception))

    def test_end_before_start_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_history_window(
                None, "2026-05-25T09:00:00", "2026-05-25T08:00:00",
                resiliency_score_flag=True,
            )
        self.assertIn("after --start-time", str(ctx.exception))

    def test_end_equal_start_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_history_window(
                None, "2026-05-25T08:00:00", "2026-05-25T08:00:00",
                resiliency_score_flag=True,
            )
        self.assertIn("after --start-time", str(ctx.exception))

    def test_invalid_duration_raises(self):
        with self.assertRaises(ValueError):
            parse_history_window("badvalue", None, None)

    def test_invalid_start_time_raises(self):
        with self.assertRaises(ValueError):
            parse_history_window(None, "not-a-date", "2026-05-25T09:00:00", resiliency_score_flag=True)


class TestApplyHistoricalResiliency(unittest.TestCase):

    def _make_window(self):
        start = datetime.datetime(2026, 5, 25, 8, 0, 0, tzinfo=datetime.timezone.utc)
        end = datetime.datetime(2026, 5, 25, 9, 0, 0, tzinfo=datetime.timezone.utc)
        return HistoryWindow(start=start, end=end, label="1h")

    def test_raises_when_prometheus_is_none(self):
        resiliency_obj = MagicMock()
        telemetry = MagicMock()
        with self.assertRaises(RuntimeError) as ctx:
            apply_historical_resiliency(self._make_window(), resiliency_obj, None, telemetry)
        self.assertIn("Prometheus", str(ctx.exception))

    def test_raises_when_resiliency_obj_is_none(self):
        prometheus = MagicMock()
        telemetry = MagicMock()
        with self.assertRaises(RuntimeError) as ctx:
            apply_historical_resiliency(self._make_window(), None, prometheus, telemetry)
        self.assertIn("Prometheus", str(ctx.exception))

    def test_populates_overall_resiliency_report(self):
        window = self._make_window()
        resiliency_obj = MagicMock()
        resiliency_obj.scenario_reports = [
            {"score": 85, "breakdown": {"passed": 20, "failed": 5}}
        ]
        prometheus = MagicMock()
        telemetry = MagicMock()

        apply_historical_resiliency(window, resiliency_obj, prometheus, telemetry)

        resiliency_obj.add_scenario_report.assert_called_once_with(
            scenario_name="historical",
            prom_cli=prometheus,
            start_time=window.start,
            end_time=window.end,
        )
        self.assertIsNotNone(telemetry.overall_resiliency_report)
        report = telemetry.overall_resiliency_report
        self.assertEqual(report.resiliency_score, 85)
        self.assertEqual(report.passed_slos, 20)
        self.assertEqual(report.total_slos, 25)

    def test_uses_last_scenario_report(self):
        window = self._make_window()
        resiliency_obj = MagicMock()
        resiliency_obj.scenario_reports = [
            {"score": 50, "breakdown": {"passed": 10, "failed": 10}},
            {"score": 90, "breakdown": {"passed": 18, "failed": 2}},
        ]
        prometheus = MagicMock()
        telemetry = MagicMock()

        apply_historical_resiliency(window, resiliency_obj, prometheus, telemetry)

        self.assertEqual(telemetry.overall_resiliency_report.resiliency_score, 90)


if __name__ == "__main__":
    unittest.main()
