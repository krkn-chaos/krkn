#!/usr/bin/env python3

"""
Test suite for SimpleHTTPRequestHandler class

Usage:
    python -m coverage run -a -m unittest tests/test_server.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO

import server
from server import SimpleHTTPRequestHandler


class TestSimpleHTTPRequestHandler(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for SimpleHTTPRequestHandler
        """
        # Reset the global server_status before each test
        server.server_status = ""
        # Reset the requests_served counter
        SimpleHTTPRequestHandler.requests_served = 0

        # Create a mock request
        self.mock_request = MagicMock()
        self.mock_client_address = ('127.0.0.1', 12345)
        self.mock_server = MagicMock()

    def _create_handler(self, method='GET', path='/'):
        """
        Helper method to create a handler instance with mocked request
        """
        # Create a mock request with proper attributes
        mock_request = MagicMock()
        mock_request.makefile.return_value = BytesIO(
            f"{method} {path} HTTP/1.1\r\n\r\n".encode('utf-8')
        )

        # Create handler
        handler = SimpleHTTPRequestHandler(
            mock_request,
            self.mock_client_address,
            self.mock_server
        )

        # Mock the wfile (write file) for response
        handler.wfile = BytesIO()

        return handler

    def test_do_GET_root_path_calls_do_status(self):
        """
        Test do_GET with root path calls do_status
        """
        handler = self._create_handler('GET', '/')

        with patch.object(handler, 'do_status') as mock_do_status:
            handler.do_GET()
            mock_do_status.assert_called_once()

    def test_do_GET_non_root_path_does_nothing(self):
        """
        Test do_GET with non-root path does not call do_status
        """
        handler = self._create_handler('GET', '/other')

        with patch.object(handler, 'do_status') as mock_do_status:
            handler.do_GET()
            mock_do_status.assert_not_called()

    def test_do_status_sends_200_response(self):
        """
        Test do_status sends 200 status code
        """
        server.server_status = "TEST_STATUS"
        handler = self._create_handler()

        with patch.object(handler, 'send_response') as mock_send_response:
            with patch.object(handler, 'end_headers'):
                handler.do_status()
                mock_send_response.assert_called_once_with(200)

    def test_do_status_writes_server_status(self):
        """
        Test do_status writes server_status to response
        """
        server.server_status = "RUNNING"
        handler = self._create_handler()

        with patch.object(handler, 'send_response'):
            with patch.object(handler, 'end_headers'):
                handler.do_status()

        # Check that the status was written to wfile
        response_content = handler.wfile.getvalue().decode('utf-8')
        self.assertEqual(response_content, "RUNNING")

    def test_do_status_increments_requests_served(self):
        """
        Test do_status increments requests_served counter
        """
        # Note: Creating a handler increments the counter by 1
        # Then do_status increments it again
        SimpleHTTPRequestHandler.requests_served = 0
        handler = self._create_handler()
        initial_count = SimpleHTTPRequestHandler.requests_served

        with patch.object(handler, 'send_response'):
            with patch.object(handler, 'end_headers'):
                handler.do_status()

        self.assertEqual(
            SimpleHTTPRequestHandler.requests_served,
            initial_count + 1
        )

    def test_do_status_multiple_requests_increment_counter(self):
        """
        Test multiple do_status calls increment counter correctly
        """
        SimpleHTTPRequestHandler.requests_served = 0

        for i in range(5):
            handler = self._create_handler()
            with patch.object(handler, 'send_response'):
                with patch.object(handler, 'end_headers'):
                    handler.do_status()

        # Each iteration: handler creation increments by 1, do_status increments by 1
        # Total: 5 * 2 = 10
        self.assertEqual(SimpleHTTPRequestHandler.requests_served, 10)

    def test_do_POST_STOP_path_calls_set_stop(self):
        """
        Test do_POST with /STOP path calls set_stop
        """
        handler = self._create_handler('POST', '/STOP')

        with patch.object(handler, 'set_stop') as mock_set_stop:
            handler.do_POST()
            mock_set_stop.assert_called_once()

    def test_do_POST_RUN_path_calls_set_run(self):
        """
        Test do_POST with /RUN path calls set_run
        """
        handler = self._create_handler('POST', '/RUN')

        with patch.object(handler, 'set_run') as mock_set_run:
            handler.do_POST()
            mock_set_run.assert_called_once()

    def test_do_POST_PAUSE_path_calls_set_pause(self):
        """
        Test do_POST with /PAUSE path calls set_pause
        """
        handler = self._create_handler('POST', '/PAUSE')

        with patch.object(handler, 'set_pause') as mock_set_pause:
            handler.do_POST()
            mock_set_pause.assert_called_once()

    def test_do_POST_unknown_path_does_nothing(self):
        """
        Test do_POST with unknown path does not call any setter
        """
        handler = self._create_handler('POST', '/UNKNOWN')

        with patch.object(handler, 'set_stop') as mock_set_stop:
            with patch.object(handler, 'set_run') as mock_set_run:
                with patch.object(handler, 'set_pause') as mock_set_pause:
                    handler.do_POST()
                    mock_set_stop.assert_not_called()
                    mock_set_run.assert_not_called()
                    mock_set_pause.assert_not_called()

    def test_set_run_sets_status_to_RUN(self):
        """
        Test set_run sets global server_status to 'RUN'
        """
        handler = self._create_handler()

        with patch.object(handler, 'send_response'):
            with patch.object(handler, 'end_headers'):
                handler.set_run()

        self.assertEqual(server.server_status, 'RUN')

    def test_set_run_sends_200_response(self):
        """
        Test set_run sends 200 status code
        """
        handler = self._create_handler()

        with patch.object(handler, 'send_response') as mock_send_response:
            with patch.object(handler, 'end_headers'):
                handler.set_run()
                mock_send_response.assert_called_once_with(200)

    def test_set_stop_sets_status_to_STOP(self):
        """
        Test set_stop sets global server_status to 'STOP'
        """
        handler = self._create_handler()

        with patch.object(handler, 'send_response'):
            with patch.object(handler, 'end_headers'):
                handler.set_stop()

        self.assertEqual(server.server_status, 'STOP')

    def test_set_stop_sends_200_response(self):
        """
        Test set_stop sends 200 status code
        """
        handler = self._create_handler()

        with patch.object(handler, 'send_response') as mock_send_response:
            with patch.object(handler, 'end_headers'):
                handler.set_stop()
                mock_send_response.assert_called_once_with(200)

    def test_set_pause_sets_status_to_PAUSE(self):
        """
        Test set_pause sets global server_status to 'PAUSE'
        """
        handler = self._create_handler()

        with patch.object(handler, 'send_response'):
            with patch.object(handler, 'end_headers'):
                handler.set_pause()

        self.assertEqual(server.server_status, 'PAUSE')

    def test_set_pause_sends_200_response(self):
        """
        Test set_pause sends 200 status code
        """
        handler = self._create_handler()

        with patch.object(handler, 'send_response') as mock_send_response:
            with patch.object(handler, 'end_headers'):
                handler.set_pause()
                mock_send_response.assert_called_once_with(200)

    def test_requests_served_is_class_variable(self):
        """
        Test requests_served is shared across all instances
        """
        SimpleHTTPRequestHandler.requests_served = 0

        handler1 = self._create_handler()  # Increments to 1
        handler2 = self._create_handler()  # Increments to 2

        with patch.object(handler1, 'send_response'):
            with patch.object(handler1, 'end_headers'):
                handler1.do_status()  # Increments to 3

        with patch.object(handler2, 'send_response'):
            with patch.object(handler2, 'end_headers'):
                handler2.do_status()  # Increments to 4

        # Both handlers should see the same counter
        # 2 handler creations + 2 do_status calls = 4
        self.assertEqual(handler1.requests_served, 4)
        self.assertEqual(handler2.requests_served, 4)
        self.assertEqual(SimpleHTTPRequestHandler.requests_served, 4)


