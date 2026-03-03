#!/usr/bin/env python3
"""
Test suite for HttpHealthCheckPlugin

This test file provides comprehensive coverage for the HTTP health check plugin:
- Plugin creation via factory
- HTTP request making with various authentication methods
- Health check monitoring with status tracking
- Failure detection and recovery tracking
- Exit on failure behavior
- Telemetry collection

How to run:
    # Run directly (requires full krkn environment with dependencies)
    python3 tests/test_http_health_check_plugin.py

    # Run from project root
    cd /path/to/kraken
    python3 tests/test_http_health_check_plugin.py

    # Run with pytest
    pytest tests/test_http_health_check_plugin.py -v

    # Run with unittest
    python3 -m unittest tests/test_http_health_check_plugin.py -v

    # Run specific test
    python3 -m unittest tests.test_http_health_check_plugin.TestHttpHealthCheckPlugin.test_make_request_success -v

    # Run with coverage
    coverage run -m pytest tests/test_http_health_check_plugin.py -v
    coverage report

Requirements:
    - requests library (pip install requests)
    - krkn_lib library (pip install krkn-lib)
    - All dependencies in requirements.txt

Note:
    - Tests will be skipped if http_health_check plugin fails to load
    - Plugin may fail to load if 'requests' module is not installed
    - Use a virtual environment with all dependencies installed

Migrated from test_health_checker.py to use the plugin architecture.
"""

import queue
import sys
import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from krkn_lib.models.telemetry.models import HealthCheck
from krkn.health_checks import HealthCheckFactory, HealthCheckPluginNotFound


