#!/usr/bin/env python3

"""
Test suite for HttpTrigger class

Usage:
    python -m coverage run -a -m unittest tests/test_triggers/test_http_trigger.py -v

Assisted By: Antigravity
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

from krkn.scenario_plugins.triggers.http_trigger import (
    HTTP_REQUEST_TIMEOUT_SECONDS, VALID_METHODS, HttpTrigger)


class TestHttpTrigger(unittest.TestCase):

    def _make_trigger(self, **overrides):
        """Build an HttpTrigger with sensible defaults."""
        config = {"url": "http://example.com/health", "expected_status": 200}
        config.update(overrides)
        return HttpTrigger(config)

    def _mock_response(self, status_code=200, text="ok"):
        """Build a mock requests.Response."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = text
        return mock_resp

    # ------------------------------------------------------------------
    # evaluate() tests
    # ------------------------------------------------------------------

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_evaluate_success(self, mock_session_cls):
        """Status matches expected_status -> returns True."""
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(200)
        )
        trigger = self._make_trigger(
            url="http://example.com/health", expected_status=200
        )

        self.assertTrue(trigger.evaluate())
        mock_session_cls.return_value.__enter__.return_value.request.assert_called_once_with(
            "GET",
            "http://example.com/health",
            headers={},
            timeout=HTTP_REQUEST_TIMEOUT_SECONDS,
        )

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_evaluate_wrong_status(self, mock_session_cls):
        """Status does not match expected_status -> returns False."""
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(503)
        )
        trigger = self._make_trigger(expected_status=200)

        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_evaluate_body_contains_match(self, mock_session_cls):
        """Status matches and body_contains substring found -> returns True."""
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(200, text='{"status": "healthy"}')
        )
        trigger = self._make_trigger(body_contains="healthy")

        self.assertTrue(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_evaluate_body_contains_no_match(self, mock_session_cls):
        """Status matches but body_contains substring not found -> returns False."""
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(200, text='{"status": "degraded"}')
        )
        trigger = self._make_trigger(body_contains="healthy")

        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_evaluate_body_contains_skipped_on_wrong_status(self, mock_session_cls):
        """body_contains is not checked when status does not match."""
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(503, text="healthy")
        )
        trigger = self._make_trigger(expected_status=200, body_contains="healthy")

        # Should be False because status is wrong, body_contains not evaluated
        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_evaluate_connection_error(self, mock_session_cls):
        """ConnectionError -> returns False, no exception propagated."""
        mock_session_cls.return_value.__enter__.return_value.request.side_effect = (
            requests.exceptions.ConnectionError("refused")
        )
        trigger = self._make_trigger()

        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_evaluate_timeout(self, mock_session_cls):
        """Timeout -> returns False, no exception propagated."""
        mock_session_cls.return_value.__enter__.return_value.request.side_effect = (
            requests.exceptions.Timeout("timed out")
        )
        trigger = self._make_trigger()

        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_evaluate_request_exception(self, mock_session_cls):
        """Generic RequestException -> returns False, no exception propagated."""
        mock_session_cls.return_value.__enter__.return_value.request.side_effect = (
            requests.exceptions.RequestException("generic error")
        )
        trigger = self._make_trigger()

        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_evaluate_unexpected_exception(self, mock_session_cls):
        """Unexpected exception -> returns False, no exception propagated."""
        mock_session_cls.return_value.__enter__.return_value.request.side_effect = (
            RuntimeError("something unexpected")
        )
        trigger = self._make_trigger()

        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_bearer_token_sets_authorization_header(self, mock_session_cls):
        """bearer_token -> Authorization: Bearer <token> header sent."""
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(200)
        )
        trigger = self._make_trigger(bearer_token="my-secret-token")

        trigger.evaluate()
        call_kwargs = (
            mock_session_cls.return_value.__enter__.return_value.request.call_args[1]
        )
        self.assertEqual(
            call_kwargs["headers"]["Authorization"], "Bearer my-secret-token"
        )

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_custom_headers_merged(self, mock_session_cls):
        """headers dict -> merged into request headers."""
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(200)
        )
        trigger = self._make_trigger(headers={"X-Custom": "value"})

        trigger.evaluate()
        call_kwargs = (
            mock_session_cls.return_value.__enter__.return_value.request.call_args[1]
        )
        self.assertEqual(call_kwargs["headers"]["X-Custom"], "value")

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_bearer_token_overrides_authorization_in_headers(self, mock_session_cls):
        """bearer_token applied after headers dict -> overrides any Authorization in headers."""
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(200)
        )
        trigger = self._make_trigger(
            headers={"Authorization": "Bearer old-token"},
            bearer_token="new-token",
        )

        trigger.evaluate()
        call_kwargs = (
            mock_session_cls.return_value.__enter__.return_value.request.call_args[1]
        )
        self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer new-token")

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_method_override_post(self, mock_session_cls):
        """method=POST -> POST used in session.request."""
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(201)
        )
        trigger = self._make_trigger(method="POST", expected_status=201)

        trigger.evaluate()
        args = mock_session_cls.return_value.__enter__.return_value.request.call_args[0]
        self.assertEqual(args[0], "POST")

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_method_lowercased_input_normalized(self, mock_session_cls):
        """method='get' (lowercase) -> normalised to 'GET'."""
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(200)
        )
        trigger = self._make_trigger(method="get")

        self.assertEqual(trigger._method, "GET")
        trigger.evaluate()
        args = mock_session_cls.return_value.__enter__.return_value.request.call_args[0]
        self.assertEqual(args[0], "GET")

    @patch("krkn.scenario_plugins.triggers.http_trigger.requests.Session")
    def test_state_change_logging_not_satisfied_then_satisfied(self, mock_session_cls):
        """State-change logging fires on transition, not on repeat."""
        trigger = self._make_trigger()

        # First call: False -> logs "not satisfied"
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(503)
        )
        with self.assertLogs(level="INFO") as log_ctx:
            trigger.evaluate()
        self.assertTrue(
            any("trigger condition not satisfied" in line for line in log_ctx.output)
        )

        # Second call: still False -> no INFO log (state unchanged)
        # (INFO is only emitted on change)
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(503)
        )
        initial_last = trigger._last_result
        with patch("logging.info") as mock_info:
            trigger.evaluate()
            mock_info.assert_not_called()
        self.assertEqual(trigger._last_result, initial_last)  # state unchanged

        # Third call: True -> logs "satisfied"
        mock_session_cls.return_value.__enter__.return_value.request.return_value = (
            self._mock_response(200)
        )
        with self.assertLogs(level="INFO") as log_ctx:
            trigger.evaluate()
        self.assertTrue(
            any("trigger condition satisfied" in line for line in log_ctx.output)
        )

    # ------------------------------------------------------------------
    # describe() tests
    # ------------------------------------------------------------------

    def test_describe_default(self):
        """describe() returns string with method, url, and expected status."""
        trigger = self._make_trigger(
            url="http://nginx.default.svc:8080/health",
            expected_status=200,
        )
        description = trigger.describe()

        self.assertIn("http trigger", description)
        self.assertIn("GET", description)
        self.assertIn("http://nginx.default.svc:8080/health", description)
        self.assertIn("200", description)
        self.assertIsInstance(description, str)

    def test_describe_post(self):
        """describe() reflects method override."""
        trigger = self._make_trigger(method="POST", expected_status=201)
        description = trigger.describe()

        self.assertIn("POST", description)
        self.assertIn("201", description)

    # ------------------------------------------------------------------
    # Validation tests
    # ------------------------------------------------------------------

    def test_missing_url_raises(self):
        """No 'url' field -> raises ValueError containing 'url'."""
        with self.assertRaises(ValueError) as ctx:
            HttpTrigger({})
        self.assertIn("url", str(ctx.exception).lower())

    def test_empty_url_raises(self):
        """url='' -> raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            HttpTrigger({"url": ""})
        self.assertIn("url", str(ctx.exception).lower())

    def test_invalid_method_raises(self):
        """method='BREW' -> raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self._make_trigger(method="BREW")
        self.assertIn("BREW", str(ctx.exception))

    def test_valid_methods_accepted(self):
        """All methods in VALID_METHODS are accepted without raising."""
        for method in VALID_METHODS:
            trigger = self._make_trigger(method=method)
            self.assertEqual(trigger._method, method)

    def test_expected_status_string_coerced_to_int(self):
        """expected_status='200' (string) -> coerced to int 200."""
        trigger = self._make_trigger(expected_status="200")
        self.assertEqual(trigger._expected_status, 200)
        self.assertIsInstance(trigger._expected_status, int)

    def test_expected_status_invalid_string_raises(self):
        """expected_status='ok' -> raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self._make_trigger(expected_status="ok")
        self.assertIn("expected_status", str(ctx.exception))

    def test_expected_status_below_range_raises(self):
        """expected_status=99 -> raises ValueError (valid range 100-599)."""
        with self.assertRaises(ValueError) as ctx:
            self._make_trigger(expected_status=99)
        self.assertIn("100", str(ctx.exception))

    def test_expected_status_above_range_raises(self):
        """expected_status=600 -> raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self._make_trigger(expected_status=600)
        self.assertIn("599", str(ctx.exception))

    def test_default_expected_status_is_200(self):
        """No expected_status in config -> defaults to 200."""
        trigger = HttpTrigger({"url": "http://example.com"})
        self.assertEqual(trigger._expected_status, 200)

    def test_default_method_is_get(self):
        """No method in config -> defaults to GET."""
        trigger = HttpTrigger({"url": "http://example.com"})
        self.assertEqual(trigger._method, "GET")

    def test_no_bearer_token_no_authorization_header(self):
        """No bearer_token -> Authorization header not set."""
        trigger = self._make_trigger()
        self.assertNotIn("Authorization", trigger._headers)

    def test_bearer_token_stored_in_headers(self):
        """bearer_token -> stored as Authorization header on the trigger."""
        trigger = self._make_trigger(bearer_token="tok123")
        self.assertEqual(trigger._headers["Authorization"], "Bearer tok123")

    def test_last_result_initialised_to_none(self):
        """_last_result starts as None before first evaluate()."""
        trigger = self._make_trigger()
        self.assertIsNone(trigger._last_result)


if __name__ == "__main__":
    unittest.main()
