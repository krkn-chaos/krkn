#!/usr/bin/env python3

"""
Test suite for standalone file scenario plugin

Usage:
    python -m coverage run -a -m unittest tests/test_standalone_file_scenario_plugin.py -v
"""

import unittest
import sys
from unittest.mock import MagicMock, patch, mock_open

sys.modules['boto3'] = MagicMock()

from krkn.scenario_plugins.standalone_file.standalone_file_scenario_plugin import (
    StandaloneFileScenarioPlugin,
)
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor


class TestStandaloneFileScenarioPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = StandaloneFileScenarioPlugin()

    def test_get_scenario_types(self):
        self.assertEqual(
            self.plugin.get_scenario_types(), ["standalone_file_scenarios"]
        )

    def test_apply_chmod(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "644", "")
        config = {"permissions": "000"}

        revert = self.plugin._apply_file_chaos(
            mock_ssh, "10.0.0.1", "chmod", "/etc/nginx/nginx.conf", config
        )

        self.assertEqual(revert["original_perms"], "644")
        calls = mock_ssh.execute.call_args_list
        self.assertIn("chmod 000", str(calls[1]))

    def test_apply_rename(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")
        config = {"target_path": "/etc/nginx/nginx.conf.bak"}

        revert = self.plugin._apply_file_chaos(
            mock_ssh, "10.0.0.1", "rename", "/etc/nginx/nginx.conf", config
        )

        self.assertEqual(revert["target_path"], "/etc/nginx/nginx.conf.bak")
        self.assertIn("mv", str(mock_ssh.execute.call_args))

    def test_apply_append(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "1024", "")
        config = {"content": "chaos", "count": 2}

        revert = self.plugin._apply_file_chaos(
            mock_ssh, "10.0.0.1", "append", "/tmp/test.txt", config
        )

        self.assertEqual(revert["original_size"], "1024")
        self.assertEqual(mock_ssh.execute.call_count, 3)

    def test_apply_delete(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")
        config = {}

        revert = self.plugin._apply_file_chaos(
            mock_ssh, "10.0.0.1", "delete", "/tmp/test.txt", config
        )

        self.assertIn("backup_path", revert)

    def test_apply_unknown_action(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        with self.assertRaises(ValueError):
            self.plugin._apply_file_chaos(
                mock_ssh, "10.0.0.1", "invalid", "/tmp/test.txt", {}
            )

    def test_revert_chmod(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")

        self.plugin._revert_file_chaos(
            mock_ssh, "10.0.0.1", "chmod", "/tmp/test.txt",
            {"original_perms": "755"}
        )

        self.assertIn("chmod 755", str(mock_ssh.execute.call_args))

    def test_revert_rename(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")

        self.plugin._revert_file_chaos(
            mock_ssh, "10.0.0.1", "rename", "/tmp/test.txt",
            {"target_path": "/tmp/test.txt.bak"}
        )

        self.assertIn("mv /tmp/test.txt.bak /tmp/test.txt", str(mock_ssh.execute.call_args))

    def test_revert_append(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")

        self.plugin._revert_file_chaos(
            mock_ssh, "10.0.0.1", "append", "/tmp/test.txt",
            {"original_size": "1024"}
        )

        self.assertIn("truncate -s 1024", str(mock_ssh.execute.call_args))

    def test_revert_delete(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")

        self.plugin._revert_file_chaos(
            mock_ssh, "10.0.0.1", "delete", "/tmp/test.txt",
            {"backup_path": "/tmp/test.txt.krkn_bak"}
        )

        self.assertIn("mv /tmp/test.txt.krkn_bak /tmp/test.txt", str(mock_ssh.execute.call_args))

    @patch("krkn.scenario_plugins.standalone_file.standalone_file_scenario_plugin.SSHExecutor")
    @patch("builtins.open", mock_open(read_data="targets:\n  - 10.0.0.1\naction: chmod\nfile_path: /tmp/test.txt\npermissions: '000'\nduration: 1\n"))
    @patch("krkn.scenario_plugins.standalone_file.standalone_file_scenario_plugin.time")
    def test_run_success(self, mock_time, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "644", "")
        mock_ssh_cls.return_value = mock_ssh
        mock_time.sleep = MagicMock()

        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        self.assertEqual(result, 0)

    @patch("builtins.open", mock_open(read_data="action: chmod\nfile_path: /tmp/test.txt\n"))
    def test_run_no_targets(self):
        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        self.assertEqual(result, 1)

    @patch("builtins.open", mock_open(read_data="targets:\n  - 10.0.0.1\naction: chmod\n"))
    def test_run_no_file_path(self):
        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
