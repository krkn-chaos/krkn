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
    python -m unittest tests.test_resiliency.TestComputeResiliency

    # Run a specific test method
    python -m unittest tests.test_resiliency.TestResiliencyInit.test_init_from_file
    python -m unittest tests.test_resiliency.TestResiliencyScenarioReports.test_add_scenario_report

    # Run with coverage
    python -m coverage run -m unittest tests.test_resiliency
    python -m coverage report -m
"""

import base64
import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open, call

from krkn.resiliency.resiliency import (
    Resiliency,
    compute_resiliency,
    add_scenario_reports,
    finalize_and_save,
)


class TestResiliencyInit(unittest.TestCase):
    """Test cases for Resiliency class initialization."""

    def test_init_from_file(self):
        """Test initialization from alerts.yaml file."""
        # File should contain just the list, not wrapped in a dict
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

    @patch.dict(os.environ, {Resiliency.ENV_VAR_NAME: ''})
    def test_init_from_env_var_plain_yaml(self):
        """Test initialization from environment variable with plain YAML."""
        # Env var can have the "slos" wrapper
        yaml_content = """
slos:
  - expr: "up == 0"
    severity: "critical"
    description: "Test SLO"
"""
        with patch.dict(os.environ, {Resiliency.ENV_VAR_NAME: yaml_content}):
            # When env var is set, it should use that and not try to open file
            # We need to provide a valid file path though
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write('[]')  # Dummy content
                temp_file = f.name

            try:
                res = Resiliency(alerts_yaml_path=temp_file)
                # Should load from env var, not file
                self.assertEqual(len(res._slos), 1)
                self.assertEqual(res._slos[0]["name"], "Test SLO")
            finally:
                os.unlink(temp_file)

    @patch.dict(os.environ, {})
    def test_init_from_env_var_base64_yaml(self):
        """Test initialization from environment variable with base64-encoded YAML."""
        yaml_content = """
slos:
  - expr: "memory > 90"
    severity: "warning"
    description: "High memory"
"""
        encoded = base64.b64encode(yaml_content.encode('utf-8')).decode('utf-8')

        with patch.dict(os.environ, {Resiliency.ENV_VAR_NAME: encoded}):
            with patch('os.path.exists', return_value=True):
                with patch('builtins.open', mock_open(read_data='slos: []')):
                    res = Resiliency()
                    self.assertEqual(len(res._slos), 1)
                    self.assertEqual(res._slos[0]["name"], "High memory")

    @patch.dict(os.environ, {})
    def test_init_from_env_var_invalid_yaml_returns_empty(self):
        """Test that invalid YAML in env var returns empty SLO list."""
        with patch.dict(os.environ, {Resiliency.ENV_VAR_NAME: "invalid: yaml: content:"}):
            with patch('os.path.exists', return_value=True):
                with patch('builtins.open', mock_open(read_data='slos: []')):
                    res = Resiliency()
                    # Should fall back to empty list on YAML error
                    self.assertEqual(len(res._slos), 0)

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
        # Should log warnings for invalid entries
        self.assertEqual(mock_logging.warning.call_count, 3)

    def test_normalise_alerts_with_non_list_raises_error(self):
        """Test _normalise_alerts raises ValueError for non-list input."""
        with self.assertRaises(ValueError):
            Resiliency._normalise_alerts("not a list")

        with self.assertRaises(ValueError):
            Resiliency._normalise_alerts({"key": "value"})


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

    def test_calculate_score_with_custom_weights(self):
        """Test calculate_score with custom severity weights."""
        self.res._results = {"slo1": False, "slo2": True}
        custom_weights = {"critical": 10, "warning": 1}

        score = self.res.calculate_score(weights=custom_weights)

        # Total: 10 + 1 = 11 pts, Lost: 10 pts -> ~9%
        self.assertEqual(score, 9)


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
        mock_calc_score.return_value = (100, {"passed": 1, "failed": 0})

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
        # Mock responses
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

            mock_calc.return_value = (60, {"passed": 0, "failed": 1, "total_points": 3, "points_lost": 1})
            self.res.add_scenario_report(
                scenario_name="scenario2",
                prom_cli=self.mock_prom,
                start_time=start,
                end_time=end,
                weight=1,
            )

        # Finalize
        with patch('krkn.resiliency.resiliency.calculate_resiliency_score') as mock_calc:
            mock_calc.return_value = (100, {"passed": 1, "failed": 0})
            self.res.finalize_report(
                prom_cli=self.mock_prom,
                total_start_time=start,
                total_end_time=end,
            )

        # Weighted average: (80*2 + 60*1) / (2+1) = 220/3 = 73.33... = 73
        self.assertEqual(self.res.summary["resiliency_score"], 73)

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

    def test_get_summary_before_finalize_returns_none(self):
        """Test that get_summary returns None before finalize."""
        # summary is initialized as None in __init__, so hasattr returns True
        # The method won't raise error, just returns None
        result = self.res.get_summary()
        self.assertIsNone(result)

    def test_get_detailed_report_before_finalize_returns_none(self):
        """Test that get_detailed_report returns None before finalize."""
        # detailed_report is initialized as None in __init__
        result = self.res.get_detailed_report()
        self.assertIsNone(result)


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


class TestComputeResiliency(unittest.TestCase):
    """Test cases for compute_resiliency function."""

    @patch('krkn.resiliency.resiliency.Resiliency')
    @patch('krkn.resiliency.resiliency.evaluate_slos')
    def test_compute_resiliency_success(self, mock_eval_slos, mock_resiliency_class):
        """Test successful resiliency computation."""
        # Setup mocks
        mock_prom = Mock()
        mock_telemetry = Mock()
        mock_telemetry.health_checks = []

        mock_res_instance = Mock()
        mock_res_instance._slos = [{"name": "test", "expr": "up", "severity": "critical"}]
        mock_res_instance.to_dict.return_value = {
            "score": 90,
            "breakdown": {"passed": 1, "failed": 0}
        }
        mock_resiliency_class.return_value = mock_res_instance

        mock_eval_slos.return_value = {"test": True}

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 1, 0, 0)

        result = compute_resiliency(
            prometheus=mock_prom,
            chaos_telemetry=mock_telemetry,
            start_time=start,
            end_time=end,
            run_uuid="test-uuid",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["score"], 90)
        self.assertEqual(mock_telemetry.resiliency_score, 90)

    @patch('krkn.resiliency.resiliency.Resiliency')
    def test_compute_resiliency_handles_exception(self, mock_resiliency_class):
        """Test that exceptions are caught and logged."""
        mock_resiliency_class.side_effect = Exception("Test error")

        mock_prom = Mock()
        mock_telemetry = Mock()
        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 1, 0, 0)

        with patch('krkn.resiliency.resiliency.logging') as mock_logging:
            result = compute_resiliency(
                prometheus=mock_prom,
                chaos_telemetry=mock_telemetry,
                start_time=start,
                end_time=end,
            )

        self.assertIsNone(result)
        # Should log error
        mock_logging.getLogger().error.assert_called()


class TestAddScenarioReports(unittest.TestCase):
    """Test cases for add_scenario_reports helper function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_prom = Mock()
        self.mock_res = Mock()
        self.mock_res.scenario_reports = []

    def test_add_scenario_reports_with_dict_telemetry(self):
        """Test adding scenario reports with dict telemetry items."""
        telemetries = [
            {
                "scenario": "pod_scenario",
                "start_timestamp": 1609459200,  # 2021-01-01 00:00:00
                "end_timestamp": 1609462800,    # 2021-01-01 01:00:00
            }
        ]

        self.mock_res.add_scenario_report.return_value = 85
        self.mock_res.scenario_reports.append({
            "score": 85,
            "breakdown": {"passed": 8, "failed": 2}
        })

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 1, 0, 0)

        add_scenario_reports(
            resiliency_obj=self.mock_res,
            scenario_telemetries=telemetries,
            prom_cli=self.mock_prom,
            scenario_type="default_type",
            batch_start_dt=start,
            batch_end_dt=end,
            weight=1.5,
        )

        self.mock_res.add_scenario_report.assert_called_once()
        # Verify resiliency_report was added to telemetry
        self.assertIn("resiliency_report", telemetries[0])

    def test_add_scenario_reports_with_none_resiliency_obj_is_noop(self):
        """Test that passing None resiliency_obj is a no-op."""
        telemetries = [{"scenario": "test"}]

        # Should not raise any errors
        add_scenario_reports(
            resiliency_obj=None,
            scenario_telemetries=telemetries,
            prom_cli=self.mock_prom,
            scenario_type="test",
            batch_start_dt=datetime.datetime.now(),
            batch_end_dt=datetime.datetime.now(),
        )


