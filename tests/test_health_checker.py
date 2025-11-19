#!/usr/bin/env python3

"""
Test suite for HealthChecker class

This test file provides comprehensive coverage for the main functionality of HealthChecker:
- HTTP request making with various authentication methods
- Health check monitoring with status tracking
- Failure detection and recovery tracking
- Exit on failure behavior
- Telemetry collection

Usage:
    python -m coverage run -a -m unittest tests/test_health_checker.py -v

Assisted By: Claude Code
"""

import queue
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from krkn_lib.models.telemetry.models import HealthCheck

from krkn.utils.HealthChecker import HealthChecker


class TestHealthChecker(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for HealthChecker
        """
        self.checker = HealthChecker(iterations=5)
        self.health_check_queue = queue.Queue()

    def tearDown(self):
        """
        Clean up after each test
        """
        self.checker.current_iterations = 0
        self.checker.ret_value = 0

    def make_increment_side_effect(self, response_data):
        """
        Helper to create a side effect that increments current_iterations
        """
        def side_effect(*args, **kwargs):
            self.checker.current_iterations += 1
            return response_data
        return side_effect

    @patch('requests.get')
    def test_make_request_success(self, mock_get):
        """
        Test make_request returns success for 200 status code
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = self.checker.make_request("http://example.com")

        self.assertEqual(result["url"], "http://example.com")
        self.assertEqual(result["status"], True)
        self.assertEqual(result["status_code"], 200)
        mock_get.assert_called_once_with(
            "http://example.com",
            auth=None,
            headers=None,
            verify=True,
            timeout=3
        )

    @patch('requests.get')
    def test_make_request_with_auth(self, mock_get):
        """
        Test make_request with basic authentication
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        auth = ("user", "pass")
        result = self.checker.make_request("http://example.com", auth=auth)

        self.assertEqual(result["status"], True)
        mock_get.assert_called_once_with(
            "http://example.com",
            auth=auth,
            headers=None,
            verify=True,
            timeout=3
        )

    @patch('requests.get')
    def test_make_request_with_bearer_token(self, mock_get):
        """
        Test make_request with bearer token authentication
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        headers = {"Authorization": "Bearer token123"}
        result = self.checker.make_request("http://example.com", headers=headers)

        self.assertEqual(result["status"], True)
        mock_get.assert_called_once_with(
            "http://example.com",
            auth=None,
            headers=headers,
            verify=True,
            timeout=3
        )

    @patch('requests.get')
    def test_make_request_failure(self, mock_get):
        """
        Test make_request returns failure for non-200 status code
        """
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        result = self.checker.make_request("http://example.com")

        self.assertEqual(result["status"], False)
        self.assertEqual(result["status_code"], 500)

    @patch('requests.get')
    def test_make_request_with_verify_false(self, mock_get):
        """
        Test make_request with SSL verification disabled
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = self.checker.make_request("https://example.com", verify=False)

        self.assertEqual(result["status"], True)
        mock_get.assert_called_once_with(
            "https://example.com",
            auth=None,
            headers=None,
            verify=False,
            timeout=3
        )

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_empty_config(self, mock_sleep, mock_make_request):
        """
        Test run_health_check with empty config skips checks
        """
        config = {
            "config": [],
            "interval": 2
        }

        self.checker.run_health_check(config, self.health_check_queue)

        mock_make_request.assert_not_called()
        self.assertTrue(self.health_check_queue.empty())

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_successful_requests(self, mock_sleep, mock_make_request):
        """
        Test run_health_check with all successful requests
        """
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

        self.checker.iterations = 2
        self.checker.run_health_check(config, self.health_check_queue)

        # Should have telemetry
        self.assertFalse(self.health_check_queue.empty())
        telemetry = self.health_check_queue.get()
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0].status, True)

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_failure_then_recovery(self, mock_sleep, mock_make_request):
        """
        Test run_health_check detects failure and recovery
        """
        # Create side effects that increment and return different values
        call_count = [0]
        def side_effect(*args, **kwargs):
            self.checker.current_iterations += 1
            call_count[0] += 1
            if call_count[0] == 1:
                return {"url": "http://example.com", "status": False, "status_code": 500}
            else:
                return {"url": "http://example.com", "status": True, "status_code": 200}

        mock_make_request.side_effect = side_effect

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

        self.checker.iterations = 3
        self.checker.run_health_check(config, self.health_check_queue)

        # Should have telemetry showing failure period
        self.assertFalse(self.health_check_queue.empty())
        telemetry = self.health_check_queue.get()

        # Should have at least 2 entries: one for failure period, one for success period
        self.assertGreaterEqual(len(telemetry), 1)

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_with_bearer_token(self, mock_sleep, mock_make_request):
        """
        Test run_health_check correctly handles bearer token
        """
        mock_make_request.side_effect = self.make_increment_side_effect({
            "url": "http://example.com",
            "status": True,
            "status_code": 200
        })

        config = {
            "config": [
                {
                    "url": "http://example.com",
                    "bearer_token": "test-token-123",
                    "auth": None,
                    "exit_on_failure": False
                }
            ],
            "interval": 0.01
        }

        self.checker.iterations = 1
        self.checker.run_health_check(config, self.health_check_queue)

        # Verify bearer token was added to headers
        # make_request is called as: make_request(url, auth, headers, verify_url)
        call_args = mock_make_request.call_args
        self.assertEqual(call_args[0][2]['Authorization'], "Bearer test-token-123")

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_with_auth(self, mock_sleep, mock_make_request):
        """
        Test run_health_check correctly handles basic auth
        """
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
                    "auth": "user,pass",
                    "exit_on_failure": False
                }
            ],
            "interval": 0.01
        }

        self.checker.iterations = 1
        self.checker.run_health_check(config, self.health_check_queue)

        # Verify auth tuple was created correctly
        # make_request is called as: make_request(url, auth, headers, verify_url)
        call_args = mock_make_request.call_args
        self.assertEqual(call_args[0][1], ("user", "pass"))

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_exit_on_failure(self, mock_sleep, mock_make_request):
        """
        Test run_health_check sets ret_value=2 when exit_on_failure is True
        """
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

        self.checker.iterations = 1
        self.checker.run_health_check(config, self.health_check_queue)

        # ret_value should be set to 2 on failure
        self.assertEqual(self.checker.ret_value, 2)

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_exit_on_failure_not_set_on_success(self, mock_sleep, mock_make_request):
        """
        Test run_health_check does not set ret_value when request succeeds
        """
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
                    "exit_on_failure": True
                }
            ],
            "interval": 0.01
        }

        self.checker.iterations = 1
        self.checker.run_health_check(config, self.health_check_queue)

        # ret_value should remain 0 on success
        self.assertEqual(self.checker.ret_value, 0)

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_with_verify_url_false(self, mock_sleep, mock_make_request):
        """
        Test run_health_check respects verify_url setting
        """
        mock_make_request.side_effect = self.make_increment_side_effect({
            "url": "https://example.com",
            "status": True,
            "status_code": 200
        })

        config = {
            "config": [
                {
                    "url": "https://example.com",
                    "bearer_token": None,
                    "auth": None,
                    "exit_on_failure": False,
                    "verify_url": False
                }
            ],
            "interval": 0.01
        }

        self.checker.iterations = 1
        self.checker.run_health_check(config, self.health_check_queue)

        # Verify that verify parameter was set to False
        # make_request is called as: make_request(url, auth, headers, verify_url)
        call_args = mock_make_request.call_args
        self.assertEqual(call_args[0][3], False)

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_exception_handling(self, mock_sleep, mock_make_request):
        """
        Test run_health_check handles exceptions during requests
        """
        # Simulate exception during request but also increment to avoid infinite loop
        def side_effect(*args, **kwargs):
            self.checker.current_iterations += 1
            raise Exception("Connection error")

        mock_make_request.side_effect = side_effect

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

        self.checker.iterations = 1

        # Should not raise exception
        self.checker.run_health_check(config, self.health_check_queue)

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_multiple_urls(self, mock_sleep, mock_make_request):
        """
        Test run_health_check with multiple URLs
        """
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            # Increment only after both URLs are called (one iteration)
            if call_count[0] % 2 == 0:
                self.checker.current_iterations += 1
            return {
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

        self.checker.iterations = 1
        self.checker.run_health_check(config, self.health_check_queue)

        # Should have called make_request for both URLs
        self.assertEqual(mock_make_request.call_count, 2)

    @patch('krkn.utils.HealthChecker.HealthChecker.make_request')
    @patch('time.sleep')
    def test_run_health_check_custom_interval(self, mock_sleep, mock_make_request):
        """
        Test run_health_check uses custom interval
        """
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
            "interval": 5
        }

        self.checker.iterations = 2
        self.checker.run_health_check(config, self.health_check_queue)

        # Verify sleep was called with custom interval
        mock_sleep.assert_called_with(5)


if __name__ == "__main__":
    unittest.main()
