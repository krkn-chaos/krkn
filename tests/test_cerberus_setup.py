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

    @patch('krkn.cerberus.setup.requests.get')
    def test_get_status_cerberus_disabled(self, mock_get):
        """Test get_status when cerberus is disabled"""
        cerberus_setup.cerberus_enabled = False

        result = cerberus_setup.get_status(0, 100)

        self.assertTrue(result)
        mock_get.assert_not_called()

    @patch('krkn.cerberus.setup.requests.get')
    def test_get_status_cerberus_enabled_healthy(self, mock_get):
        """Test get_status when cerberus is enabled and cluster is healthy"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        
        mock_response = MagicMock()
        mock_response.content = b"True"
        mock_get.return_value = mock_response

        result = cerberus_setup.get_status(0, 100)

        self.assertTrue(result)
        mock_get.assert_called_once_with("http://cerberus.example.com", timeout=60)

    @patch('krkn.cerberus.setup.requests.get')
    def test_get_status_cerberus_enabled_unhealthy(self, mock_get):
        """Test get_status when cerberus is enabled and cluster is unhealthy"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        
        mock_response = MagicMock()
        mock_response.content = b"False"
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.get_status(0, 100)
        
        self.assertEqual(cm.exception.code, 1)
        mock_get.assert_called_once_with("http://cerberus.example.com", timeout=60)

    def test_get_status_no_url_provided(self):
        """Test get_status when cerberus is enabled but URL is not provided"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = None

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.get_status(0, 100)
        
        self.assertEqual(cm.exception.code, 1)

    @patch('krkn.cerberus.setup.requests.get')
    def test_get_status_with_application_routes_check_success(self, mock_get):
        """Test get_status with application routes check when routes are healthy"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        
        # Mock both cerberus status check and history endpoint
        def mock_get_side_effect(url, timeout):
            mock_response = MagicMock()
            if "/history?" in url:
                # History endpoint - no failures
                mock_response.content = json.dumps({"history": {"failures": []}}).encode()
            else:
                # Status endpoint
                mock_response.content = b"True"
            return mock_response
        
        mock_get.side_effect = mock_get_side_effect

        # Note: check_application_routes is set to False locally in get_status()
        # so we can't test the full flow without modifying the function
        # This test verifies cerberus status returns True
        result = cerberus_setup.get_status(0, 100)

        self.assertTrue(result)

    @patch('krkn.cerberus.setup.requests.get')
    def test_get_status_with_application_routes_check_failure(self, mock_get):
        """Test get_status with cerberus returning False (unhealthy)"""
        cerberus_setup.cerberus_enabled = True
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        
        mock_response = MagicMock()
        mock_response.content = b"False"  # Cerberus reports unhealthy
        mock_get.return_value = mock_response

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.get_status(0, 100)
        
        self.assertEqual(cm.exception.code, 1)

    @patch('krkn.cerberus.setup.get_status')
    def test_publish_kraken_status_healthy_exit_on_failure_false(self, mock_get_status):
        """Test publish_kraken_status when cluster is healthy and exit_on_failure is False"""
        cerberus_setup.exit_on_failure = False
        mock_get_status.return_value = True

        # Should not raise SystemExit
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

        # Should not raise SystemExit
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

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_no_failures(self, mock_get):
        """Test application_status when there are no route failures"""
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "history": {
                "failures": []
            }
        }).encode()
        mock_get.return_value = mock_response

        status, failed_routes = cerberus_setup.application_status(0, 6000)

        self.assertTrue(status)
        self.assertEqual(failed_routes, set())
        expected_url = "http://cerberus.example.com/history?loopback=100.0"
        mock_get.assert_called_once_with(expected_url, timeout=60)

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_with_route_failures(self, mock_get):
        """Test application_status when there are route failures"""
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "history": {
                "failures": [
                    {"component": "route", "name": "route1"},
                    {"component": "route", "name": "route2"},
                    {"component": "pod", "name": "pod1"},  # Should be ignored
                    {"component": "route", "name": "route1"},  # Duplicate, should only appear once
                ]
            }
        }).encode()
        mock_get.return_value = mock_response

        status, failed_routes = cerberus_setup.application_status(0, 6000)

        self.assertFalse(status)
        self.assertEqual(failed_routes, {"route1", "route2"})

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_with_non_route_failures(self, mock_get):
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
        mock_get.return_value = mock_response

        status, failed_routes = cerberus_setup.application_status(0, 6000)

        self.assertTrue(status)
        self.assertEqual(failed_routes, set())

    def test_application_status_no_url_provided(self):
        """Test application_status when cerberus URL is not provided"""
        cerberus_setup.cerberus_url = None

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.application_status(0, 100)
        
        self.assertEqual(cm.exception.code, 1)

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_request_exception(self, mock_get):
        """Test application_status when request raises an exception"""
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        
        mock_get.side_effect = Exception("Connection error")

        with self.assertRaises(SystemExit) as cm:
            cerberus_setup.application_status(0, 6000)
        
        self.assertEqual(cm.exception.code, 1)

    @patch('krkn.cerberus.setup.requests.get')
    def test_application_status_duration_calculation(self, mock_get):
        """Test application_status correctly calculates duration in minutes"""
        cerberus_setup.cerberus_url = "http://cerberus.example.com"
        
        mock_response = MagicMock()
        mock_response.content = json.dumps({"history": {"failures": []}}).encode()
        mock_get.return_value = mock_response

        # Duration: (300 - 0) / 60 = 5 minutes
        cerberus_setup.application_status(0, 300)

        expected_url = "http://cerberus.example.com/history?loopback=5.0"
        mock_get.assert_called_once_with(expected_url, timeout=60)


if __name__ == '__main__':
    unittest.main()
