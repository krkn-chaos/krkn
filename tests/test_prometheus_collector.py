"""
Tests for krkn.prometheus.collector module.

How to run these tests:

    # Run all tests in this file
    python -m unittest tests.test_prometheus_collector

    # Run all tests with verbose output
    python -m unittest tests.test_prometheus_collector -v

    # Run a specific test class
    python -m unittest tests.test_prometheus_collector.TestSLOPassed
    python -m unittest tests.test_prometheus_collector.TestEvaluateSLOs

    # Run a specific test method
    python -m unittest tests.test_prometheus_collector.TestSLOPassed.test_empty_result_returns_none
    python -m unittest tests.test_prometheus_collector.TestEvaluateSLOs.test_evaluate_single_slo_passing

    # Run with coverage
    python -m coverage run -m unittest tests.test_prometheus_collector
    python -m coverage report -m
"""

import datetime
import unittest
from unittest.mock import Mock, patch, MagicMock

from krkn.prometheus.collector import slo_passed, evaluate_slos


class TestSLOPassed(unittest.TestCase):
    """Test cases for the slo_passed function."""

    def test_empty_result_returns_none(self):
        """Test that an empty result list returns None."""
        result = slo_passed([])
        self.assertIsNone(result)

    def test_result_with_values_all_zero_returns_true(self):
        """Test that all zero values in 'values' returns True."""
        prometheus_result = [
            {
                "values": [
                    [1234567890, "0"],
                    [1234567891, "0"],
                    [1234567892, "0"],
                ]
            }
        ]
        result = slo_passed(prometheus_result)
        self.assertTrue(result)

    def test_result_with_values_containing_nonzero_returns_false(self):
        """Test that any non-zero value in 'values' returns False."""
        prometheus_result = [
            {
                "values": [
                    [1234567890, "0"],
                    [1234567891, "1.5"],  # Non-zero value
                    [1234567892, "0"],
                ]
            }
        ]
        result = slo_passed(prometheus_result)
        self.assertFalse(result)

    def test_result_with_single_value_zero_returns_true(self):
        """Test that a single 'value' field with zero returns True."""
        prometheus_result = [
            {
                "value": [1234567890, "0"]
            }
        ]
        result = slo_passed(prometheus_result)
        self.assertTrue(result)

    def test_result_with_single_value_nonzero_returns_false(self):
        """Test that a single 'value' field with non-zero returns False."""
        prometheus_result = [
            {
                "value": [1234567890, "5.2"]
            }
        ]
        result = slo_passed(prometheus_result)
        self.assertFalse(result)

    def test_result_with_no_samples_returns_none(self):
        """Test that result with no 'values' or 'value' keys returns None."""
        prometheus_result = [
            {
                "metric": {"job": "test"}
            }
        ]
        result = slo_passed(prometheus_result)
        self.assertIsNone(result)

    def test_result_with_invalid_value_type_in_values(self):
        """Test handling of invalid value types in 'values' field."""
        prometheus_result = [
            {
                "values": [
                    [1234567890, "invalid"],  # Will raise ValueError
                    [1234567891, "0"],
                ]
            }
        ]
        # Should continue processing after ValueError and find the zero
        result = slo_passed(prometheus_result)
        self.assertTrue(result)

    def test_result_with_invalid_value_in_single_value_returns_false(self):
        """Test that invalid value type in 'value' field returns False."""
        prometheus_result = [
            {
                "value": [1234567890, "invalid"]
            }
        ]
        result = slo_passed(prometheus_result)
        self.assertFalse(result)

    def test_result_with_none_value_in_values(self):
        """Test handling of None values in 'values' field."""
        prometheus_result = [
            {
                "values": [
                    [1234567890, None],  # Will raise TypeError
                    [1234567891, "0"],
                ]
            }
        ]
        # Should continue processing after TypeError and find the zero
        result = slo_passed(prometheus_result)
        self.assertTrue(result)

    def test_result_with_multiple_series_first_has_nonzero(self):
        """Test that first non-zero value in any series returns False immediately."""
        prometheus_result = [
            {
                "values": [
                    [1234567890, "0"],
                    [1234567891, "2.0"],  # Non-zero in first series
                ]
            },
            {
                "values": [
                    [1234567890, "0"],
                    [1234567891, "0"],
                ]
            }
        ]
        result = slo_passed(prometheus_result)
        self.assertFalse(result)

    def test_result_with_float_zero(self):
        """Test that float zero is handled correctly."""
        prometheus_result = [
            {
                "values": [
                    [1234567890, "0.0"],
                    [1234567891, "0.00"],
                ]
            }
        ]
        result = slo_passed(prometheus_result)
        self.assertTrue(result)

    def test_result_with_scientific_notation(self):
        """Test values in scientific notation."""
        prometheus_result = [
            {
                "values": [
                    [1234567890, "0e0"],
                    [1234567891, "1e-10"],  # Very small but non-zero
                ]
            }
        ]
        result = slo_passed(prometheus_result)
        self.assertFalse(result)


