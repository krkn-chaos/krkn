#!/usr/bin/env python
"""
Tests for weight validation in weighted scenario config parsing and resiliency scoring.

These tests ensure that invalid weights (zero, negative, non-numeric) are handled gracefully
and don't cause crashes (ZeroDivisionError, TypeError, etc.).

How to run:
    python -m unittest tests.test_weight_validation -v
"""

import datetime
import logging
import tempfile
import unittest
from unittest.mock import Mock, patch

from krkn.resiliency.resiliency import Resiliency
from krkn.scenario_config_parser import parse_scenario_config


class TestWeightValidation(unittest.TestCase):
    """Test weight validation for config parsing."""

    def test_zero_weight_defaults_to_1(self):
        """Weight of 0 should default to 1 to avoid division by zero."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": 0,
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 1)  # Should default to 1, not 0

    def test_negative_weight_defaults_to_1(self):
        """Negative weight should default to 1."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": -5,
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 1)  # Should default to 1

    def test_string_weight_defaults_to_1(self):
        """Non-numeric string weight should default to 1."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": "invalid",
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 1)  # Should default to 1

    def test_numeric_string_weight_converts_to_float(self):
        """Numeric string weight should be converted to float."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": "3",
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 3.0)

    def test_none_weight_defaults_to_1(self):
        """None weight should default to 1."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": None,
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 1)

    def test_list_weight_defaults_to_1(self):
        """List weight (invalid type) should default to 1."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": [1, 2, 3],
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 1)

    def test_dict_weight_defaults_to_1(self):
        """Dict weight (invalid type) should default to 1."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": {"value": 3},
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 1)

    def test_very_small_positive_weight_accepted(self):
        """Very small positive weight (0.001) should be accepted."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": 0.001,
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 0.001)

    def test_very_large_weight_accepted(self):
        """Very large weight (1000) should be accepted."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": 1000,
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 1000)


class TestResiliencyWeightValidation(unittest.TestCase):
    """Test weight validation in the Resiliency class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a minimal alerts file
        alerts_data = [
            {"expr": "up == 0", "severity": "critical", "description": "Instance down"},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(alerts_data, f)
            self.temp_file = f.name

        self.res = Resiliency(alerts_yaml_path=self.temp_file)
        self.mock_prom = Mock()

        # Suppress logging during tests
        logging.disable(logging.WARNING)

    def tearDown(self):
        """Clean up."""
        import os
        os.unlink(self.temp_file)
        logging.disable(logging.NOTSET)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    @patch('krkn.resiliency.resiliency.calculate_resiliency_score')
    def test_add_scenario_report_zero_weight_defaults_to_1(self, mock_calc, mock_eval):
        """add_scenario_report with weight=0 should default to 1."""
        mock_eval.return_value = {"slo1": True}
        mock_calc.return_value = (100, {"passed": 1, "failed": 0})

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 2, 0, 0)

        score = self.res.add_scenario_report(
            scenario_name="test_scenario",
            prom_cli=self.mock_prom,
            start_time=start,
            end_time=end,
            weight=0,  # Invalid weight
        )

        # Check that weight was defaulted to 1
        self.assertEqual(self.res.scenario_reports[0]["weight"], 1)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    @patch('krkn.resiliency.resiliency.calculate_resiliency_score')
    def test_add_scenario_report_negative_weight_defaults_to_1(self, mock_calc, mock_eval):
        """add_scenario_report with negative weight should default to 1."""
        mock_eval.return_value = {"slo1": True}
        mock_calc.return_value = (100, {"passed": 1, "failed": 0})

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 2, 0, 0)

        score = self.res.add_scenario_report(
            scenario_name="test_scenario",
            prom_cli=self.mock_prom,
            start_time=start,
            end_time=end,
            weight=-5,  # Invalid weight
        )

        self.assertEqual(self.res.scenario_reports[0]["weight"], 1)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    @patch('krkn.resiliency.resiliency.calculate_resiliency_score')
    def test_add_scenario_report_string_weight_defaults_to_1(self, mock_calc, mock_eval):
        """add_scenario_report with string weight should default to 1."""
        mock_eval.return_value = {"slo1": True}
        mock_calc.return_value = (100, {"passed": 1, "failed": 0})

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 2, 0, 0)

        score = self.res.add_scenario_report(
            scenario_name="test_scenario",
            prom_cli=self.mock_prom,
            start_time=start,
            end_time=end,
            weight="invalid",  # Invalid weight
        )

        self.assertEqual(self.res.scenario_reports[0]["weight"], 1)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    @patch('krkn.resiliency.resiliency.calculate_resiliency_score')
    def test_finalize_with_all_zero_weights_uses_simple_average(self, mock_calc, mock_eval):
        """finalize_report with all zero weights should fall back to simple average."""
        mock_eval.return_value = {"slo1": True}

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 2, 0, 0)

        # Add scenarios that all have weight 0 (which get defaulted to 1 by validation)
        # But let's test if someone bypasses validation
        mock_calc.return_value = (80, {"passed": 1, "failed": 0})
        self.res.add_scenario_report(
            scenario_name="scenario1",
            prom_cli=self.mock_prom,
            start_time=start,
            end_time=end,
            weight=1,
        )

        # Manually corrupt the weight to test fallback
        self.res.scenario_reports[0]["weight"] = 0

        mock_calc.return_value = (60, {"passed": 0, "failed": 1})
        self.res.add_scenario_report(
            scenario_name="scenario2",
            prom_cli=self.mock_prom,
            start_time=start,
            end_time=end,
            weight=1,
        )
        self.res.scenario_reports[1]["weight"] = 0

        # This should not crash, should use simple average
        mock_calc.return_value = (100, {"passed": 1, "failed": 0})
        self.res.finalize_report(
            prom_cli=self.mock_prom,
            total_start_time=start,
            total_end_time=end,
        )

        # Simple average: (80 + 60) / 2 = 70
        self.assertEqual(self.res.summary["resiliency_score"], 70)

    @patch('krkn.resiliency.resiliency.evaluate_slos')
    @patch('krkn.resiliency.resiliency.calculate_resiliency_score')
    def test_finalize_with_valid_weights_uses_weighted_average(self, mock_calc, mock_eval):
        """finalize_report with valid weights should use weighted average."""
        mock_eval.return_value = {"slo1": True}

        start = datetime.datetime(2025, 1, 1, 0, 0, 0)
        end = datetime.datetime(2025, 1, 1, 2, 0, 0)

        mock_calc.return_value = (80, {"passed": 1, "failed": 0})
        self.res.add_scenario_report(
            scenario_name="scenario1",
            prom_cli=self.mock_prom,
            start_time=start,
            end_time=end,
            weight=3,
        )

        mock_calc.return_value = (60, {"passed": 0, "failed": 1})
        self.res.add_scenario_report(
            scenario_name="scenario2",
            prom_cli=self.mock_prom,
            start_time=start,
            end_time=end,
            weight=1,
        )

        mock_calc.return_value = (100, {"passed": 1, "failed": 0})
        self.res.finalize_report(
            prom_cli=self.mock_prom,
            total_start_time=start,
            total_end_time=end,
        )

        # Weighted average: (80*3 + 60*1) / (3+1) = 300/4 = 75
        self.assertEqual(self.res.summary["resiliency_score"], 75)


if __name__ == '__main__':
    unittest.main()
