#!/usr/bin/env python3

"""
Test suite for SSH node scenarios (standalone mode)

Usage:
    python -m coverage run -a -m unittest tests/test_ssh_node_scenarios.py -v
"""

import unittest
import sys
from unittest.mock import MagicMock, patch, call

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

from krkn.scenario_plugins.node_actions.ssh_node_scenarios import (
    SSHExecutor,
    ssh_node_scenarios,
)


class TestSSHExecutor(unittest.TestCase):
    """Test cases for SSHExecutor class"""

    def setUp(self):
        self.executor = SSHExecutor(
            ssh_user="root",
            ssh_private_key="/tmp/test_key",
            ssh_port=22,
            connect_timeout=10,
        )

    @patch("krkn_lib.utils.ssh_executor.paramiko")
    def test_execute_success(self, mock_paramiko):
        mock_ssh = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_ssh
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"output"
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_ssh.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        exit_code, stdout, stderr = self.executor.execute("10.0.0.1", "uptime")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "output")
        self.assertEqual(stderr, "")
        mock_ssh.connect.assert_called_once_with(
            "10.0.0.1",
            port=22,
            username="root",
            key_filename="/tmp/test_key",
            timeout=10,
            banner_timeout=10,
        )
        mock_ssh.close.assert_called_once()

    @patch("krkn_lib.utils.ssh_executor.paramiko")
    def test_execute_connection_failure(self, mock_paramiko):
        mock_ssh = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_ssh
        mock_ssh.connect.side_effect = Exception("Connection refused")

        with self.assertRaises(Exception):
            self.executor.execute("10.0.0.1", "uptime")
        mock_ssh.close.assert_called_once()

    @patch("krkn_lib.utils.ssh_executor.paramiko")
    def test_is_host_reachable_true(self, mock_paramiko):
        mock_ssh = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_ssh

        result = self.executor.is_host_reachable("10.0.0.1")

        self.assertTrue(result)
        mock_ssh.close.assert_called_once()

    @patch("krkn_lib.utils.ssh_executor.paramiko")
    def test_is_host_reachable_false(self, mock_paramiko):
        mock_ssh = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_ssh
        mock_ssh.connect.side_effect = Exception("Connection refused")

        result = self.executor.is_host_reachable("10.0.0.1")

        self.assertFalse(result)

    @patch("krkn_lib.utils.ssh_executor.time")
    @patch("krkn_lib.utils.ssh_executor.paramiko")
    def test_wait_for_host_reachable(self, mock_paramiko, mock_time):
        mock_ssh = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_ssh
        mock_time.time.side_effect = [0, 5, 10]
        mock_time.sleep = MagicMock()

        result = self.executor.wait_for_host(
            "10.0.0.1", timeout=60, reachable=True
        )

        self.assertTrue(result)

    @patch("krkn_lib.utils.ssh_executor.time")
    @patch("krkn_lib.utils.ssh_executor.paramiko")
    def test_wait_for_host_timeout(self, mock_paramiko, mock_time):
        mock_ssh = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_ssh
        mock_ssh.connect.side_effect = Exception("Connection refused")
        mock_time.time.side_effect = [0, 100]
        mock_time.sleep = MagicMock()

        result = self.executor.wait_for_host(
            "10.0.0.1", timeout=5, reachable=True
        )

        self.assertFalse(result)


class TestSSHNodeScenarios(unittest.TestCase):
    """Test cases for ssh_node_scenarios class"""

    def setUp(self):
        self.mock_kubecli = MagicMock(spec=KrknKubernetes)
        self.affected_nodes_status = AffectedNodeStatus()
        self.ssh_config = {
            "ssh_user": "root",
            "ssh_private_key": "/tmp/test_key",
            "ssh_port": 22,
            "ssh_connect_timeout": 10,
        }
        self.scenarios = ssh_node_scenarios(
            self.mock_kubecli,
            False,
            self.affected_nodes_status,
            self.ssh_config,
        )
        self.scenarios.ssh = MagicMock(spec=SSHExecutor)

    def test_node_reboot_scenario(self):
        self.scenarios.ssh.execute.side_effect = Exception("Connection closed")
        self.scenarios.ssh.wait_for_host.return_value = True

        self.scenarios.node_reboot_scenario(1, "10.0.0.1", 300)

        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    def test_node_stop_scenario(self):
        self.scenarios.ssh.execute.side_effect = Exception("Connection closed")
        self.scenarios.ssh.wait_for_host.return_value = True

        self.scenarios.node_stop_scenario(1, "10.0.0.1", 300, 15)

        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    def test_node_crash_scenario(self):
        self.scenarios.ssh.execute.side_effect = Exception("Connection closed")

        self.scenarios.node_crash_scenario(1, "10.0.0.1", 300)

    def test_stop_kubelet_scenario(self):
        self.scenarios.ssh.execute.return_value = (0, "", "")

        self.scenarios.stop_kubelet_scenario(1, "10.0.0.1", 300)

        self.scenarios.ssh.execute.assert_called_with(
            "10.0.0.1", "sudo systemctl stop kubelet", timeout=60
        )
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    def test_stop_kubelet_scenario_failure(self):
        self.scenarios.ssh.execute.return_value = (1, "", "kubelet not found")

        with self.assertRaises(Exception):
            self.scenarios.stop_kubelet_scenario(1, "10.0.0.1", 300)

    def test_restart_kubelet_scenario(self):
        self.scenarios.ssh.execute.return_value = (0, "", "")

        self.scenarios.restart_kubelet_scenario(1, "10.0.0.1", 300)

        self.scenarios.ssh.execute.assert_called_with(
            "10.0.0.1", "sudo systemctl restart kubelet", timeout=60
        )
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    def test_node_start_scenario_unsupported(self):
        self.scenarios.node_start_scenario(1, "10.0.0.1", 300, 15)

    def test_node_termination_scenario_unsupported(self):
        self.scenarios.node_termination_scenario(1, "10.0.0.1", 300, 15)

    def test_multiple_kill_count(self):
        self.scenarios.ssh.execute.side_effect = Exception("Connection closed")
        self.scenarios.ssh.wait_for_host.return_value = True

        self.scenarios.node_reboot_scenario(3, "10.0.0.1", 300)

        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 3)


if __name__ == "__main__":
    unittest.main()
