#!/usr/bin/env python
#
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
"""
Tests for krkn.resiliency.resiliency module.

How to run these tests:

    # Run all tests in this file
    python -m unittest tests.test_resiliency

    # Run all tests with verbose output
    python -m unittest tests.test_resiliency -v

    # Run a specific test class
    python -m unittest tests.test_resiliency.TestResiliencyInit
    python -m unittest tests.test_resiliency.TestResiliencyCalculateScore
    python -m unittest tests.test_resiliency.TestResiliencyScenarioReports

    # Run a specific test method
    python -m unittest tests.test_resiliency.TestResiliencyInit.test_init_from_file
    python -m unittest tests.test_resiliency.TestResiliencyScenarioReports.test_add_scenario_report

    # Run with coverage
    python -m coverage run -m unittest tests.test_resiliency
    python -m coverage report -m
"""

import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from krkn.resiliency.resiliency import Resiliency


class TestResiliencyInit(unittest.TestCase):
    """Test cases for Resiliency class initialization."""

    def test_init_from_file(self):
        """Test initialization from alerts.yaml file."""
        alerts_data = [
            {"expr": "up == 0", "severity": "critical", "description": "Instance down"},
            {"expr": "cpu > 80", "severity": "warning", "description": "High CPU"},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(alerts_data, f)
            temp_file = f.name

        try:
            res = Resiliency(alerts_yaml_path=temp_file)
            self.assertEqual(len(res._slos), 2)
            self.assertEqual(res._slos[0]["name"], "Instance down")
            self.assertEqual(res._slos[0]["expr"], "up == 0")
            self.assertEqual(res._slos[0]["severity"], "critical")
        finally:
            os.unlink(temp_file)

    def test_init_from_file_not_found_raises_error(self):
        """Test that missing alerts file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            Resiliency(alerts_yaml_path="/nonexistent/path.yaml")

    def test_init_preserves_custom_weight_on_slo(self):
        """Test that custom weight is preserved from the alerts file."""
        alerts_data = [
            {"expr": "up == 0", "severity": "critical", "description": "slo1", "weight": 10},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(alerts_data, f)
            temp_file = f.name

        try:
            res = Resiliency(alerts_yaml_path=temp_file)
            self.assertEqual(res._slos[0]["weight"], 10)
        finally:
            os.unlink(temp_file)

    def test_normalise_alerts_with_valid_data(self):
        """Test _normalise_alerts with valid alert data."""
        raw_alerts = [
            {"expr": "up == 0", "severity": "critical", "description": "Down"},
            {"expr": "cpu > 80", "severity": "warning", "description": "High CPU"},
        ]

        normalized = Resiliency._normalise_alerts(raw_alerts)

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]["name"], "Down")
        self.assertEqual(normalized[1]["name"], "High CPU")

    def test_normalise_alerts_without_description_uses_index(self):
        """Test _normalise_alerts uses index as name when description missing."""
        raw_alerts = [
            {"expr": "up == 0", "severity": "critical"},
        ]

        normalized = Resiliency._normalise_alerts(raw_alerts)

        self.assertEqual(normalized[0]["name"], "slo_0")

    def test_normalise_alerts_skips_invalid_entries(self):
        """Test _normalise_alerts skips entries missing required fields."""
        raw_alerts = [
            {"expr": "up == 0", "severity": "critical"},  # Valid
            {"severity": "warning"},  # Missing expr
            {"expr": "cpu > 80"},  # Missing severity
            "invalid",  # Not a dict
        ]

        with patch('krkn.resiliency.resiliency.logging') as mock_logging:
            normalized = Resiliency._normalise_alerts(raw_alerts)

        self.assertEqual(len(normalized), 1)
        self.assertEqual(mock_logging.warning.call_count, 3)

    def test_normalise_alerts_with_non_list_raises_error(self):
        """Test _normalise_alerts raises ValueError for non-list input."""
        with self.assertRaises(ValueError):
            Resiliency._normalise_alerts("not a list")

        with self.assertRaises(ValueError):
            Resiliency._normalise_alerts({"key": "value"})

    def test_normalise_alerts_stores_weight_none_when_absent(self):
        """Test that alerts without a weight field store None, not 0, preserving severity fallback."""
        raw_alerts = [
            {"expr": "up == 0", "severity": "critical", "description": "no weight"},
        ]

        normalized = Resiliency._normalise_alerts(raw_alerts)

        self.assertIsNone(normalized[0]["weight"])

    def test_normalise_alerts_stores_custom_weight_when_present(self):
        """Test that a numeric weight field is preserved exactly."""
        raw_alerts = [
            {"expr": "up == 0", "severity": "critical", "description": "slo1", "weight": 10},
            {"expr": "cpu > 80", "severity": "warning",  "description": "slo2", "weight": 0.5},
        ]

        normalized = Resiliency._normalise_alerts(raw_alerts)

        self.assertEqual(normalized[0]["weight"], 10)
        self.assertEqual(normalized[1]["weight"], 0.5)


class TestResiliencyCalculateScore(unittest.TestCase):
    """Test cases for calculate_score method."""

    def setUp(self):
        """Set up test fixtures."""
        alerts_data = [
            {"expr": "up == 0", "severity": "critical", "description": "slo1"},
            {"expr": "cpu > 80", "severity": "warning", "description": "slo2"},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(alerts_data, f)
            self.temp_file = f.name

        self.res = Resiliency(alerts_yaml_path=self.temp_file)

    def tearDown(self):
        """Clean up temp files."""
        if os.path.exists(self.temp_file):
            os.unlink(self.temp_file)

    def test_calculate_score_with_all_passing(self):
        """Test calculate_score with all SLOs passing."""
        self.res._results = {"slo1": True, "slo2": True}
        score = self.res.calculate_score()

        self.assertEqual(score, 100)
        self.assertEqual(self.res._score, 100)

    def test_calculate_score_with_failures(self):
        """Test calculate_score with some failures."""
        self.res._results = {"slo1": False, "slo2": True}
        score = self.res.calculate_score()

        # slo1 is critical (3 pts lost), slo2 is warning (1 pt)
        # Total: 4 pts, Lost: 3 pts -> 25%
        self.assertEqual(score, 25)

    def test_calculate_score_with_health_checks(self):
        """Test calculate_score includes health check results."""
        self.res._results = {"slo1": True, "slo2": True}
        health_checks = {"http://service": False}  # Critical, 3 pts lost

        score = self.res.calculate_score(health_check_results=health_checks)

        # Total: 3 + 1 + 3 = 7 pts, Lost: 3 pts -> ~57%
        self.assertEqual(score, 57)
        self.assertEqual(self.res._health_check_results, health_checks)

    def test_calculate_score_uses_per_slo_custom_weight_from_yaml(self):
        """Integration: per-SLO custom weight loaded from YAML is used in scoring."""
        alerts_data = [
            {"expr": "up == 0", "severity": "critical", "description": "high", "weight": 10},
            {"expr": "cpu > 80", "severity": "warning",  "description": "low",  "weight": 0.5},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(alerts_data, f)
            temp = f.name

        try:
            res = Resiliency(alerts_yaml_path=temp)
            # "high" passes (10 pts), "low" fails (loses 0.5 pts)
            res._results = {"high": True, "low": False}
            score = res.calculate_score()

            # Total: 10.5, Lost: 0.5 -> 95%
            self.assertEqual(score, 95)
            self.assertEqual(res._breakdown["total_points"], 10.5)
            self.assertEqual(res._breakdown["points_lost"], 0.5)
        finally:
            os.unlink(temp)

    def test_calculate_score_stores_breakdown(self):
        """Test that calculate_score stores the breakdown dict."""
        self.res._results = {"slo1": True, "slo2": False}
        self.res.calculate_score()

        self.assertIsNotNone(self.res._breakdown)
        self.assertIn("passed", self.res._breakdown)
        self.assertIn("failed", self.res._breakdown)
        self.assertIn("total_points", self.res._breakdown)
        self.assertIn("points_lost", self.res._breakdown)


class TestResiliencyToDict(unittest.TestCase):
    """Test cases for to_dict method."""

    def setUp(self):
        """Set up test fixtures."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump([{"expr": "test", "severity": "critical"}], f)
            self.temp_file = f.name

        self.res = Resiliency(alerts_yaml_path=self.temp_file)

    def tearDown(self):
        """Clean up temp files."""
        if os.path.exists(self.temp_file):
            os.unlink(self.temp_file)

    def test_to_dict_before_calculate_raises_error(self):
        """Test that to_dict raises error if calculate_score not called."""
        with self.assertRaises(RuntimeError):
            self.res.to_dict()

    def test_to_dict_returns_complete_data(self):
        """Test that to_dict returns all expected fields."""
        self.res._results = {"slo_0": True}
        health_checks = {"health1": True}
        self.res.calculate_score(health_check_results=health_checks)

        result = self.res.to_dict()

        self.assertIn("score", result)
        self.assertIn("breakdown", result)
        self.assertIn("slo_results", result)
        self.assertIn("health_check_results", result)
        self.assertEqual(result["slo_results"], {"slo_0": True})
        self.assertEqual(result["health_check_results"], health_checks)


class TestResiliencyScenarioReports(unittest.TestCase):
    """Test cases for scenario-based resiliency evaluation."""

    def setUp(self):
        """Set up test fixtures."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump([
                {"expr": "up == 0", "severity": "critical", "description": "slo1"}
            ], f)
            self.temp_file = f.name

        self.res = Resiliency(alerts_yaml_path=self.temp_file)
        self.mock_prom = Mock()

    def tearDown(self):
        """Clean up temp files."""
        if os.path.exists(self.temp_file):
            os.unlink(self.temp_file)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    @patch('krkn.resiliency.resiliency.calculate_resiliency_score')
    def test_add_scenario_report(self, mock_calc_score, mock_eval_slos):
        """Test adding a scenario report."""
        mock_eval_slos.return_value = {"slo1": True}
        mock_calc_score.return_value = (100, {"passed": 1, "failed": 0, "total_points": 3, "points_lost": 0})

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 1, 0, 0)

        score = self.res.add_scenario_report(
            scenario_name="test_scenario",
            prom_cli=self.mock_prom,
            start_time=start,
            end_time=end,
            weight=1.5,
        )

        self.assertEqual(score, 100)
        self.assertEqual(len(self.res.scenario_reports), 1)
        self.assertEqual(self.res.scenario_reports[0]["name"], "test_scenario")
        self.assertEqual(self.res.scenario_reports[0]["weight"], 1.5)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    def test_finalize_report_calculates_weighted_average(self, mock_eval_slos):
        """Test that finalize_report calculates weighted average correctly."""
        mock_eval_slos.return_value = {"slo1": True}

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 2, 0, 0)

        # Add two scenarios with different scores and weights
        with patch('krkn.resiliency.resiliency.calculate_resiliency_score') as mock_calc:
            mock_calc.return_value = (80, {"passed": 1, "failed": 0, "total_points": 3, "points_lost": 0})
            self.res.add_scenario_report(
                scenario_name="scenario1",
                prom_cli=self.mock_prom,
                start_time=start,
                end_time=end,
                weight=2,
            )

            mock_calc.return_value = (60, {"passed": 0, "failed": 1, "total_points": 3, "points_lost": 3})
            self.res.add_scenario_report(
                scenario_name="scenario2",
                prom_cli=self.mock_prom,
                start_time=start,
                end_time=end,
                weight=1,
            )

        with patch('krkn.resiliency.resiliency.calculate_resiliency_score') as mock_calc:
            mock_calc.return_value = (100, {"passed": 1, "failed": 0})
            self.res.finalize_report(
                prom_cli=self.mock_prom,
                total_start_time=start,
                total_end_time=end,
            )

        # Weighted average: (80*2 + 60*1) / (2+1) = 220/3 = 73.33... = 73
        self.assertEqual(self.res.summary["resiliency_score"], 73)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    def test_finalize_report_populates_summary_and_detailed(self, mock_eval_slos):
        """Test that finalize_report sets summary and detailed_report."""
        mock_eval_slos.return_value = {"slo1": True}

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 1, 0, 0)

        with patch('krkn.resiliency.resiliency.calculate_resiliency_score') as mock_calc:
            mock_calc.return_value = (95, {"passed": 1, "failed": 0, "total_points": 3, "points_lost": 0})
            self.res.add_scenario_report(
                scenario_name="s1",
                prom_cli=self.mock_prom,
                start_time=start,
                end_time=end,
            )
            self.res.finalize_report(
                prom_cli=self.mock_prom,
                total_start_time=start,
                total_end_time=end,
            )

        self.assertIsNotNone(self.res.summary)
        self.assertIn("resiliency_score", self.res.summary)
        self.assertIn("scenarios", self.res.summary)
        self.assertIsNotNone(self.res.detailed_report)
        self.assertIn("scenarios", self.res.detailed_report)

    def test_finalize_report_without_scenarios_raises_error(self):
        """Test that finalize_report raises error if no scenarios added."""
        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 1, 0, 0)

        with self.assertRaises(RuntimeError):
            self.res.finalize_report(
                prom_cli=self.mock_prom,
                total_start_time=start,
                total_end_time=end,
            )

    def test_get_summary_before_finalize_raises_error(self):
        """Test that get_summary raises RuntimeError before finalize_report is called."""
        with self.assertRaises(RuntimeError):
            self.res.get_summary()

    def test_get_detailed_report_before_finalize_raises_error(self):
        """Test that get_detailed_report raises RuntimeError before finalize_report is called."""
        with self.assertRaises(RuntimeError):
            self.res.get_detailed_report()


class TestResiliencyCompactBreakdown(unittest.TestCase):
    """Test cases for compact_breakdown static method."""

    def test_compact_breakdown_with_valid_report(self):
        """Test compact_breakdown with valid report structure."""
        report = {
            "score": 85,
            "breakdown": {
                "passed": 8,
                "failed": 2,
            }
        }

        result = Resiliency.compact_breakdown(report)

        self.assertEqual(result["resiliency_score"], 85)
        self.assertEqual(result["passed_slos"], 8)
        self.assertEqual(result["total_slos"], 10)

    def test_compact_breakdown_with_missing_fields_uses_defaults(self):
        """Test compact_breakdown handles missing fields gracefully."""
        report = {}

        result = Resiliency.compact_breakdown(report)

        self.assertEqual(result["resiliency_score"], 0)
        self.assertEqual(result["passed_slos"], 0)
        self.assertEqual(result["total_slos"], 0)


class TestResiliencyAddScenarioReports(unittest.TestCase):
    """Test cases for the add_scenario_reports method."""

    def setUp(self):
        """Set up test fixtures."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump([
                {"expr": "up == 0", "severity": "critical", "description": "slo1"}
            ], f)
            self.temp_file = f.name

        self.res = Resiliency(alerts_yaml_path=self.temp_file)
        self.mock_prom = Mock()

    def tearDown(self):
        """Clean up temp files."""
        if os.path.exists(self.temp_file):
            os.unlink(self.temp_file)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    @patch('krkn.resiliency.resiliency.calculate_resiliency_score')
    def test_add_scenario_reports_enriches_dict_telemetry(self, mock_calc_score, mock_eval_slos):
        """Test that dict telemetry items are enriched with a resiliency_report."""
        mock_eval_slos.return_value = {"slo1": True}
        mock_calc_score.return_value = (85, {"passed": 1, "failed": 0, "total_points": 3, "points_lost": 0})

        telemetries = [
            {
                "scenario": "pod_scenario",
                "start_timestamp": 1609459200,
                "end_timestamp": 1609462800,
            }
        ]

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 1, 0, 0)

        self.res.add_scenario_reports(
            scenario_telemetries=telemetries,
            prom_cli=self.mock_prom,
            scenario_type="default_type",
            batch_start_dt=start,
            batch_end_dt=end,
            weight=1.5,
        )

        self.assertEqual(len(self.res.scenario_reports), 1)
        self.assertIn("resiliency_report", telemetries[0])
        self.assertIn("resiliency_score", telemetries[0]["resiliency_report"])

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    @patch('krkn.resiliency.resiliency.calculate_resiliency_score')
    def test_add_scenario_reports_uses_batch_times_when_timestamps_missing(self, mock_calc_score, mock_eval_slos):
        """Test that batch times are used when telemetry has no timestamps."""
        mock_eval_slos.return_value = {}
        mock_calc_score.return_value = (0, {"passed": 0, "failed": 0, "total_points": 0, "points_lost": 0})

        telemetries = [{"scenario": "my_scenario"}]
        start = datetime.datetime(2025, 6, 1, 0, 0, 0)
        end = datetime.datetime(2025, 6, 1, 1, 0, 0)

        self.res.add_scenario_reports(
            scenario_telemetries=telemetries,
            prom_cli=self.mock_prom,
            scenario_type="fallback_type",
            batch_start_dt=start,
            batch_end_dt=end,
        )

        # evaluate_slos should have been called with the batch times
        call_kwargs = mock_eval_slos.call_args[1]
        self.assertEqual(call_kwargs["start_time"], start)
        self.assertEqual(call_kwargs["end_time"], end)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    @patch('krkn.resiliency.resiliency.calculate_resiliency_score')
    def test_add_scenario_reports_uses_scenario_name_from_telemetry(self, mock_calc_score, mock_eval_slos):
        """Test that scenario name is taken from telemetry, not the fallback type."""
        mock_eval_slos.return_value = {"slo1": True}
        mock_calc_score.return_value = (100, {"passed": 1, "failed": 0, "total_points": 3, "points_lost": 0})

        telemetries = [{"scenario": "real_scenario_name"}]

        self.res.add_scenario_reports(
            scenario_telemetries=telemetries,
            prom_cli=self.mock_prom,
            scenario_type="fallback_type",
            batch_start_dt=datetime.datetime(2025, 1, 1),
            batch_end_dt=datetime.datetime(2025, 1, 2),
        )

        self.assertEqual(self.res.scenario_reports[0]["name"], "real_scenario_name")


