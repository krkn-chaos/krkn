#!/usr/bin/env python3

"""
Test suite for standalone disk fill scenario plugin

Usage:
    python -m coverage run -a -m unittest tests/test_standalone_disk_fill_scenario_plugin.py -v
"""

import unittest
import sys
from unittest.mock import MagicMock, patch, mock_open

sys.modules['boto3'] = MagicMock()

from krkn.scenario_plugins.standalone_disk_fill.standalone_disk_fill_scenario_plugin import (
    StandaloneDiskFillScenarioPlugin,
)
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor


class TestStandaloneDiskFillScenarioPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = StandaloneDiskFillScenarioPlugin()

    def test_get_scenario_types(self):
        self.assertEqual(
            self.plugin.get_scenario_types(),
            ["standalone_disk_fill_scenarios"],
        )

    def test_fill_disk_by_size(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")

        self.plugin._fill_disk(mock_ssh, "10.0.0.1", "/tmp", "1G", 0)

        mock_ssh.execute.assert_called_once_with(
            "10.0.0.1", "fallocate -l 1G /tmp/krkn_disk_fill_chaos", timeout=120
        )

    def test_fill_disk_by_percentage(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.side_effect = [
            (0, "5000000000 10000000000", ""),
            (0, "", ""),
        ]

        self.plugin._fill_disk(mock_ssh, "10.0.0.1", "/tmp", "", 90)

        calls = mock_ssh.execute.call_args_list
        self.assertIn("df --output=avail,size", str(calls[0]))
        self.assertIn("fallocate", str(calls[1]))

    def test_fill_disk_already_full(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "100000000 10000000000", "")

        self.plugin._fill_disk(mock_ssh, "10.0.0.1", "/tmp", "", 5)

    def test_cleanup(self):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")

        self.plugin._cleanup(mock_ssh, "10.0.0.1")

        mock_ssh.execute.assert_called_once()
        self.assertIn("rm -f", str(mock_ssh.execute.call_args))

    @patch("krkn.scenario_plugins.standalone_disk_fill.standalone_disk_fill_scenario_plugin.SSHExecutor")
    @patch("krkn.scenario_plugins.standalone_disk_fill.standalone_disk_fill_scenario_plugin.time")
    @patch("builtins.open", mock_open(read_data="targets:\n  - 10.0.0.1\nfill_path: /tmp\nfill_size: 100M\nduration: 1\n"))
    def test_run_success(self, mock_time, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")
        mock_ssh_cls.return_value = mock_ssh
        mock_time.sleep = MagicMock()

        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        self.assertEqual(result, 0)

    @patch("builtins.open", mock_open(read_data="targets:\n  - 10.0.0.1\nfill_path: /tmp\nduration: 1\n"))
    def test_run_no_fill_params(self):
        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        self.assertEqual(result, 1)

    @patch("builtins.open", mock_open(read_data="fill_size: 100M\n"))
    def test_run_no_targets(self):
        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
