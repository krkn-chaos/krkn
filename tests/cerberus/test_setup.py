#!/usr/bin/env python3

"""
Test suite for krkn.cerberus.setup module

Usage:
    python3 -m coverage run --source=krkn -m pytest tests/cerberus/test_setup.py -v
    python3 -m coverage report -m --include=krkn/cerberus/setup.py
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from krkn.cerberus.setup import get_status, publish_kraken_status, application_status


class TestGetStatus(unittest.TestCase):
    """Test suite for get_status function"""

    def test_cerberus_disabled(self):
        """Test get_status returns True when cerberus is disabled"""
        config = {
            "cerberus": {
                "cerberus_enabled": False
            }
        }
        
        result = get_status(config, 0, 100)
        
        self.assertTrue(result)

    @patch('krkn.cerberus.setup.sys.exit')
    def test_cerberus_enabled_no_url(self, mock_exit):
        """Test get_status exits when cerberus_url is not provided"""
        mock_exit.side_effect = SystemExit(1)
        config = {
            "cerberus": {
                "cerberus_enabled": True,
                "cerberus_url": "",
                "check_applicaton_routes": False
            }
        }
        
        with self.assertRaises(SystemExit):
            get_status(config, 0, 100)
        
        mock_exit.assert_called_once_with(1)

    @patch('krkn.cerberus.setup.requests.get')
    def test_cerberus_enabled_healthy(self, mock_get):
        """Test get_status returns True when cerberus returns healthy status"""
        config = {
            "cerberus": {
                "cerberus_enabled": True,
                "cerberus_url": "http://cerberus:8080",
                "check_applicaton_routes": False
            }
        }
        mock_response = MagicMock()
        mock_response.content = b"True"
        mock_get.return_value = mock_response
        
        result = get_status(config, 0, 100)
        
        self.assertTrue(result)
        mock_get.assert_called_once_with("http://cerberus:8080", timeout=60)

    @patch('krkn.cerberus.setup.sys.exit')
    @patch('krkn.cerberus.setup.requests.get')
    def test_cerberus_enabled_unhealthy(self, mock_get, mock_exit):
        """Test get_status exits when cerberus returns unhealthy status"""
        config = {
            "cerberus": {
                "cerberus_enabled": True,
                "cerberus_url": "http://cerberus:8080",
                "check_applicaton_routes": False
            }
        }
        mock_response = MagicMock()
        mock_response.content = b"False"
        mock_get.return_value = mock_response
        
        get_status(config, 0, 100)
        
        mock_exit.assert_called_once_with(1)

    @patch('krkn.cerberus.setup.application_status')
    @patch('krkn.cerberus.setup.requests.get')
    def test_cerberus_with_application_routes_healthy(self, mock_get, mock_app_status):
        """Test get_status with application routes check - all healthy"""
        config = {
            "cerberus": {
                "cerberus_enabled": True,
                "cerberus_url": "http://cerberus:8080",
                "check_applicaton_routes": True
            }
        }
        mock_response = MagicMock()
        mock_response.content = b"True"
        mock_get.return_value = mock_response
        mock_app_status.return_value = (True, set())
        
        result = get_status(config, 0, 100)
        
        self.assertTrue(result)
        mock_app_status.assert_called_once_with("http://cerberus:8080", 0, 100)

    @patch('krkn.cerberus.setup.sys.exit')
    @patch('krkn.cerberus.setup.application_status')
    @patch('krkn.cerberus.setup.requests.get')
    def test_cerberus_with_application_routes_unhealthy(self, mock_get, mock_app_status, mock_exit):
        """Test get_status with application routes check - routes unhealthy"""
        config = {
            "cerberus": {
                "cerberus_enabled": True,
                "cerberus_url": "http://cerberus:8080",
                "check_applicaton_routes": True
            }
        }
        mock_response = MagicMock()
        mock_response.content = b"True"
        mock_get.return_value = mock_response
        mock_app_status.return_value = (False, {"route1", "route2"})
        
        get_status(config, 0, 100)
        
        mock_exit.assert_called_once_with(1)


class TestPublishKrakenStatus(unittest.TestCase):
    """Test suite for publish_kraken_status function"""

    @patch('krkn.cerberus.setup.get_status')
    def test_cerberus_unhealthy_failed_scenarios_exit_on_failure(self, mock_get_status):
        """Test when cerberus is unhealthy, scenarios failed, and exit_on_failure is True"""
        config = {
            "cerberus": {},
            "kraken": {
                "exit_on_failure": True
            }
        }
        mock_get_status.return_value = False
        
        with patch('krkn.cerberus.setup.sys.exit') as mock_exit:
            publish_kraken_status(config, ["failed_scenario"], 0, 100)
            mock_exit.assert_called_once_with(1)

    @patch('krkn.cerberus.setup.get_status')
    def test_cerberus_unhealthy_failed_scenarios_no_exit(self, mock_get_status):
        """Test when cerberus is unhealthy, scenarios failed, and exit_on_failure is False"""
        config = {
            "cerberus": {},
            "kraken": {
                "exit_on_failure": False
            }
        }
        mock_get_status.return_value = False
        
        # Should not exit, just log
        publish_kraken_status(config, ["failed_scenario"], 0, 100)
        # No assertion needed - just verifying no exception raised

    @patch('krkn.cerberus.setup.get_status')
    def test_cerberus_healthy_failed_scenarios_exit_on_failure(self, mock_get_status):
        """Test when cerberus is healthy, scenarios failed, and exit_on_failure is True"""
        config = {
            "cerberus": {},
            "kraken": {
                "exit_on_failure": True
            }
        }
        mock_get_status.return_value = True
        
        with patch('krkn.cerberus.setup.sys.exit') as mock_exit:
            publish_kraken_status(config, ["failed_scenario"], 0, 100)
            mock_exit.assert_called_once_with(1)

    @patch('krkn.cerberus.setup.get_status')
    def test_cerberus_healthy_failed_scenarios_no_exit(self, mock_get_status):
        """Test when cerberus is healthy, scenarios failed, and exit_on_failure is False"""
        config = {
            "cerberus": {},
            "kraken": {
                "exit_on_failure": False
            }
        }
        mock_get_status.return_value = True
        
        # Should not exit, just log
        publish_kraken_status(config, ["failed_scenario"], 0, 100)
        # No assertion needed - just verifying no exception raised

    @patch('krkn.cerberus.setup.get_status')
    def test_cerberus_unhealthy_no_failed_scenarios(self, mock_get_status):
        """Test when cerberus is unhealthy but no failed scenarios"""
        config = {
            "cerberus": {},
            "kraken": {
                "exit_on_failure": True
            }
        }
        mock_get_status.return_value = False
        
        # Should not enter the if blocks for failed_post_scenarios
        publish_kraken_status(config, [], 0, 100)

    @patch('krkn.cerberus.setup.get_status')
    def test_cerberus_healthy_no_failed_scenarios(self, mock_get_status):
        """Test when cerberus is healthy and no failed scenarios"""
        config = {
            "cerberus": {},
            "kraken": {
                "exit_on_failure": True
            }
        }
        mock_get_status.return_value = True
        
        # Should not enter the if blocks for failed_post_scenarios
        publish_kraken_status(config, [], 0, 100)


class TestApplicationStatus(unittest.TestCase):
    """Test suite for application_status function"""

    @patch('krkn.cerberus.setup.sys.exit')
    def test_no_cerberus_url(self, mock_exit):
        """Test application_status exits when cerberus_url is not provided"""
        mock_exit.side_effect = SystemExit(1)
        
        with self.assertRaises(SystemExit):
            application_status("", 0, 100)
        
        mock_exit.assert_called_once_with(1)

    @patch('krkn.cerberus.setup.sys.exit')
    def test_no_cerberus_url_none(self, mock_exit):
        """Test application_status exits when cerberus_url is None"""
        mock_exit.side_effect = SystemExit(1)
        
        with self.assertRaises(SystemExit):
            application_status(None, 0, 100)
        
        mock_exit.assert_called_once_with(1)

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_healthy(self, mock_get):
        """Test application_status returns healthy status with no failed routes"""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "history": {
                "failures": []
            }
        }).encode()
        mock_get.return_value = mock_response
        
        status, failed_routes = application_status("http://cerberus:8080", 0, 6000)
        
        self.assertTrue(status)
        self.assertEqual(failed_routes, set())
        # Check URL format: duration should be (6000 - 0) / 60 = 100
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        self.assertIn("loopback=100.0", call_url)

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_with_failed_routes(self, mock_get):
        """Test application_status returns failed routes"""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "history": {
                "failures": [
                    {"component": "route", "name": "route1"},
                    {"component": "route", "name": "route2"},
                    {"component": "pod", "name": "pod1"}  # Non-route component
                ]
            }
        }).encode()
        mock_get.return_value = mock_response
        
        status, failed_routes = application_status("http://cerberus:8080", 0, 6000)
        
        self.assertFalse(status)
        self.assertEqual(failed_routes, {"route1", "route2"})

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_with_non_route_failures(self, mock_get):
        """Test application_status ignores non-route failures"""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "history": {
                "failures": [
                    {"component": "pod", "name": "pod1"},
                    {"component": "node", "name": "node1"}
                ]
            }
        }).encode()
        mock_get.return_value = mock_response
        
        status, failed_routes = application_status("http://cerberus:8080", 0, 6000)
        
        self.assertTrue(status)
        self.assertEqual(failed_routes, set())

    @patch('krkn.cerberus.setup.sys.exit')
    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_request_exception(self, mock_get, mock_exit):
        """Test application_status exits on request exception"""
        mock_get.side_effect = Exception("Connection error")
        
        application_status("http://cerberus:8080", 0, 6000)
        
        mock_exit.assert_called_once_with(1)

    @patch('krkn.cerberus.setup.sys.exit')
    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_json_parse_error(self, mock_get, mock_exit):
        """Test application_status exits on JSON parse error"""
        mock_response = MagicMock()
        mock_response.content = b"invalid json"
        mock_get.return_value = mock_response
        
        application_status("http://cerberus:8080", 0, 6000)
        
        mock_exit.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