class TestEvaluateSLOs(unittest.TestCase):
    """Test cases for the evaluate_slos function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_prom_cli = Mock()
        self.start_time = datetime.datetime(2025, 1, 1, 0, 0, 0)
        self.end_time = datetime.datetime(2025, 1, 1, 1, 0, 0)

    def test_evaluate_single_slo_passing(self):
        """Test evaluation of a single passing SLO."""
        slo_list = [
            {
                "name": "test_slo",
                "expr": "sum(rate(http_requests_total[5m]))"
            }
        ]

        # Mock the Prometheus response with all zeros (passing)
        self.mock_prom_cli.process_prom_query_in_range.return_value = [
            {
                "values": [
                    [1234567890, "0"],
                    [1234567891, "0"],
                ]
            }
        ]

        results = evaluate_slos(
            self.mock_prom_cli,
            slo_list,
            self.start_time,
            self.end_time
        )

        self.assertEqual(results["test_slo"], True)
        self.mock_prom_cli.process_prom_query_in_range.assert_called_once_with(
            "sum(rate(http_requests_total[5m]))",
            start_time=self.start_time,
            end_time=self.end_time,
        )

    def test_evaluate_single_slo_failing(self):
        """Test evaluation of a single failing SLO."""
        slo_list = [
            {
                "name": "test_slo",
                "expr": "sum(rate(errors[5m]))"
            }
        ]

        # Mock the Prometheus response with non-zero value (failing)
        self.mock_prom_cli.process_prom_query_in_range.return_value = [
            {
                "values": [
                    [1234567890, "0"],
                    [1234567891, "5"],  # Non-zero indicates failure
                ]
            }
        ]

        results = evaluate_slos(
            self.mock_prom_cli,
            slo_list,
            self.start_time,
            self.end_time
        )

        self.assertEqual(results["test_slo"], False)

    def test_evaluate_slo_with_no_data_returns_true(self):
        """Test that SLO with no data (None) is treated as passing."""
        slo_list = [
            {
                "name": "test_slo",
                "expr": "absent(metric)"
            }
        ]

        # Mock the Prometheus response with no samples
        self.mock_prom_cli.process_prom_query_in_range.return_value = []

        results = evaluate_slos(
            self.mock_prom_cli,
            slo_list,
            self.start_time,
            self.end_time
        )

        # No data should be treated as passing
        self.assertEqual(results["test_slo"], True)

    def test_evaluate_slo_query_exception_returns_false(self):
        """Test that an exception during query results in False."""
        slo_list = [
            {
                "name": "test_slo",
                "expr": "invalid_query"
            }
        ]

        # Mock the Prometheus client to raise an exception
        self.mock_prom_cli.process_prom_query_in_range.side_effect = Exception("Query failed")

        with patch('krkn.prometheus.collector.logging') as mock_logging:
            results = evaluate_slos(
                self.mock_prom_cli,
                slo_list,
                self.start_time,
                self.end_time
            )

        # Exception should result in False
        self.assertEqual(results["test_slo"], False)
        mock_logging.error.assert_called_once()

    def test_evaluate_multiple_slos(self):
        """Test evaluation of multiple SLOs with mixed results."""
        slo_list = [
            {
                "name": "slo_pass",
                "expr": "query1"
            },
            {
                "name": "slo_fail",
                "expr": "query2"
            },
            {
                "name": "slo_no_data",
                "expr": "query3"
            }
        ]

        # Mock different responses for each query
        def mock_query_side_effect(expr, start_time, end_time):
            if expr == "query1":
                return [{"values": [[1234567890, "0"]]}]
            elif expr == "query2":
                return [{"values": [[1234567890, "1"]]}]
            else:  # query3
                return []

        self.mock_prom_cli.process_prom_query_in_range.side_effect = mock_query_side_effect

        results = evaluate_slos(
            self.mock_prom_cli,
            slo_list,
            self.start_time,
            self.end_time
        )

        self.assertEqual(results["slo_pass"], True)
        self.assertEqual(results["slo_fail"], False)
        self.assertEqual(results["slo_no_data"], True)
        self.assertEqual(len(results), 3)

    def test_evaluate_empty_slo_list(self):
        """Test evaluation with an empty SLO list."""
        slo_list = []

        results = evaluate_slos(
            self.mock_prom_cli,
            slo_list,
            self.start_time,
            self.end_time
        )

        self.assertEqual(results, {})
        self.mock_prom_cli.process_prom_query_in_range.assert_not_called()

    @patch('krkn.prometheus.collector.logging')
    def test_evaluate_slos_logs_info_message(self, mock_logging):
        """Test that evaluation logs an info message with SLO count."""
        slo_list = [
            {"name": "slo1", "expr": "query1"},
            {"name": "slo2", "expr": "query2"},
        ]

        self.mock_prom_cli.process_prom_query_in_range.return_value = [
            {"values": [[1234567890, "0"]]}
        ]

        evaluate_slos(
            self.mock_prom_cli,
            slo_list,
            self.start_time,
            self.end_time
        )

        # Check that info logging was called with the expected message
        mock_logging.info.assert_called_once()
        call_args = mock_logging.info.call_args[0]
        self.assertIn("Evaluating %d SLOs", call_args[0])
        self.assertEqual(call_args[1], 2)

    @patch('krkn.prometheus.collector.logging')
    def test_evaluate_slos_logs_debug_for_no_data(self, mock_logging):
        """Test that no data scenario logs a debug message."""
        slo_list = [
            {"name": "test_slo", "expr": "query"}
        ]

        self.mock_prom_cli.process_prom_query_in_range.return_value = []

        evaluate_slos(
            self.mock_prom_cli,
            slo_list,
            self.start_time,
            self.end_time
        )

        # Check that debug logging was called
        mock_logging.debug.assert_called_once()
        call_args = mock_logging.debug.call_args[0]
        self.assertIn("no data", call_args[0])
        self.assertIn("test_slo", call_args[1])


if __name__ == '__main__':
    unittest.main()
