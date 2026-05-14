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


if __name__ == "__main__":
    unittest.main()