class TestHttpHealthCheckPlugin(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures for HTTP health check plugin"""
        self.factory = HealthCheckFactory()

        # Skip tests if plugin not loaded (missing dependencies)
        if "http_health_check" not in self.factory.loaded_plugins:
            self.skipTest("HTTP health check plugin not loaded (missing dependencies)")

        self.plugin = self.factory.create_plugin("http_health_check", iterations=5)
        self.health_check_queue = queue.Queue()

    def tearDown(self):
        """Clean up after each test"""
        if hasattr(self, 'plugin'):
            self.plugin.close()
            self.plugin.current_iterations = 0
            self.plugin.set_return_value(0)

    def make_increment_side_effect(self, response_data):
        """Helper to create a side effect that increments current_iterations"""
        def side_effect(*args, **kwargs):
            self.plugin.current_iterations += 1
            return response_data
        return side_effect

    def _make_mock_session(self):
        """Create a mock session that returns a 200 response by default"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response
        return mock_session

    def test_make_request_success(self):
        """Test make_request returns success for 200 status code"""
        self.plugin.http_session = self._make_mock_session()

        result = self.plugin.make_request("http://example.com")

        self.assertEqual(result["url"], "http://example.com")
        self.assertEqual(result["status"], True)
        self.assertEqual(result["status_code"], 200)
        self.plugin.http_session.get.assert_called_once_with(
            "http://example.com",
            auth=None,
            headers=None,
            verify=True,
            timeout=3,
        )

    def test_make_request_with_auth(self):
        """Test make_request with basic authentication"""
        self.plugin.http_session = self._make_mock_session()

        auth = ("user", "pass")
        result = self.plugin.make_request("http://example.com", auth=auth)

        self.assertEqual(result["status"], True)
        self.plugin.http_session.get.assert_called_once_with(
            "http://example.com",
            auth=auth,
            headers=None,
            verify=True,
            timeout=3,
        )

    def test_make_request_with_bearer_token(self):
        """Test make_request with bearer token authentication"""
        self.plugin.http_session = self._make_mock_session()

        headers = {"Authorization": "Bearer token123"}
        result = self.plugin.make_request("http://example.com", headers=headers)

        self.assertEqual(result["status"], True)
        self.plugin.http_session.get.assert_called_once_with(
            "http://example.com",
            auth=None,
            headers=headers,
            verify=True,
            timeout=3,
        )

    def test_make_request_failure(self):
        """Test make_request returns failure for non-200 status code"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_session.get.return_value = mock_response
        self.plugin.http_session = mock_session

        result = self.plugin.make_request("http://example.com")

        self.assertEqual(result["status"], False)
        self.assertEqual(result["status_code"], 500)

    def test_make_request_with_verify_false(self):
        """Test make_request with SSL verification disabled"""
        self.plugin.http_session = self._make_mock_session()

        result = self.plugin.make_request("https://example.com", verify=False)

        self.assertEqual(result["status"], True)
        self.plugin.http_session.get.assert_called_once_with(
            "https://example.com",
            auth=None,
            headers=None,
            verify=False,
            timeout=3,
        )

    def test_make_request_network_error_returns_500(self):
        """Test make_request returns status 500 when the session raises"""
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection refused")
        self.plugin.http_session = mock_session

        result = self.plugin.make_request("http://example.com")

        self.assertEqual(result["status"], False)
        self.assertEqual(result["status_code"], 500)

    def test_plugin_uses_session_for_connection_pooling(self):
        """Test that the plugin creates and holds a requests.Session"""
        import requests
        self.assertTrue(hasattr(self.plugin, 'http_session'))
        self.assertIsInstance(self.plugin.http_session, requests.Session)

    def test_session_reused_across_requests(self):
        """Test that the same session object is used for every make_request call"""
        self.plugin.http_session = self._make_mock_session()
        original_session = self.plugin.http_session

        self.plugin.make_request("http://example1.com")
        self.plugin.make_request("http://example2.com")

        self.assertIs(self.plugin.http_session, original_session)
        self.assertEqual(self.plugin.http_session.get.call_count, 2)

    def test_close_closes_session_and_sets_none(self):
        """Test that close() closes the session and sets it to None"""
        import requests
        mock_session = MagicMock(spec=requests.Session)
        self.plugin.http_session = mock_session

        self.plugin.close()

        mock_session.close.assert_called_once()
        self.assertIsNone(self.plugin.http_session)

    def test_close_twice_is_safe(self):
        """Test that calling close() twice does not raise"""
        self.plugin.close()
        self.plugin.close()  # must not raise
        self.assertIsNone(self.plugin.http_session)

    def test_context_manager_closes_session_on_exit(self):
        """Test that the plugin can be used as a context manager"""
        from krkn.health_checks.http_health_check_plugin import HttpHealthCheckPlugin
        with HttpHealthCheckPlugin(iterations=1) as plugin:
            mock_session = self._make_mock_session()
            plugin.http_session = mock_session
            plugin.make_request("http://example.com")
            mock_session.get.assert_called_once()
        self.assertIsNone(plugin.http_session)

    def test_plugin_creation(self):
        """Test plugin is created correctly via factory"""
        self.assertIsNotNone(self.plugin)
        self.assertEqual(self.plugin.iterations, 5)
        self.assertEqual(self.plugin.current_iterations, 0)
        self.assertEqual(self.plugin.get_return_value(), 0)

    def test_get_health_check_types(self):
        """Test plugin returns correct health check types"""
        types = self.plugin.get_health_check_types()
        self.assertIn("http_health_check", types)

    def test_increment_iterations(self):
        """Test increment_iterations method"""
        initial = self.plugin.current_iterations
        self.plugin.increment_iterations()
        self.assertEqual(self.plugin.current_iterations, initial + 1)

    def test_return_value_methods(self):
        """Test get/set return value methods"""
        self.assertEqual(self.plugin.get_return_value(), 0)

        self.plugin.set_return_value(2)
        self.assertEqual(self.plugin.get_return_value(), 2)

        self.plugin.set_return_value(0)
        self.assertEqual(self.plugin.get_return_value(), 0)

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    @patch('time.sleep')
    def test_run_health_check_empty_config(self, mock_sleep, mock_make_request):
        """Test run_health_check with empty config skips checks"""
        config = {
            "config": [],
            "interval": 2
        }

        self.plugin.run_health_check(config, self.health_check_queue)

        mock_make_request.assert_not_called()

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    @patch('time.sleep')
    def test_run_health_check_successful_requests(self, mock_sleep, mock_make_request):
        """Test run_health_check with all successful requests"""
        mock_make_request.side_effect = self.make_increment_side_effect({
            "url": "http://example.com",
            "status": True,
            "status_code": 200
        })

        config = {
            "config": [
                {
                    "url": "http://example.com",
                    "bearer_token": None,
                    "auth": None,
                    "exit_on_failure": False
                }
            ],
            "interval": 0.01
        }

        self.plugin.iterations = 2
        self.plugin.run_health_check(config, self.health_check_queue)

        # Should have telemetry
        self.assertFalse(self.health_check_queue.empty())
        telemetry = self.health_check_queue.get()
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0].status, True)

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    @patch('time.sleep')
    def test_run_health_check_exit_on_failure(self, mock_sleep, mock_make_request):
        """Test run_health_check sets ret_value=2 when exit_on_failure is True"""
        mock_make_request.side_effect = self.make_increment_side_effect({
            "url": "http://example.com",
            "status": False,
            "status_code": 500
        })

        config = {
            "config": [
                {
                    "url": "http://example.com",
                    "bearer_token": None,
                    "auth": None,
                    "exit_on_failure": True
                }
            ],
            "interval": 0.01
        }

        self.plugin.iterations = 1
        self.plugin.run_health_check(config, self.health_check_queue)

        # ret_value should be set to 3 on health check failure
        self.assertEqual(self.plugin.get_return_value(), 3)

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    @patch('time.sleep')
    def test_run_health_check_multiple_urls(self, mock_sleep, mock_make_request):
        """Test run_health_check with multiple URLs"""
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            # Increment only after both URLs are called (one iteration)
            if call_count[0] % 2 == 0:
                self.plugin.current_iterations += 1
            return {
                "url": args[0] if args else "http://example.com",
                "status": True,
                "status_code": 200
            }

        mock_make_request.side_effect = side_effect

        config = {
            "config": [
                {
                    "url": "http://example1.com",
                    "bearer_token": None,
                    "auth": None,
                    "exit_on_failure": False
                },
                {
                    "url": "http://example2.com",
                    "bearer_token": None,
                    "auth": None,
                    "exit_on_failure": False
                }
            ],
            "interval": 0.01
        }

        self.plugin.iterations = 1
        self.plugin.run_health_check(config, self.health_check_queue)

        # Should have called make_request for both URLs
        self.assertEqual(mock_make_request.call_count, 2)

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    def test_run_health_check_failure_then_recovery(self, mock_make_request):
        """Test run_health_check records a telemetry entry when status changes"""
        call_count = [0]

        def side_effect(*_):
            self.plugin.current_iterations += 1
            call_count[0] += 1
            if call_count[0] == 1:
                return {"url": "http://example.com", "status": False, "status_code": 500}
            return {"url": "http://example.com", "status": True, "status_code": 200}

        mock_make_request.side_effect = side_effect

        config = {
            "config": [{"url": "http://example.com", "bearer_token": None, "auth": None, "exit_on_failure": False}],
            "interval": 0.01,
        }

        self.plugin.iterations = 3
        self.plugin.run_health_check(config, self.health_check_queue)

        self.assertFalse(self.health_check_queue.empty())
        telemetry = self.health_check_queue.get()
        self.assertGreaterEqual(len(telemetry), 1)

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    @patch('time.sleep')
    def test_run_health_check_with_bearer_token(self, mock_sleep, mock_make_request):
        """Test run_health_check passes bearer token header to make_request"""
        mock_make_request.side_effect = self.make_increment_side_effect({
            "url": "http://example.com", "status": True, "status_code": 200
        })

        config = {
            "config": [{"url": "http://example.com", "bearer_token": "test-token-123", "auth": None, "exit_on_failure": False}],
            "interval": 0.01,
        }

        self.plugin.iterations = 1
        self.plugin.run_health_check(config, self.health_check_queue)

        call_args = mock_make_request.call_args
        self.assertEqual(call_args[0][2]["Authorization"], "Bearer test-token-123")

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    @patch('time.sleep')
    def test_run_health_check_with_auth(self, mock_sleep, mock_make_request):
        """Test run_health_check passes auth tuple to make_request"""
        mock_make_request.side_effect = self.make_increment_side_effect({
            "url": "http://example.com", "status": True, "status_code": 200
        })

        config = {
            "config": [{"url": "http://example.com", "bearer_token": None, "auth": "user,pass", "exit_on_failure": False}],
            "interval": 0.01,
        }

        self.plugin.iterations = 1
        self.plugin.run_health_check(config, self.health_check_queue)

        call_args = mock_make_request.call_args
        self.assertEqual(call_args[0][1], ("user", "pass"))

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    @patch('time.sleep')
    def test_run_health_check_exit_on_failure_not_set_on_success(self, mock_sleep, mock_make_request):
        """Test run_health_check does not set ret_value when request succeeds"""
        mock_make_request.side_effect = self.make_increment_side_effect({
            "url": "http://example.com", "status": True, "status_code": 200
        })

        config = {
            "config": [{"url": "http://example.com", "bearer_token": None, "auth": None, "exit_on_failure": True}],
            "interval": 0.01,
        }

        self.plugin.iterations = 1
        self.plugin.run_health_check(config, self.health_check_queue)

        self.assertEqual(self.plugin.get_return_value(), 0)

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    @patch('time.sleep')
    def test_run_health_check_with_verify_url_false(self, mock_sleep, mock_make_request):
        """Test run_health_check passes verify=False to make_request"""
        mock_make_request.side_effect = self.make_increment_side_effect({
            "url": "https://example.com", "status": True, "status_code": 200
        })

        config = {
            "config": [{"url": "https://example.com", "bearer_token": None, "auth": None, "exit_on_failure": False, "verify_url": False}],
            "interval": 0.01,
        }

        self.plugin.iterations = 1
        self.plugin.run_health_check(config, self.health_check_queue)

        call_args = mock_make_request.call_args
        self.assertEqual(call_args[0][3], False)

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    @patch('time.sleep')
    def test_run_health_check_exception_handling(self, mock_sleep, mock_make_request):
        """Test run_health_check does not raise when make_request throws"""
        def side_effect(*args, **kwargs):
            self.plugin.current_iterations += 1
            raise Exception("Connection error")

        mock_make_request.side_effect = side_effect

        config = {
            "config": [{"url": "http://example.com", "bearer_token": None, "auth": None, "exit_on_failure": False}],
            "interval": 0.01,
        }

        self.plugin.iterations = 1
        self.plugin.run_health_check(config, self.health_check_queue)  # must not raise

    @patch('krkn.health_checks.http_health_check_plugin.HttpHealthCheckPlugin.make_request')
    @patch('time.sleep')
    def test_run_health_check_custom_interval(self, mock_sleep, mock_make_request):
        """Test run_health_check sleeps for the configured interval"""
        mock_make_request.side_effect = self.make_increment_side_effect({
            "url": "http://example.com", "status": True, "status_code": 200
        })

        config = {
            "config": [{"url": "http://example.com", "bearer_token": None, "auth": None, "exit_on_failure": False}],
            "interval": 5,
        }

        self.plugin.iterations = 2
        self.plugin.run_health_check(config, self.health_check_queue)

        mock_sleep.assert_called_with(5)


class TestHttpHealthCheckPluginFactory(unittest.TestCase):
    """Test factory-specific functionality"""

    def test_factory_loads_http_plugin(self):
        """Test that factory loads HTTP health check plugin"""
        factory = HealthCheckFactory()

        # May not be loaded if dependencies missing
        if "http_health_check" not in factory.loaded_plugins:
            self.skipTest("HTTP health check plugin not loaded (missing dependencies)")

        self.assertIn("http_health_check", factory.loaded_plugins)

    def test_factory_creates_http_plugin(self):
        """Test factory creates HTTP plugin instances"""
        factory = HealthCheckFactory()

        if "http_health_check" not in factory.loaded_plugins:
            self.skipTest("HTTP health check plugin not loaded (missing dependencies)")

        plugin = factory.create_plugin("http_health_check", iterations=10)
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.iterations, 10)
        self.assertEqual(plugin.__class__.__name__, "HttpHealthCheckPlugin")


if __name__ == "__main__":
    unittest.main()
