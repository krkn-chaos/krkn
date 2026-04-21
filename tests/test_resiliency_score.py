#!/usr/bin/env python
"""
Tests for krkn.resiliency.score module.

How to run these tests:

    # Run all tests in this file
    python -m unittest tests.test_resiliency_score

    # Run all tests with verbose output
    python -m unittest tests.test_resiliency_score -v

    # Run a specific test class
    python -m unittest tests.test_resiliency_score.TestSLOResult
    python -m unittest tests.test_resiliency_score.TestCalculateResiliencyScore

    # Run a specific test method
    python -m unittest tests.test_resiliency_score.TestSLOResult.test_slo_result_initialization
    python -m unittest tests.test_resiliency_score.TestCalculateResiliencyScore.test_all_slos_passing_returns_100

    # Run with coverage
    python -m coverage run -m unittest tests.test_resiliency_score
    python -m coverage report -m
"""

import unittest

from krkn.resiliency.score import (
    SLOResult,
    calculate_resiliency_score,
    DEFAULT_WEIGHTS,
)


class TestSLOResult(unittest.TestCase):
    """Test cases for the SLOResult class."""

    def test_slo_result_initialization(self):
        """Test SLOResult object initialization."""
        slo = SLOResult(name="test_slo", severity="critical", passed=True)
        self.assertEqual(slo.name, "test_slo")
        self.assertEqual(slo.severity, "critical")
        self.assertTrue(slo.passed)

    def test_slo_result_weight_critical_default(self):
        """Test weight calculation for critical SLO with default weights."""
        slo = SLOResult(name="test_slo", severity="critical", passed=True)
        self.assertEqual(slo.weight(DEFAULT_WEIGHTS), DEFAULT_WEIGHTS["critical"])
        self.assertEqual(slo.weight(DEFAULT_WEIGHTS), 3)

    def test_slo_result_weight_warning_default(self):
        """Test weight calculation for warning SLO with default weights."""
        slo = SLOResult(name="test_slo", severity="warning", passed=True)
        self.assertEqual(slo.weight(DEFAULT_WEIGHTS), DEFAULT_WEIGHTS["warning"])
        self.assertEqual(slo.weight(DEFAULT_WEIGHTS), 1)

    def test_slo_result_weight_custom_severity_weights(self):
        """Test weight calculation with custom severity-level weights."""
        custom_weights = {"critical": 5, "warning": 2}
        slo_critical = SLOResult(name="test1", severity="critical", passed=True)
        slo_warning = SLOResult(name="test2", severity="warning", passed=True)

        self.assertEqual(slo_critical.weight(custom_weights), 5)
        self.assertEqual(slo_warning.weight(custom_weights), 2)

    def test_slo_result_weight_unknown_severity_falls_back_to_warning(self):
        """Test that unknown severity falls back to warning weight."""
        slo = SLOResult(name="test_slo", severity="unknown", passed=True)
        self.assertEqual(slo.weight(DEFAULT_WEIGHTS), DEFAULT_WEIGHTS["warning"])

    def test_slo_result_custom_weight_overrides_severity(self):
        """Test that a per-SLO custom weight overrides the severity-based weight."""
        slo = SLOResult(name="test_slo", severity="critical", passed=True, weight=10)
        self.assertEqual(slo.weight(DEFAULT_WEIGHTS), 10)

    def test_slo_result_custom_weight_zero_is_valid(self):
        """Test that a per-SLO weight of 0 is respected."""
        slo = SLOResult(name="test_slo", severity="critical", passed=False, weight=0)
        self.assertEqual(slo.weight(DEFAULT_WEIGHTS), 0)

    def test_slo_result_explicit_none_weight_falls_back_to_severity(self):
        """Test that weight=None explicitly falls back to severity-based weight, not 0."""
        slo = SLOResult(name="test_slo", severity="critical", passed=True, weight=None)
        self.assertEqual(slo.weight(DEFAULT_WEIGHTS), DEFAULT_WEIGHTS["critical"])
        self.assertEqual(slo.weight(DEFAULT_WEIGHTS), 3)

    def test_slo_result_float_custom_weight(self):
        """Test that a fractional custom weight (e.g. 0.5 as documented) is returned as-is."""
        slo = SLOResult(name="test_slo", severity="warning", passed=True, weight=0.5)
        self.assertEqual(slo.weight(DEFAULT_WEIGHTS), 0.5)


