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


class TestStartAllSkipsUnrunnablePlugins(unittest.TestCase):
    """A plugin that cannot run must not be started, nor reported as started."""

    def setUp(self):
        self.factory = HealthCheckFactory()

    def test_can_run_defaults_to_true(self):
        """The base class opts every plugin in, so existing plugins are unaffected."""
        plugin = self.factory.create_plugin("simple_health_check", iterations=1)
        self.assertTrue(plugin.can_run({}))

    def test_http_plugin_cannot_run_without_a_url(self):
        """A health_checks section with no url is not enough to start on."""
        if "http_health_check" not in self.factory.loaded_plugins:
            self.skipTest("http_health_check plugin not loaded (missing dependencies)")
        plugin = self.factory.create_plugin("http_health_check", iterations=1)

        self.assertFalse(plugin.can_run({"config": [{}]}))
        self.assertFalse(plugin.can_run({"config": []}))
        self.assertFalse(plugin.can_run({}))

    def test_http_plugin_can_run_with_a_url(self):
        if "http_health_check" not in self.factory.loaded_plugins:
            self.skipTest("http_health_check plugin not loaded (missing dependencies)")
        plugin = self.factory.create_plugin("http_health_check", iterations=1)

        self.assertTrue(plugin.can_run({"config": [{"url": "http://example.com"}]}))

    def test_start_all_does_not_report_a_skipped_plugin_as_started(self):
        """The bug in #1537: 'skipping' and 'Started' were logged for the same plugin."""
        if "http_health_check" not in self.factory.loaded_plugins:
            self.skipTest("http_health_check plugin not loaded (missing dependencies)")
        # Set explicitly rather than relying on the loader: config_key_map is only
        # populated for the first factory built in a process (see loaded_plugins
        # short-circuit in __load_plugins), which would make this test order-dependent.
        self.factory.config_key_map = {"health_checks": "http_health_check"}

        # A present but urlless section: truthy, so start_all() reaches the plugin.
        config = {"health_checks": {"config": [{"not_a_url": "x"}]}}

        with self.assertLogs(level=logging.INFO) as captured:
            checkers = self.factory.start_all(config, iterations=1)

        self.assertEqual(checkers, [], "an unrunnable plugin must not be started")
        started = [line for line in captured.output if "Started health check plugin" in line]
        self.assertEqual(started, [], f"skipped plugin was reported as started: {started}")
        self.assertTrue(
            any("skipping" in line for line in captured.output),
            f"expected a skip reason to be logged, got: {captured.output}",
        )

    def test_start_all_still_starts_a_runnable_plugin(self):
        """The gate must not suppress plugins that are configured correctly."""
        if "http_health_check" not in self.factory.loaded_plugins:
            self.skipTest("http_health_check plugin not loaded (missing dependencies)")
        self.factory.config_key_map = {"health_checks": "http_health_check"}

        config = {"health_checks": {"config": [{"url": "http://example.com"}]}}

        # The unit under test is the factory's gate, not the plugin's polling loop.
        # Left real, the worker thread would do live DNS/HTTP against the url above
        # and only exit on the next interval tick.
        plugin_class = type(self.factory.create_plugin("http_health_check", iterations=1))
        with patch.object(plugin_class, "run_health_check", return_value=None):
            with self.assertLogs(level=logging.INFO) as captured:
                checkers = self.factory.start_all(config, iterations=1)
            for _, worker, _ in checkers:
                if worker is not None:
                    worker.join(timeout=5)

        self.assertTrue(checkers, "a runnable plugin should still be started")
        self.assertTrue(
            any("Started health check plugin" in line for line in captured.output),
            f"expected a start to be logged, got: {captured.output}",
        )

    def test_start_all_survives_a_plugin_whose_can_run_raises(self):
        """A malformed config section must skip that plugin, not abort startup."""
        if "http_health_check" not in self.factory.loaded_plugins:
            self.skipTest("http_health_check plugin not loaded (missing dependencies)")
        self.factory.config_key_map = {"health_checks": "http_health_check"}

        # A list of strings, not of dicts: can_run() calls .get() on each entry.
        config = {"health_checks": {"config": ["http://example.com"]}}

        with self.assertLogs(level=logging.WARNING) as captured:
            checkers = self.factory.start_all(config, iterations=1)

        self.assertEqual(checkers, [], "a plugin that cannot validate must not start")
        self.assertTrue(
            any("failed to validate its configuration" in line for line in captured.output),
            f"expected the validation failure to be logged, got: {captured.output}",
        )


if __name__ == "__main__":
    unittest.main()
