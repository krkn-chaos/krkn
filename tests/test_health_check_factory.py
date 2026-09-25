#!/usr/bin/env python3
"""
Test suite for the Health Check Factory.

Usage:
    python -m unittest tests/test_health_check_factory.py -v
    python -m coverage run -a -m unittest tests/test_health_check_factory.py -v
"""

import logging
import queue
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from krkn.health_checks import HealthCheckFactory, HealthCheckPluginNotFound


class TestHealthCheckFactory(unittest.TestCase):

    def setUp(self):
        self.factory = HealthCheckFactory()

    def test_factory_loads_plugins(self):
        """Factory initialises without error and populates loaded_plugins."""
        self.assertIsNotNone(self.factory.loaded_plugins)

    def test_expected_plugins_are_loaded(self):
        """simple_health_check and test_health_check are present by default."""
        for plugin_type in ["simple_health_check", "test_health_check"]:
            self.assertIn(plugin_type, self.factory.loaded_plugins,
                          f"Expected plugin '{plugin_type}' was not loaded")

    def test_create_simple_health_check_plugin(self):
        """Factory creates a SimpleHealthCheckPlugin with correct attributes."""
        plugin = self.factory.create_plugin("simple_health_check", iterations=5)
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.iterations, 5)
        self.assertEqual(plugin.current_iterations, 0)
        self.assertEqual(plugin.get_return_value(), 0)

    def test_plugin_not_found_raises(self):
        """Requesting an unknown plugin type raises HealthCheckPluginNotFound."""
        with self.assertRaises(HealthCheckPluginNotFound):
            self.factory.create_plugin("nonexistent_plugin_type")

    def test_multiple_types_map_to_same_plugin_class(self):
        """simple_health_check and test_health_check resolve to the same class."""
        plugin1 = self.factory.create_plugin("simple_health_check", iterations=1)
        plugin2 = self.factory.create_plugin("test_health_check", iterations=1)
        self.assertEqual(plugin1.__class__.__name__, plugin2.__class__.__name__)

    def test_increment_iterations(self):
        """increment_iterations advances the counter by one."""
        plugin = self.factory.create_plugin("simple_health_check", iterations=3)
        initial = plugin.current_iterations
        plugin.increment_iterations()
        self.assertEqual(plugin.current_iterations, initial + 1)

    def test_set_and_get_return_value(self):
        """set_return_value / get_return_value round-trip correctly."""
        plugin = self.factory.create_plugin("simple_health_check", iterations=1)
        plugin.set_return_value(2)
        self.assertEqual(plugin.get_return_value(), 2)
        plugin.set_return_value(0)
        self.assertEqual(plugin.get_return_value(), 0)

    def test_run_health_check_with_empty_config(self):
        """run_health_check does not raise when config is empty."""
        plugin = self.factory.create_plugin("simple_health_check", iterations=1)
        telemetry_queue = queue.Queue()
        plugin.run_health_check({}, telemetry_queue)  # must not raise

    def test_http_plugin_loaded(self):
        """http_health_check plugin is present (requests is available)."""
        if "http_health_check" not in self.factory.loaded_plugins:
            self.skipTest("http_health_check plugin not loaded (missing dependencies)")
        self.assertIn("http_health_check", self.factory.loaded_plugins)

    def test_create_http_plugin(self):
        """Factory creates an HttpHealthCheckPlugin with the requested iteration count."""
        if "http_health_check" not in self.factory.loaded_plugins:
            self.skipTest("http_health_check plugin not loaded (missing dependencies)")
        plugin = self.factory.create_plugin("http_health_check", iterations=10)
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.iterations, 10)
        self.assertEqual(plugin.__class__.__name__, "HttpHealthCheckPlugin")

    def test_simple_plugin_run_once(self):
        """SimpleHealthCheckPlugin run_once returns expected structure."""
        plugin = self.factory.create_plugin("simple_health_check", iterations=1)
        result = plugin.run_once({})

        self.assertIn("passed", result)
        self.assertIn("failures", result)
        self.assertIn("details", result)
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["failures"]), 0)

    def test_http_plugin_run_once_no_config(self):
        """HttpHealthCheckPlugin run_once with no config returns passed."""
        if "http_health_check" not in self.factory.loaded_plugins:
            self.skipTest("http_health_check plugin not loaded (missing dependencies)")

        plugin = self.factory.create_plugin("http_health_check", iterations=1)
        result = plugin.run_once({})

        self.assertIn("passed", result)
        self.assertIn("failures", result)
        self.assertIn("details", result)
        self.assertTrue(result["passed"])

    def test_run_all_once_with_no_config(self):
        """run_all_once with empty config returns passed with no checks."""
        result = self.factory.run_all_once({}, check_type="pre")

        self.assertIn("passed", result)
        self.assertIn("failures", result)
        self.assertIn("details", result)
        self.assertIn("summary", result)
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["failures"]), 0)

    def test_run_all_once_with_simple_config(self):
        """run_all_once with simple_health_checks config runs the check when run_during includes timing."""
        config = {
            "simple_health_checks": {
                "test": "value",
                "run_during": "pre"  # This check should run at pre timing
            }
        }
        result = self.factory.run_all_once(config, check_type="pre")

        self.assertIn("passed", result)
        self.assertIn("simple_health_checks", result["details"])
        self.assertTrue(result["passed"])
        self.assertTrue(result["details"]["simple_health_checks"]["passed"])

    def test_run_all_once_summary_format(self):
        """run_all_once summary contains expected text."""
        config = {
            "simple_health_checks": {
                "test": "value",
                "run_during": "pre"
            }
        }
        result = self.factory.run_all_once(config, check_type="pre")

        # Check the summary contains expected components
        self.assertIn("health check results", result["summary"])
        self.assertIn("simple_health_checks", result["summary"])
        self.assertIn("All checks passed", result["summary"])

    def test_run_all_once_can_select_config_keys(self):
        """Deferred evaluation can run only the requested health-check config."""
        config = {
            "simple_health_checks": {"test": "value", "run_during": "during"},
            "performance_monitoring": {
                "enable_alerts": False,
                "run_during": "during",
            },
        }

        result = self.factory.run_all_once(
            config,
            check_type="during",
            config_keys={"performance_monitoring"},
        )

        self.assertIn("performance_monitoring", result["details"])
        self.assertNotIn("simple_health_checks", result["details"])

    def test_run_during_list_support(self):
        """run_during can accept a list of timings."""
        config = {
            "simple_health_checks": {
                "test": "value",
                "run_during": ["pre", "post"]  # Should run at both pre and post
            }
        }

        # Should run at pre
        pre_result = self.factory.run_all_once(config, check_type="pre")
        self.assertIn("simple_health_checks", pre_result["details"])

        # Should run at post
        post_result = self.factory.run_all_once(config, check_type="post")
        self.assertIn("simple_health_checks", post_result["details"])

    def test_run_during_skips_wrong_timing(self):
        """Health check configured for 'post' doesn't run at 'pre'."""
        config = {
            "simple_health_checks": {
                "test": "value",
                "run_during": "post"  # Only post
            }
        }

        # Should NOT run at pre
        pre_result = self.factory.run_all_once(config, check_type="pre")
        self.assertNotIn("simple_health_checks", pre_result["details"])

        # Should run at post
        post_result = self.factory.run_all_once(config, check_type="post")
        self.assertIn("simple_health_checks", post_result["details"])

    def test_run_during_blank_skips_health_check(self):
        """Blank run_during strings and lists disable a health check."""
        for run_during in ("", "   ", []):
            with self.subTest(run_during=run_during):
                config = {
                    "simple_health_checks": {
                        "test": "value",
                        "run_during": run_during
                    }
                }

                pre_result = self.factory.run_all_once(config, check_type="pre")
                during_result = self.factory.start_all(config, iterations=1)

                self.assertNotIn("simple_health_checks", pre_result["details"])
                self.assertEqual(during_result, [])

    def test_run_during_default_behavior(self):
        """Health checks without run_during default to 'during' and don't run at pre/post."""
        config = {
            "simple_health_checks": {
                "test": "value"
                # No run_during specified - defaults to "during"
            }
        }

        # Should NOT run at pre
        pre_result = self.factory.run_all_once(config, check_type="pre")
        self.assertNotIn("simple_health_checks", pre_result["details"])

        # Should NOT run at post
        post_result = self.factory.run_all_once(config, check_type="post")
        self.assertNotIn("simple_health_checks", post_result["details"])

    def test_exit_on_failure_tracking(self):
        """exit_on_failure is tracked in run_all_once results."""
        config = {
            "simple_health_checks": {
                "test": "value",
                "run_during": "pre",
                "exit_on_failure": True
            }
        }

        result = self.factory.run_all_once(config, check_type="pre")
        self.assertTrue(result.get("exit_on_failure", False))


if __name__ == "__main__":
    unittest.main()
