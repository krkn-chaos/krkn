#!/usr/bin/env python3

"""
Test suite for StandaloneHostHealthCheckPlugin

Usage:
    python -m coverage run -a -m unittest tests/test_standalone_host_health_check_plugin.py -v
"""

import queue
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules['boto3'] = MagicMock()

from krkn.health_checks.standalone_host_health_check_plugin import (
    StandaloneHostHealthCheckPlugin,
)
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor


class TestStandaloneHostHealthCheckPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = StandaloneHostHealthCheckPlugin(iterations=1)

    def test_get_scenario_types(self):
        self.assertEqual(
            self.plugin.get_health_check_types(),
            ["standalone_host_health_check"],
        )

    def test_get_config_key(self):
        self.assertEqual(
            self.plugin.get_config_key(), "standalone_health_checks"
        )

    def test_check_tcp_reachable(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        with patch(
            "krkn.health_checks.standalone_host_health_check_plugin.is_host_reachable",
            return_value=True,
        ):
            status, code = self.plugin._check_tcp(mock_ssh, "10.0.0.1", 8080)
        self.assertTrue(status)
        self.assertEqual(code, 200)

    def test_check_tcp_unreachable(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        with patch(
            "krkn.health_checks.standalone_host_health_check_plugin.is_host_reachable",
            return_value=False,
        ):
            status, code = self.plugin._check_tcp(mock_ssh, "10.0.0.1", 8080)
        self.assertFalse(status)
        self.assertEqual(code, 503)

    def test_check_process_found(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "1234", "")

        status, code = self.plugin._check_process(
            mock_ssh, "10.0.0.1", "nginx"
        )
        self.assertTrue(status)
        self.assertEqual(code, 200)

    def test_check_process_not_found(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (1, "", "")

        status, code = self.plugin._check_process(
            mock_ssh, "10.0.0.1", "nginx"
        )
        self.assertFalse(status)
        self.assertEqual(code, 503)

    def test_check_process_empty_name(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        status, code = self.plugin._check_process(mock_ssh, "10.0.0.1", "")
        self.assertFalse(status)
        self.assertEqual(code, 400)

    def test_check_http_success(self):
        with patch(
            "krkn.health_checks.standalone_host_health_check_plugin.requests.get"
        ) as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            status, code = self.plugin._check_http("http://10.0.0.1/health")
        self.assertTrue(status)
        self.assertEqual(code, 200)

    def test_check_http_failure(self):
        with patch(
            "krkn.health_checks.standalone_host_health_check_plugin.requests.get"
        ) as mock_get:
            mock_get.return_value = MagicMock(status_code=500)
            status, code = self.plugin._check_http("http://10.0.0.1/health")
        self.assertFalse(status)
        self.assertEqual(code, 500)

    def test_check_http_exception(self):
        with patch(
            "krkn.health_checks.standalone_host_health_check_plugin.requests.get",
            side_effect=Exception("connection refused"),
        ):
            status, code = self.plugin._check_http("http://10.0.0.1/health")
        self.assertFalse(status)
        self.assertEqual(code, 503)

    def test_check_command_allowed(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")

        status, code = self.plugin._check_command(
            mock_ssh, "10.0.0.1", "systemctl status nginx"
        )
        self.assertTrue(status)
        self.assertEqual(code, 200)

    def test_check_command_blocked(self):
        mock_ssh = MagicMock(spec=SSHExecutor)

        status, code = self.plugin._check_command(
            mock_ssh, "10.0.0.1", "rm -rf /"
        )
        self.assertFalse(status)
        self.assertEqual(code, 403)
        mock_ssh.execute.assert_not_called()

    def test_check_command_empty(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        status, code = self.plugin._check_command(
            mock_ssh, "10.0.0.1", ""
        )
        self.assertFalse(status)
        self.assertEqual(code, 400)

    def test_check_host_metrics_success(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (
            0,
            "1.5\n4000000000 8000000000\n45",
            "",
        )

        status, code = self.plugin._check_host_metrics(mock_ssh, "10.0.0.1")
        self.assertTrue(status)
        self.assertEqual(code, 200)

    def test_check_host_metrics_ssh_failure(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (1, "", "connection refused")

        status, code = self.plugin._check_host_metrics(mock_ssh, "10.0.0.1")
        self.assertFalse(status)
        self.assertEqual(code, 503)

    def test_exit_on_failure_initial_unhealthy(self):
        """If first check is unhealthy and exit_on_failure is True,
        ret_value should be set to 3 immediately."""
        plugin = StandaloneHostHealthCheckPlugin(iterations=1)
        plugin.current_iterations = 0

        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (1, "", "")

        config = {
            "interval": 0,
            "ssh_user": "root",
            "ssh_private_key": "~/.ssh/id_rsa",
            "ssh_port": 22,
            "config": [
                {
                    "host": "10.0.0.1",
                    "exit_on_failure": True,
                    "checks": [{"type": "process", "name": "nginx"}],
                }
            ],
        }

        telemetry_queue = queue.Queue()

        with patch(
            "krkn.health_checks.standalone_host_health_check_plugin.SSHExecutor",
            return_value=mock_ssh,
        ):
            # Simulate one iteration then stop
            original_sleep = __import__("time").sleep

            def fake_sleep(t):
                plugin.current_iterations = plugin.iterations

            with patch("time.sleep", side_effect=fake_sleep):
                plugin.run_health_check(config, telemetry_queue)

        self.assertEqual(plugin.ret_value, 3)

    def test_increment_iterations(self):
        self.assertEqual(self.plugin.current_iterations, 0)
        self.plugin.increment_iterations()
        self.assertEqual(self.plugin.current_iterations, 1)

    def test_check_command_allowed_prefixes(self):
        """Verify several allowed command prefixes pass the whitelist."""
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")

        allowed_commands = [
            "systemctl is-active nginx",
            "pgrep -f sshd",
            "pidof httpd",
            "df -h",
            "free -m",
            "uptime",
            "cat /proc/loadavg",
            "ss -tlnp",
            "ip addr",
        ]
        for cmd in allowed_commands:
            status, code = self.plugin._check_command(
                mock_ssh, "10.0.0.1", cmd
            )
            self.assertTrue(
                status, "Command should be allowed: %s" % cmd
            )
            self.assertEqual(code, 200)


if __name__ == "__main__":
    unittest.main()