class TestFinalizeAndSave(unittest.TestCase):
    """Test cases for finalize_and_save method."""

    def setUp(self):
        """Set up test fixtures with a pre-populated scenario report."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump([
                {"expr": "up == 0", "severity": "critical", "description": "slo1"}
            ], f)
            self.temp_file = f.name

        self.res = Resiliency(alerts_yaml_path=self.temp_file)
        self.mock_prom = Mock()
        self.start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        self.end = datetime.datetime(2025, 1, 1, 2, 0, 0)

        # Pre-populate a scenario report so finalize_report doesn't raise
        self.res.scenario_reports = [
            {
                "name": "test_scenario",
                "window": {"start": self.start.isoformat(), "end": self.end.isoformat()},
                "score": 90,
                "weight": 1,
                "breakdown": {"total_points": 3, "points_lost": 0, "passed": 1, "failed": 0},
                "slo_results": {"slo1": True},
                "health_check_results": {},
            }
        ]

    def tearDown(self):
        """Clean up temp files."""
        if os.path.exists(self.temp_file):
            os.unlink(self.temp_file)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    def test_finalize_and_save_standalone_writes_detailed_file(self, mock_eval_slos):
        """Test that standalone mode writes a detailed JSON report to the given path."""
        mock_eval_slos.return_value = {"slo1": True}

        with tempfile.TemporaryDirectory() as tmpdir:
            detailed_path = os.path.join(tmpdir, "resiliency-report.json")

            self.res.finalize_and_save(
                prom_cli=self.mock_prom,
                total_start_time=self.start,
                total_end_time=self.end,
                run_mode="standalone",
                detailed_path=detailed_path,
            )

            self.assertTrue(os.path.exists(detailed_path))
            with open(detailed_path) as fp:
                report = json.load(fp)
            self.assertIn("scenarios", report)

    @patch('builtins.print')
    @patch('krkn.resiliency.resiliency.evaluate_slos')
    def test_finalize_and_save_controller_mode_prints_to_stdout(self, mock_eval_slos, mock_print):
        """Test that controller mode prints the detailed report to stdout with the expected prefix."""
        mock_eval_slos.return_value = {"slo1": True}

        self.res.finalize_and_save(
            prom_cli=self.mock_prom,
            total_start_time=self.start,
            total_end_time=self.end,
            run_mode="detailed",
        )

        mock_print.assert_called()
        call_args = str(mock_print.call_args)
        self.assertIn("KRKN_RESILIENCY_REPORT_JSON", call_args)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    def test_finalize_and_save_populates_summary_after_call(self, mock_eval_slos):
        """Test that finalize_and_save populates summary so get_summary works afterward."""
        mock_eval_slos.return_value = {"slo1": True}

        self.res.finalize_and_save(
            prom_cli=self.mock_prom,
            total_start_time=self.start,
            total_end_time=self.end,
        )

        summary = self.res.get_summary()
        self.assertIsNotNone(summary)
        self.assertIn("resiliency_score", summary)


if __name__ == '__main__':
    unittest.main()
