#!/usr/bin/env python3

"""
Test suite for PromQL injection prevention in chaos_recommender/prometheus.py

Validates that namespace, scrape_duration, and pod_name inputs are
sanitized before interpolation into PromQL query strings.

Usage:
    python -m unittest tests.test_chaos_recommender_prometheus -v
"""

import importlib.util
import os
import unittest

# Import validators directly to avoid triggering the chaos_recommender
# __init__.py which pulls in pandas/prometheus_api_client.
_validators_path = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "krkn",
        "chaos_recommender",
        "validators.py",
    )
)
_spec = importlib.util.spec_from_file_location("validators", _validators_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load validators module from {_validators_path}")
_validators = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validators)

validate_namespace = _validators.validate_namespace
validate_pod_name = _validators.validate_pod_name
validate_scrape_duration = _validators.validate_scrape_duration


class TestValidateNamespace(unittest.TestCase):
    """Tests for PromQL injection prevention via namespace validation."""

    def test_valid_namespaces(self):
        valid = ["default", "kube-system", "my-namespace", "ns1", "a"]
        for ns in valid:
            validate_namespace(ns)  # should not raise

    def test_injection_closing_brace(self):
        with self.assertRaises(ValueError):
            validate_namespace('default"}[1m]) + sum(something_else{x="')

    def test_injection_special_chars(self):
        with self.assertRaises(ValueError):
            validate_namespace('ns"; drop table')

    def test_empty_string(self):
        with self.assertRaises(ValueError):
            validate_namespace("")

    def test_uppercase_rejected(self):
        with self.assertRaises(ValueError):
            validate_namespace("Default")

    def test_underscores_rejected(self):
        with self.assertRaises(ValueError):
            validate_namespace("my_namespace")

    def test_dots_rejected(self):
        with self.assertRaises(ValueError):
            validate_namespace("my.namespace")

    def test_too_long_rejected(self):
        with self.assertRaises(ValueError):
            validate_namespace("a" * 64)

    def test_max_length_accepted(self):
        validate_namespace("a" * 63)  # should not raise

    def test_starts_with_hyphen_rejected(self):
        with self.assertRaises(ValueError):
            validate_namespace("-invalid")

    def test_ends_with_hyphen_rejected(self):
        with self.assertRaises(ValueError):
            validate_namespace("invalid-")


class TestValidateScrapeDuration(unittest.TestCase):
    """Tests for PromQL injection prevention via scrape_duration validation."""

    def test_valid_durations(self):
        valid = ["5m", "1h", "30s", "7d", "2w", "1y"]
        for d in valid:
            validate_scrape_duration(d)  # should not raise

    def test_injection_attempt(self):
        with self.assertRaises(ValueError):
            validate_scrape_duration('1m]) + sum(evil_metric{x="')

    def test_empty_string(self):
        with self.assertRaises(ValueError):
            validate_scrape_duration("")

    def test_missing_unit(self):
        with self.assertRaises(ValueError):
            validate_scrape_duration("100")

    def test_missing_number(self):
        with self.assertRaises(ValueError):
            validate_scrape_duration("m")

    def test_invalid_unit(self):
        with self.assertRaises(ValueError):
            validate_scrape_duration("5x")

    def test_float_rejected(self):
        with self.assertRaises(ValueError):
            validate_scrape_duration("5.5m")


class TestValidatePodName(unittest.TestCase):
    """Tests for PromQL injection prevention via pod name validation."""

    def test_valid_pod_names(self):
        valid = [
            "nginx-deployment-5d8b6bf8b-abcde",
            "my-pod",
            "pod1",
            "a",
            "my-app.instance-0",
        ]
        for name in valid:
            validate_pod_name(name)  # should not raise

    def test_injection_attempt(self):
        with self.assertRaises(ValueError):
            validate_pod_name('pod-name"})} + vector(1){__name__="')

    def test_empty_string(self):
        with self.assertRaises(ValueError):
            validate_pod_name("")

    def test_uppercase_rejected(self):
        with self.assertRaises(ValueError):
            validate_pod_name("MyPod")

    def test_starts_with_hyphen_rejected(self):
        with self.assertRaises(ValueError):
            validate_pod_name("-invalid-pod")

    def test_ends_with_hyphen_rejected(self):
        with self.assertRaises(ValueError):
            validate_pod_name("invalid-pod-")


if __name__ == "__main__":
    unittest.main()