class TestCalculateResiliencyScore(unittest.TestCase):
    """Test cases for the calculate_resiliency_score function."""

    def test_all_slos_passing_returns_100(self):
        """Test that all passing SLOs returns score of 100."""
        slo_definitions = {
            "slo1": "critical",
            "slo2": "warning",
        }
        prometheus_results = {
            "slo1": True,
            "slo2": True,
        }
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        self.assertEqual(score, 100)
        self.assertEqual(breakdown["passed"], 2)
        self.assertEqual(breakdown["failed"], 0)
        self.assertEqual(breakdown["points_lost"], 0)

    def test_all_slos_failing_returns_0(self):
        """Test that all failing SLOs returns score of 0."""
        slo_definitions = {
            "slo1": "critical",
            "slo2": "warning",
        }
        prometheus_results = {
            "slo1": False,
            "slo2": False,
        }
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        self.assertEqual(score, 0)
        self.assertEqual(breakdown["passed"], 0)
        self.assertEqual(breakdown["failed"], 2)

    def test_mixed_results_calculates_correct_score(self):
        """Test score calculation with mixed pass/fail results."""
        slo_definitions = {
            "slo_critical": "critical",  # weight=3
            "slo_warning": "warning",    # weight=1
        }
        prometheus_results = {
            "slo_critical": True,   # 3 points
            "slo_warning": False,   # 0 points (lost 1)
        }
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        # Total: 4 points, Lost: 1 point
        # Score: (4-1)/4 * 100 = 75%
        self.assertEqual(score, 75)
        self.assertEqual(breakdown["total_points"], 4)
        self.assertEqual(breakdown["points_lost"], 1)
        self.assertEqual(breakdown["passed"], 1)
        self.assertEqual(breakdown["failed"], 1)

    def test_slo_not_in_prometheus_results_is_excluded(self):
        """Test that SLOs not in prometheus_results are excluded from calculation."""
        slo_definitions = {
            "slo1": "critical",
            "slo2": "warning",
            "slo3": "critical",  # Not in prometheus_results
        }
        prometheus_results = {
            "slo1": True,
            "slo2": True,
            # slo3 is missing (no data)
        }
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        # Only slo1 and slo2 should be counted
        self.assertEqual(score, 100)
        self.assertEqual(breakdown["passed"], 2)
        self.assertEqual(breakdown["failed"], 0)

    def test_health_checks_are_treated_as_critical(self):
        """Test that health checks are always weighted as critical."""
        slo_definitions = {}
        prometheus_results = {}
        health_check_results = {
            "http://service1": True,
            "http://service2": False,
        }

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        # 2 health checks, each critical (weight=3)
        # Total: 6 points, Lost: 3 points (one failed)
        # Score: (6-3)/6 * 100 = 50%
        self.assertEqual(score, 50)
        self.assertEqual(breakdown["total_points"], 6)
        self.assertEqual(breakdown["points_lost"], 3)

    def test_combined_slos_and_health_checks(self):
        """Test calculation with both SLOs and health checks."""
        slo_definitions = {
            "slo1": "warning",  # weight=1
        }
        prometheus_results = {
            "slo1": True,
        }
        health_check_results = {
            "health1": True,  # weight=3 (critical)
            "health2": False, # weight=3 (critical)
        }

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        # Total: 1 + 3 + 3 = 7 points
        # Lost: 3 points (health2 failed)
        # Score: (7-3)/7 * 100 = 57.14... = 57%
        self.assertEqual(score, 57)
        self.assertEqual(breakdown["total_points"], 7)
        self.assertEqual(breakdown["points_lost"], 3)
        self.assertEqual(breakdown["passed"], 2)
        self.assertEqual(breakdown["failed"], 1)

    def test_per_slo_custom_weight_overrides_severity(self):
        """Test that per-SLO custom weight in extended format overrides default severity weight."""
        slo_definitions = {
            "slo1": {"severity": "critical", "weight": 10},
        }
        prometheus_results = {
            "slo1": False,
        }
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        self.assertEqual(breakdown["total_points"], 10)
        self.assertEqual(breakdown["points_lost"], 10)
        self.assertEqual(score, 0)

    def test_extended_format_mixed_with_legacy_format(self):
        """Test that extended dict format and legacy string format can be mixed."""
        slo_definitions = {
            "slo_custom": {"severity": "warning", "weight": 5},  # custom weight
            "slo_legacy": "critical",                             # legacy, weight=3
        }
        prometheus_results = {
            "slo_custom": False,  # loses 5 pts
            "slo_legacy": True,   # keeps 3 pts
        }
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        # Total: 5 + 3 = 8, Lost: 5
        # Score: (8-5)/8 * 100 = 37.5 -> 37
        self.assertEqual(breakdown["total_points"], 8)
        self.assertEqual(breakdown["points_lost"], 5)
        self.assertEqual(score, 37)

    def test_extended_format_weight_none_falls_back_to_severity(self):
        """Test that weight=None in extended dict format falls back to severity-based weight."""
        slo_definitions = {
            "slo1": {"severity": "critical", "weight": None},  # should use default critical weight=3
        }
        prometheus_results = {"slo1": False}
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        # weight falls back to critical=3
        self.assertEqual(breakdown["total_points"], 3)
        self.assertEqual(breakdown["points_lost"], 3)
        self.assertEqual(score, 0)

    def test_float_custom_weight_scoring(self):
        """Test scoring with fractional weights as documented (e.g. weight: 0.5)."""
        slo_definitions = {
            "slo_high":  {"severity": "critical", "weight": 10},
            "slo_low":   {"severity": "warning",  "weight": 0.5},
        }
        prometheus_results = {
            "slo_high": True,   # keeps 10 pts
            "slo_low":  False,  # loses 0.5 pts
        }
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        # Total: 10.5, Lost: 0.5 -> (10/10.5)*100 = 95.23... -> 95
        self.assertEqual(breakdown["total_points"], 10.5)
        self.assertEqual(breakdown["points_lost"], 0.5)
        self.assertEqual(score, 95)

    def test_failed_slo_with_zero_weight_does_not_affect_score(self):
        """Test that a failing SLO with weight=0 contributes nothing to points_lost."""
        slo_definitions = {
            "slo_zero":   {"severity": "critical", "weight": 0},
            "slo_normal": "warning",  # weight=1
        }
        prometheus_results = {
            "slo_zero":   False,  # fails but contributes 0 pts
            "slo_normal": True,
        }
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        self.assertEqual(breakdown["total_points"], 1)
        self.assertEqual(breakdown["points_lost"], 0)
        self.assertEqual(score, 100)

    def test_all_custom_weight_slos_passing_returns_100(self):
        """Test that all custom-weight SLOs passing returns 100 regardless of weight values."""
        slo_definitions = {
            "slo1": {"severity": "critical", "weight": 20},
            "slo2": {"severity": "warning",  "weight": 5},
            "slo3": {"severity": "critical", "weight": 0.5},
        }
        prometheus_results = {"slo1": True, "slo2": True, "slo3": True}
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        self.assertEqual(score, 100)
        self.assertEqual(breakdown["points_lost"], 0)
        self.assertEqual(breakdown["passed"], 3)
        self.assertEqual(breakdown["failed"], 0)

    def test_empty_slo_definitions_returns_zero_score(self):
        """Test that empty SLO definitions returns score of 0."""
        score, breakdown = calculate_resiliency_score(
            slo_definitions={},
            prometheus_results={},
            health_check_results={}
        )

        self.assertEqual(score, 0)
        self.assertEqual(breakdown["total_points"], 0)
        self.assertEqual(breakdown["points_lost"], 0)
        self.assertEqual(breakdown["passed"], 0)
        self.assertEqual(breakdown["failed"], 0)

    def test_prometheus_results_coerced_to_bool(self):
        """Test that prometheus results are properly coerced to boolean."""
        slo_definitions = {
            "slo1": "warning",
            "slo2": "warning",
            "slo3": "warning",
        }
        prometheus_results = {
            "slo1": 1,      # Truthy
            "slo2": 0,      # Falsy
            "slo3": None,   # Falsy
        }
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        # slo1 passes (1 point), slo2 and slo3 fail (0 points each)
        # Total: 3 points, Lost: 2 points
        # Score: (3-2)/3 * 100 = 33.33... = 33%
        self.assertEqual(score, 33)
        self.assertEqual(breakdown["passed"], 1)
        self.assertEqual(breakdown["failed"], 2)

    def test_score_calculation_rounds_down(self):
        """Test that score calculation rounds down to integer."""
        slo_definitions = {
            "slo1": "critical",  # 3 points
            "slo2": "critical",  # 3 points
            "slo3": "critical",  # 3 points
        }
        prometheus_results = {
            "slo1": True,   # 3 points
            "slo2": True,   # 3 points
            "slo3": False,  # 0 points (lost 3)
        }
        health_check_results = {}

        score, breakdown = calculate_resiliency_score(
            slo_definitions, prometheus_results, health_check_results
        )

        # Total: 9 points, Lost: 3 points
        # Score: (9-3)/9 * 100 = 66.666... -> 66
        self.assertEqual(score, 66)


if __name__ == '__main__':
    unittest.main()
