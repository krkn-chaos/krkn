#!/usr/bin/env python3
"""
Integration test for run_during health check timing.

Usage:
    python -m unittest tests/test_run_during_integration.py -v
"""

import logging
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from krkn.health_checks import HealthCheckFactory


class TestRunDuringIntegration(unittest.TestCase):
    """Integration tests for run_during functionality."""

    def setUp(self):
        self.factory = HealthCheckFactory()

    def test_pre_only_configuration(self):
        """Health check configured for pre only runs at pre, not during/post."""
        config = {
            "simple_health_checks": {
                "test": "value",
                "run_during": "pre",
                "exit_on_failure": True
            }
        }

        # Should run at pre
        pre_result = self.factory.run_all_once(config, check_type="pre")
        self.assertIn("simple_health_checks", pre_result["details"])
        self.assertTrue(pre_result["passed"])
        self.assertTrue(pre_result["exit_on_failure"])

        # Should NOT run at post
        post_result = self.factory.run_all_once(config, check_type="post")
        self.assertNotIn("simple_health_checks", post_result["details"])

    def test_during_only_configuration(self):
        """Health check configured for during only runs continuously, not pre/post."""
        config = {
            "simple_health_checks": {
                "test": "value",
                "run_during": "during",
                "exit_on_failure": False
            }
        }

        # Should NOT run at pre
        pre_result = self.factory.run_all_once(config, check_type="pre")
        self.assertNotIn("simple_health_checks", pre_result["details"])

        # Should NOT run at post
        post_result = self.factory.run_all_once(config, check_type="post")
        self.assertNotIn("simple_health_checks", post_result["details"])

        # Should start for continuous monitoring
        checkers = self.factory.start_all(config, iterations=1)
        self.assertEqual(len(checkers), 1)

        # Clean up
        for plugin, worker, tq in checkers:
            if worker:
                plugin.stop()
                worker.join(timeout=1)

    def test_post_only_configuration(self):
        """Health check configured for post only runs at post, not pre/during."""
        config = {
            "simple_health_checks": {
                "test": "value",
                "run_during": "post",
                "exit_on_failure": True
            }
        }

        # Should NOT run at pre
        pre_result = self.factory.run_all_once(config, check_type="pre")
        self.assertNotIn("simple_health_checks", pre_result["details"])

        # Should run at post
        post_result = self.factory.run_all_once(config, check_type="post")
        self.assertIn("simple_health_checks", post_result["details"])
        self.assertTrue(post_result["passed"])
        self.assertTrue(post_result["exit_on_failure"])

    def test_pre_and_post_configuration(self):
        """Health check configured for pre and post runs at both, not during."""
        config = {
            "simple_health_checks": {
                "test": "value",
                "run_during": ["pre", "post"],
                "exit_on_failure": True
            }
        }

        # Should run at pre
        pre_result = self.factory.run_all_once(config, check_type="pre")
        self.assertIn("simple_health_checks", pre_result["details"])
        self.assertTrue(pre_result["passed"])

        # Should run at post
        post_result = self.factory.run_all_once(config, check_type="post")
        self.assertIn("simple_health_checks", post_result["details"])
        self.assertTrue(post_result["passed"])

        # Should NOT start for continuous monitoring
        checkers = self.factory.start_all(config, iterations=1)
        self.assertEqual(len(checkers), 0)

    def test_all_timings_configuration(self):
        """Health check configured for all timings runs at all stages."""
        config = {
            "simple_health_checks": {
                "test": "value",
                "run_during": ["pre", "during", "post"],
                "exit_on_failure": False
            }
        }

        # Should run at pre
        pre_result = self.factory.run_all_once(config, check_type="pre")
        self.assertIn("simple_health_checks", pre_result["details"])

        # Should run at post
        post_result = self.factory.run_all_once(config, check_type="post")
        self.assertIn("simple_health_checks", post_result["details"])

        # Should start for continuous monitoring
        checkers = self.factory.start_all(config, iterations=1)
        self.assertEqual(len(checkers), 1)

        # Clean up
        for plugin, worker, tq in checkers:
            if worker:
                plugin.stop()
                worker.join(timeout=1)

    def test_multiple_health_checks_different_timings(self):
        """Multiple health check types can have different run_during settings."""
        config = {
            "simple_health_checks": {
                "test": "pre-check",
                "run_during": "pre",
                "exit_on_failure": True
            },
            "health_checks": {
                "run_during": ["during", "post"],
                "exit_on_failure": False,
                "config": []
            }
        }

        # Pre: only simple_health_checks should run
        pre_result = self.factory.run_all_once(config, check_type="pre")
        self.assertIn("simple_health_checks", pre_result["details"])
        self.assertNotIn("health_checks", pre_result["details"])

        # Post: only health_checks should run
        post_result = self.factory.run_all_once(config, check_type="post")
        self.assertNotIn("simple_health_checks", post_result["details"])
        self.assertIn("health_checks", post_result["details"])

    def test_default_run_during_behavior(self):
        """Health checks without run_during default to 'during'."""
        config = {
            "simple_health_checks": {
                "test": "value"
                # No run_during specified
            }
        }

        # Should NOT run at pre or post
        pre_result = self.factory.run_all_once(config, check_type="pre")
        self.assertNotIn("simple_health_checks", pre_result["details"])

        post_result = self.factory.run_all_once(config, check_type="post")
        self.assertNotIn("simple_health_checks", post_result["details"])

        # Should start for continuous monitoring (default is "during")
        checkers = self.factory.start_all(config, iterations=1)
        self.assertEqual(len(checkers), 1)

        # Clean up
        for plugin, worker, tq in checkers:
            if worker:
                plugin.stop()
                worker.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