class TestFinalizeAndSave(unittest.TestCase):
    """Test cases for finalize_and_save function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_prom = Mock()
        self.mock_res = Mock()
        self.start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        self.end = datetime.datetime(2025, 1, 1, 2, 0, 0)

    def test_finalize_and_save_standalone_mode_writes_files(self):
        """Test that standalone mode writes summary and detailed reports to files."""
        summary = {"resiliency_score": 85}
        detailed = {"scenarios": []}

        self.mock_res.get_summary.return_value = summary
        self.mock_res.get_detailed_report.return_value = detailed

        with tempfile.TemporaryDirectory() as tmpdir:
            summary_path = os.path.join(tmpdir, "summary.json")
            detailed_path = os.path.join(tmpdir, "detailed.json")

            result_summary, result_detailed = finalize_and_save(
                resiliency_obj=self.mock_res,
                prom_cli=self.mock_prom,
                total_start_time=self.start,
                total_end_time=self.end,
                run_mode="standalone",
                summary_path=summary_path,
                detailed_path=detailed_path,
            )

            self.assertEqual(result_summary, summary)
            self.assertEqual(result_detailed, detailed)
            self.assertTrue(os.path.exists(summary_path))
            self.assertTrue(os.path.exists(detailed_path))

    @patch('builtins.print')
    def test_finalize_and_save_controller_mode_prints_to_stdout(self, mock_print):
        """Test that controller mode prints detailed report to stdout."""
        detailed = {"scenarios": [{"name": "test", "score": 90}]}

        self.mock_res.get_summary.return_value = {}
        self.mock_res.get_detailed_report.return_value = detailed

        finalize_and_save(
            resiliency_obj=self.mock_res,
            prom_cli=self.mock_prom,
            total_start_time=self.start,
            total_end_time=self.end,
            run_mode="controller",
        )

        # Should print to stdout with special prefix
        mock_print.assert_called()
        call_args = str(mock_print.call_args)
        self.assertIn("KRKN_RESILIENCY_REPORT_JSON", call_args)

    def test_finalize_and_save_with_none_resiliency_obj_returns_empty(self):
        """Test that None resiliency_obj returns empty dicts."""
        summary, detailed = finalize_and_save(
            resiliency_obj=None,
            prom_cli=self.mock_prom,
            total_start_time=self.start,
            total_end_time=self.end,
        )

        self.assertEqual(summary, {})
        self.assertEqual(detailed, {})


if __name__ == '__main__':
    unittest.main()
