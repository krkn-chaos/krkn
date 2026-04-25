#!/usr/bin/env python
#
# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Test suite for krkn/cerberus/setup.py

Run this test file individually with:
  python -m unittest tests/test_cerberus_setup.py -v

Or with coverage:
  python3 -m coverage run -a -m unittest tests/test_cerberus_setup.py -v
"""
import unittest
from unittest.mock import patch, MagicMock
import json
from krkn.cerberus import setup as cerberus_setup


class TestCerberusSetup(unittest.TestCase):
    """Test suite for cerberus/setup.py module"""

    def setUp(self):
        """Reset global variables before each test"""
        cerberus_setup.cerberus_url = None
        cerberus_setup.exit_on_failure = False
        cerberus_setup.cerberus_enabled = False
        cerberus_setup.check_application_routes = ""

    # ── set_url tests ────────────────────────────────────────────────────────

    def test_set_url_with_correct_key(self):
        """set_url reads check_application_routes (correct spelling)"""
        config = {
            "kraken": {"exit_on_failure": True},
            "cerberus": {
                "cerberus_enabled": True,
                "cerberus_url": "http://cerberus.example.com",
                "check_application_routes": "route1,route2"
            }
        }
        cerberus_setup.set_url(config)
        self.assertEqual(cerberus_setup.check_application_routes, "route1,route2")
        self.assertTrue(cerberus_setup.exit_on_failure)

    def test_set_url_explicit_false_not_overridden_by_legacy(self):
        """Explicit check_application_routes: False must NOT be overridden by legacy key"""
        config = {
            "kraken": {"exit_on_failure": False},
            "cerberus": {
                "cerberus_enabled": True,
                "cerberus_url": "http://cerberus.example.com",
                "check_application_routes": False,
                "check_applicaton_routes": "legacy-route"
            }
        }
        cerberus_setup.set_url(config)
        self.assertFalse(cerberus_setup.check_application_routes)

    def test_set_url_legacy_misspelled_key_fallback(self):
        """Falls back to legacy misspelled key when correct key is absent"""
        config = {
            "kraken": {"exit_on_failure": False},
            "cerberus": {
                "cerberus_enabled": True,
                "cerberus_url": "http://cerberus.example.com",
                "check_applicaton_routes": "legacy-route"
            }
        }
        with self.assertLogs(level="WARNING") as log:
            cerberus_setup.set_url(config)
        self.assertEqual(cerberus_setup.check_application_routes, "legacy-route")
        self.assertTrue(any("deprecated" in msg for msg in log.output))

    def test_set_url_cerberus_disabled(self):
        config = {
            "kraken": {"exit_on_failure": False},
            "cerberus": {"cerberus_enabled": False}
        }
        cerberus_setup.set_url(config)
        self.assertFalse(cerberus_setup.cerberus_enabled)
        self.assertIsNone(cerberus_setup.cerberus_url)

    def test_set_url_defaults(self):
        config = {"kraken": {}, "cerberus": {}}
        cerberus_setup.set_url(config)
        self.assertFalse(cerberus_setup.exit_on_failure)
        self.assertFalse(cerberus_setup.cerberus_enabled)

    # ── get_status tests ─────────────────────────────────────────────────────

    @patch('krkn.cerberus.setup.requests.get')
    def test_get_status_cerberus_disabled(self, mock_get):
        cerberus_setup.cerberus_enabled = False
        cerberus_ok, routes_ok = cerberus_setup.get_status(0, 100)
        self.assertTrue(cerberus_ok)
        self.assertTrue(routes_ok)
        mock_get.assert_not_called()

    def test_get_status_no_url_returns_false(self):
        """get_status returns (False, False) when URL missing — does NOT exit"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = None
        cerberus_ok, routes_ok = cerberus_setup.get_status(0, 100)
        self.assertFalse(cerberus_ok)
        self.assertFalse(routes_ok)

    @patch('krkn.cerberus.setup.requests.get')
    def test_get_status_healthy(self, mock_get):
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        mock_get.return_value = MagicMock(content=b"True")
        cerberus_ok, routes_ok = cerberus_setup.get_status(0, 100)
        self.assertTrue(cerberus_ok)
        self.assertTrue(routes_ok)

    @patch('krkn.cerberus.setup.requests.get')
    def test_get_status_unhealthy_returns_false_no_exit(self, mock_get):
        """get_status returns (False, True) on unhealthy cerberus — does NOT exit"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        mock_get.return_value = MagicMock(content=b"False")
        cerberus_ok, routes_ok = cerberus_setup.get_status(0, 100)
        self.assertFalse(cerberus_ok)

    # ── publish_kraken_status tests ──────────────────────────────────────────

    @patch('krkn.cerberus.setup.get_status')
    def test_publish_healthy_no_exit(self, mock_get_status):
        """Healthy cluster never exits regardless of exit_on_failure"""
        cerberus_setup.exit_on_failure = True
        mock_get_status.return_value = (True, True)
        cerberus_setup.publish_kraken_status(0, 100)
        mock_get_status.assert_called_once_with(0, 100)

    @patch('krkn.cerberus.setup.get_status')
    def test_publish_unhealthy_exit_on_failure_true(self, mock_get_status):
        """Unhealthy + exit_on_failure=True → sys.exit(1)"""
        cerberus_setup.exit_on_failure = True
        mock_get_status.return_value = (False, True)
        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.publish_kraken_status(0, 100)
        self.assertEqual(cm.exception.code, 1)

    @patch('krkn.cerberus.setup.get_status')
    def test_publish_unhealthy_exit_on_failure_false(self, mock_get_status):
        """Unhealthy + exit_on_failure=False → logs only, no exit"""
        cerberus_setup.exit_on_failure = False
        mock_get_status.return_value = (False, True)
        cerberus_setup.publish_kraken_status(0, 100)

    @patch('krkn.cerberus.setup.get_status')
    def test_publish_routes_unhealthy_exit_on_failure_true(self, mock_get_status):
        """Routes unhealthy + exit_on_failure=True → sys.exit(1)"""
        cerberus_setup.exit_on_failure = True
        mock_get_status.return_value = (True, False)
        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.publish_kraken_status(0, 100)
        self.assertEqual(cm.exception.code, 1)

    # ── application_status tests ─────────────────────────────────────────────

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_no_failures(self, mock_get):
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        mock_get.return_value = MagicMock(
            content=json.dumps({"history": {"failures": []}}).encode()
        )
        status, failed_routes = cerberus_setup.application_status(0, 6000)
        self.assertTrue(status)
        self.assertEqual(failed_routes, set())

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_with_route_failures(self, mock_get):
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        mock_get.return_value = MagicMock(
            content=json.dumps({"history": {"failures": [
                {"component": "route", "name": "route1"},
                {"component": "route", "name": "route2"},
                {"component": "pod",   "name": "pod1"},
                {"component": "route", "name": "route1"},
            ]}}).encode()
        )
        status, failed_routes = cerberus_setup.application_status(0, 6000)
        self.assertFalse(status)
        self.assertEqual(failed_routes, {"route1", "route2"})

    def test_application_status_no_url(self):
        cerberus_setup.cerberus_url = None
        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.application_status(0, 100)
        self.assertEqual(cm.exception.code, 1)

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_request_exception(self, mock_get):
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        mock_get.side_effect = Exception("Connection error")
        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.application_status(0, 6000)
        self.assertEqual(cm.exception.code, 1)

    @patch('krkn.cerberus.setup.application_status')
    @patch('krkn.cerberus.setup.requests.get')
    def test_get_status_with_route_check_enabled(self, mock_get, mock_app_status):
        """
        Test that application_status is called when check_application_routes is True
        """
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://fake-cerberus:8080"
        cerberus_setup.check_application_routes = True

        mock_response = MagicMock()
        mock_response.content = b"True"
        mock_get.return_value = mock_response

        mock_app_status.return_value = (True, [])

        cerberus_status, app_routes_status = cerberus_setup.get_status(0, 100)

        mock_app_status.assert_called_once_with(0, 100)

        self.assertTrue(cerberus_status)
        self.assertTrue(app_routes_status)


if __name__ == '__main__':
    unittest.main()