class TestServerModuleFunctions(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for server module functions
        """
        server.server_status = ""

    def test_publish_kraken_status_sets_server_status(self):
        """
        Test publish_kraken_status sets global server_status
        """
        server.publish_kraken_status("NEW_STATUS")
        self.assertEqual(server.server_status, "NEW_STATUS")

    def test_publish_kraken_status_overwrites_existing_status(self):
        """
        Test publish_kraken_status overwrites existing status
        """
        server.server_status = "OLD_STATUS"
        server.publish_kraken_status("NEW_STATUS")
        self.assertEqual(server.server_status, "NEW_STATUS")

    @patch('server.HTTPServer')
    @patch('server._thread')
    def test_start_server_creates_http_server(self, mock_thread, mock_http_server):
        """
        Test start_server creates HTTPServer with correct address
        """
        address = ("localhost", 8080)
        mock_server_instance = MagicMock()
        mock_http_server.return_value = mock_server_instance

        server.start_server(address, "RUNNING")

        mock_http_server.assert_called_once_with(
            address,
            SimpleHTTPRequestHandler
        )

    @patch('server.HTTPServer')
    @patch('server._thread')
    def test_start_server_starts_thread(self, mock_thread, mock_http_server):
        """
        Test start_server starts a new thread for serve_forever
        """
        address = ("localhost", 8080)
        mock_server_instance = MagicMock()
        mock_http_server.return_value = mock_server_instance

        server.start_server(address, "RUNNING")

        mock_thread.start_new_thread.assert_called_once()
        # Check that serve_forever was passed to the thread
        args = mock_thread.start_new_thread.call_args[0]
        self.assertEqual(args[0], mock_server_instance.serve_forever)

    @patch('server.HTTPServer')
    @patch('server._thread')
    def test_start_server_publishes_status(self, mock_thread, mock_http_server):
        """
        Test start_server publishes the provided status
        """
        address = ("localhost", 8080)
        mock_server_instance = MagicMock()
        mock_http_server.return_value = mock_server_instance

        server.start_server(address, "INITIAL_STATUS")

        self.assertEqual(server.server_status, "INITIAL_STATUS")

    @patch('server.HTTPConnection')
    def test_get_status_makes_http_request(self, mock_http_connection):
        """
        Test get_status makes HTTP GET request to root path
        """
        address = ("localhost", 8080)
        mock_connection = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b"TEST_STATUS"
        mock_connection.getresponse.return_value = mock_response
        mock_http_connection.return_value = mock_connection

        result = server.get_status(address)

        mock_http_connection.assert_called_once_with("localhost", 8080)
        mock_connection.request.assert_called_once_with("GET", "/")
        self.assertEqual(result, "TEST_STATUS")

    @patch('server.HTTPConnection')
    def test_get_status_returns_decoded_response(self, mock_http_connection):
        """
        Test get_status returns decoded response string
        """
        address = ("localhost", 8080)
        mock_connection = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b"RUNNING"
        mock_connection.getresponse.return_value = mock_response
        mock_http_connection.return_value = mock_connection

        result = server.get_status(address)

        self.assertEqual(result, "RUNNING")
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
