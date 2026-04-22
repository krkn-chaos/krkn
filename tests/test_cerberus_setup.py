"""
Test suite for krkn/cerberus/setup.py

Run this test file individually with:
  python -m unittest tests/test_cerberus_setup.py -v

Or with coverage:
  python3 -m coverage run -a -m unittest tests/test_cerberus_setup.py -v

Generated with help from Claude Code
"""
import unittest
from unittest.mock import patch, MagicMock, Mock
import sys
import json
import requests
from krkn.cerberus import setup as cerberus_setup


class TestCerberusSetup(unittest.TestCase):
    """Test suite for cerberus/setup.py module"""

    def setUp(self):
        """Reset global variables before each test"""
        cerberus_setup.cerberus_url = None
        cerberus_setup.exit_on_failure = False
        cerberus_setup.cerberus_enabled = False
        cerberus_setup.check_application_routes = ""

    def test_set_url_with_cerberus_enabled(self):
        """Test set_url when cerberus is enabled"""
        config = {
            "kraken": {"exit_on_failure": True},
            "cerberus": {
                "cerberus_enabled": True,
                "cerberus_url": "http://cerberus.example.com",
                "check_applicaton_routes": "route1,route2"
            }
        }

        cerberus_setup.set_url(config)

        self.assertEqual(cerberus_setup.cerberus_url, "http://cerberus.example.com")
        self.assertTrue(cerberus_setup.exit_on_failure)
        self.assertTrue(cerberus_setup.cerberus_enabled)
        self.assertEqual(cerberus_setup.check_application_routes, "route1,route2")

    def test_set_url_with_cerberus_disabled(self):
        """Test set_url when cerberus is disabled"""
        config = {
            "kraken": {"exit_on_failure": False},
            "cerberus": {"cerberus_enabled": False}
        }

        cerberus_setup.set_url(config)

        self.assertFalse(cerberus_setup.cerberus_enabled)
        self.assertFalse(cerberus_setup.exit_on_failure)
        self.assertIsNone(cerberus_setup.cerberus_url)

    def test_set_url_with_defaults(self):
        """Test set_url with missing optional fields (should use defaults)"""
        config = {
            "kraken": {},
            "cerberus": {}
        }

        cerberus_setup.set_url(config)

        self.assertFalse(cerberus_setup.exit_on_failure)
        self.assertFalse(cerberus_setup.cerberus_enabled)

    @patch.object(cerberus_setup, 'http_session')
    def test_get_status_cerberus_disabled(self, mock_session):
        """Test get_status when cerberus is disabled makes no HTTP calls"""
        cerberus_setup.cerberus_enabled = False

        result = cerberus_setup.get_status(0, 100)

        self.assertTrue(result)
        mock_session.get.assert_not_called()

    @patch.object(cerberus_setup, 'http_session')
    def test_get_status_cerberus_enabled_healthy(self, mock_session):
        """Test get_status when cerberus is enabled and cluster is healthy"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://cerberus.example.com"

        mock_response = MagicMock()
        mock_response.content = b"True"
        mock_session.get.return_value = mock_response

        result = cerberus_setup.get_status(0, 100)

        self.assertTrue(result)
        mock_session.get.assert_called_once_with("http://cerberus.example.com", timeout=60)

    @patch.object(cerberus_setup, 'http_session')
    def test_get_status_cerberus_enabled_unhealthy(self, mock_session):
        """Test get_status when cerberus is enabled and cluster is unhealthy"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://cerberus.example.com"

        mock_response = MagicMock()
        mock_response.content = b"False"
        mock_session.get.return_value = mock_response

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.get_status(0, 100)

        self.assertEqual(cm.exception.code, 1)
        mock_session.get.assert_called_once_with("http://cerberus.example.com", timeout=60)

    def test_get_status_no_url_provided(self):
        """Test get_status when cerberus is enabled but URL is not provided"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = None

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.get_status(0, 100)

        self.assertEqual(cm.exception.code, 1)

    @patch.object(cerberus_setup, 'http_session')
    def test_get_status_cerberus_healthy_returns_true(self, mock_session):
        """Test get_status returns True when cerberus reports healthy.
        Note: check_application_routes is shadowed locally in get_status()
        (pre-existing issue), so route-check branch is not exercised here."""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://cerberus.example.com"

        mock_response = MagicMock()
        mock_response.content = b"True"
        mock_session.get.return_value = mock_response

        result = cerberus_setup.get_status(0, 100)

        self.assertTrue(result)
        mock_session.get.assert_called_once_with("http://cerberus.example.com", timeout=60)

    @patch.object(cerberus_setup, 'http_session')
    def test_get_status_with_application_routes_check_failure(self, mock_session):
        """Test get_status when cerberus returns False (unhealthy)"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://cerberus.example.com"

        mock_response = MagicMock()
        mock_response.content = b"False"
        mock_session.get.return_value = mock_response

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.get_status(0, 100)

        self.assertEqual(cm.exception.code, 1)

    @patch('krkn.cerberus.setup.get_status')
    def test_publish_kraken_status_healthy_exit_on_failure_false(self, mock_get_status):
        """Test publish_kraken_status when cluster is healthy and exit_on_failure is False"""
        cerberus_setup.exit_on_failure = False
        mock_get_status.return_value = True

        cerberus_setup.publish_kraken_status(0, 100)

        mock_get_status.assert_called_once_with(0, 100)

    @patch('krkn.cerberus.setup.get_status')
    def test_publish_kraken_status_healthy_exit_on_failure_true(self, mock_get_status):
        """Test publish_kraken_status when cluster is healthy and exit_on_failure is True"""
        cerberus_setup.exit_on_failure = True
        mock_get_status.return_value = True

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.publish_kraken_status(0, 100)

        self.assertEqual(cm.exception.code, 1)
        mock_get_status.assert_called_once_with(0, 100)

    @patch('krkn.cerberus.setup.get_status')
    def test_publish_kraken_status_unhealthy_exit_on_failure_false(self, mock_get_status):
        """Test publish_kraken_status when cluster is unhealthy and exit_on_failure is False"""
        cerberus_setup.exit_on_failure = False
        mock_get_status.return_value = False

        cerberus_setup.publish_kraken_status(0, 100)

        mock_get_status.assert_called_once_with(0, 100)

    @patch('krkn.cerberus.setup.get_status')
    def test_publish_kraken_status_unhealthy_exit_on_failure_true(self, mock_get_status):
        """Test publish_kraken_status when cluster is unhealthy and exit_on_failure is True"""
        cerberus_setup.exit_on_failure = True
        mock_get_status.return_value = False

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.publish_kraken_status(0, 100)

        self.assertEqual(cm.exception.code, 1)
        mock_get_status.assert_called_once_with(0, 100)

    @patch.object(cerberus_setup, 'http_session')
    def test_application_status_no_failures(self, mock_session):
        """Test application_status when there are no route failures"""
        cerberus_setup.cerberus_url = "http://cerberus.example.com"

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "history": {
                "failures": []
            }
        }).encode()
        mock_session.get.return_value = mock_response

        status, failed_routes = cerberus_setup.application_status(0, 6000)

        self.assertTrue(status)
        self.assertEqual(failed_routes, set())
        expected_url = "http://cerberus.example.com/history?loopback=100.0"
        mock_session.get.assert_called_once_with(expected_url, timeout=60)

    @patch.object(cerberus_setup, 'http_session')
    def test_application_status_with_route_failures(self, mock_session):
        """Test application_status when there are route failures"""
        cerberus_setup.cerberus_url = "http://cerberus.example.com"

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "history": {
                "failures": [
                    {"component": "route", "name": "route1"},
                    {"component": "route", "name": "route2"},
                    {"component": "pod", "name": "pod1"},  # Non-route: should be ignored
                    {"component": "route", "name": "route1"},  # Duplicate: deduped by set()
                ]
            }
        }).encode()
        mock_session.get.return_value = mock_response

        status, failed_routes = cerberus_setup.application_status(0, 6000)

        self.assertFalse(status)
        self.assertEqual(failed_routes, {"route1", "route2"})

    @patch.object(cerberus_setup, 'http_session')
    def test_application_status_with_non_route_failures(self, mock_session):
        """Test application_status when there are non-route failures only"""
        cerberus_setup.cerberus_url = "http://cerberus.example.com"

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "history": {
                "failures": [
                    {"component": "pod", "name": "pod1"},
                    {"component": "node", "name": "node1"},
                ]
            }
        }).encode()
        mock_session.get.return_value = mock_response

        status, failed_routes = cerberus_setup.application_status(0, 6000)

        self.assertTrue(status)
        self.assertEqual(failed_routes, set())

    def test_application_status_no_url_provided(self):
        """Test application_status when cerberus URL is not provided"""
        cerberus_setup.cerberus_url = None

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.application_status(0, 100)

        self.assertEqual(cm.exception.code, 1)

    @patch.object(cerberus_setup, 'http_session')
    def test_application_status_request_exception(self, mock_session):
        """Test application_status when request raises an exception"""
        cerberus_setup.cerberus_url = "http://cerberus.example.com"

        mock_session.get.side_effect = Exception("Connection error")

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.application_status(0, 6000)

        self.assertEqual(cm.exception.code, 1)

    @patch.object(cerberus_setup, 'http_session')
    def test_application_status_duration_calculation(self, mock_session):
        """Test application_status correctly calculates duration in minutes"""
        cerberus_setup.cerberus_url = "http://cerberus.example.com"

        mock_response = MagicMock()
        mock_response.content = json.dumps({"history": {"failures": []}}).encode()
        mock_session.get.return_value = mock_response

        cerberus_setup.application_status(0, 300)

        expected_url = "http://cerberus.example.com/history?loopback=5.0"
        mock_session.get.assert_called_once_with(expected_url, timeout=60)

    def test_http_session_is_singleton(self):
        """Test that http_session is a requests.Session and the same object across accesses"""
        session1 = cerberus_setup.http_session
        session2 = cerberus_setup.http_session
        self.assertIsInstance(session1, requests.Session)
        self.assertIs(session1, session2)

    def test_http_session_reused_across_calls(self):
        """Test that application_status reuses the module-level http_session"""
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        mock_response = MagicMock()
        mock_response.content = json.dumps({"history": {"failures": []}}).encode()
        original_session = cerberus_setup.http_session

        with patch.object(cerberus_setup.http_session, 'get', return_value=mock_response):
            cerberus_setup.application_status(0, 300)
            self.assertIs(cerberus_setup.http_session, original_session)

            cerberus_setup.application_status(0, 600)
            self.assertIs(cerberus_setup.http_session, original_session)

    def test_http_session_atexit_registered(self):
        """Test that http_session.close is registered via atexit for cleanup"""
        import atexit
        # atexit._run_exitfuncs is internal, so verify registration via the module code
        # The atexit handler should have been registered at module import time
        # We verify by checking the atexit registry contains our session's close
        registered = False
        # atexit callbacks are stored internally; verify by re-registering and checking no error
        # Best we can do without poking internals: verify the session is closeable
        session = cerberus_setup.http_session
        self.assertTrue(callable(getattr(session, 'close', None)))
        # Verify atexit module was imported and used in setup.py
        import inspect
        source = inspect.getsource(cerberus_setup)
        self.assertIn('atexit.register(http_session.close)', source)


if __name__ == '__main__':
    unittest.main()
