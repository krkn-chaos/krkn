#!/usr/bin/env python3

"""
Test suite for VM storage chaos scenario plugin

Usage:
    python -m coverage run -a -m unittest tests/test_vm_storage_chaos_scenario_plugin.py -v
"""

import unittest
import sys
from unittest.mock import MagicMock, patch, mock_open

sys.modules['boto3'] = MagicMock()

from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn.scenario_plugins.vm_storage_chaos.vm_storage_chaos_scenario_plugin import (
    VmStorageChaosScenarioPlugin,
)
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor


class TestVmStorageChaosScenarioPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = VmStorageChaosScenarioPlugin()

    def test_get_scenario_types(self):
        self.assertEqual(
            self.plugin.get_scenario_types(), ["vm_storage_chaos_scenarios"]
        )

    @patch("krkn.scenario_plugins.vm_storage_chaos.vm_storage_chaos_scenario_plugin.SSHExecutor")
    @patch("krkn.scenario_plugins.vm_storage_chaos.vm_storage_chaos_scenario_plugin.time")
    @patch(
        "builtins.open",
        mock_open(read_data=(
            "vm_storage_chaos:\n"
            "  action: kill_storage_service\n"
            "  storage_targets:\n"
            "    - host: 10.0.0.50\n"
            "      service: nfs-server\n"
            "  duration: 1\n"
        )),
    )
    def test_kill_storage_service(self, mock_time, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")
        mock_ssh_cls.return_value = mock_ssh
        mock_time.sleep = MagicMock()
        mock_time.time = MagicMock(side_effect=[0, 10])

        scenario_telemetry = MagicMock(spec=ScenarioTelemetry)
        scenario_telemetry.affected_nodes = []

        result = self.plugin.run(
            "uuid", "test.yml", MagicMock(), scenario_telemetry
        )

        self.assertEqual(result, 0)
        calls = [str(c) for c in mock_ssh.execute.call_args_list]
        self.assertTrue(any("systemctl stop" in c for c in calls))
        self.assertTrue(any("systemctl start" in c for c in calls))

    @patch("krkn.scenario_plugins.vm_storage_chaos.vm_storage_chaos_scenario_plugin.SSHExecutor")
    @patch("krkn.scenario_plugins.vm_storage_chaos.vm_storage_chaos_scenario_plugin.time")
    @patch(
        "builtins.open",
        mock_open(read_data=(
            "vm_storage_chaos:\n"
            "  action: io_burst\n"
            "  storage_targets:\n"
            "    - host: 10.0.0.1\n"
            "      path: /var/lib/containers\n"
            "  duration: 1\n"
            "  io_workers: 2\n"
            "  io_bytes: 500M\n"
        )),
    )
    def test_io_burst(self, mock_time, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "done", "")
        mock_ssh_cls.return_value = mock_ssh
        mock_time.sleep = MagicMock()
        mock_time.time = MagicMock(side_effect=[0, 5])

        scenario_telemetry = MagicMock(spec=ScenarioTelemetry)
        scenario_telemetry.affected_nodes = []

        result = self.plugin.run(
            "uuid", "test.yml", MagicMock(), scenario_telemetry
        )

        self.assertEqual(result, 0)
        calls = [str(c) for c in mock_ssh.execute.call_args_list]
        self.assertTrue(any("stress-ng" in c for c in calls))

    @patch("krkn.scenario_plugins.vm_storage_chaos.vm_storage_chaos_scenario_plugin.SSHExecutor")
    @patch("krkn.scenario_plugins.vm_storage_chaos.vm_storage_chaos_scenario_plugin.time")
    @patch(
        "builtins.open",
        mock_open(read_data=(
            "vm_storage_chaos:\n"
            "  action: fill_storage\n"
            "  storage_targets:\n"
            "    - host: 10.0.0.50\n"
            "      path: /var/lib/containers\n"
            "  duration: 1\n"
            "  fill_percentage: 90\n"
        )),
    )
    def test_fill_storage(self, mock_time, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.side_effect = [
            (0, "5000000000 10000000000", ""),
            (0, "", ""),
            (0, "", ""),
        ]
        mock_ssh_cls.return_value = mock_ssh
        mock_time.sleep = MagicMock()
        mock_time.time = MagicMock(side_effect=[0, 10])

        scenario_telemetry = MagicMock(spec=ScenarioTelemetry)
        scenario_telemetry.affected_nodes = []

        result = self.plugin.run(
            "uuid", "test.yml", MagicMock(), scenario_telemetry
        )

        self.assertEqual(result, 0)

    @patch("builtins.open", mock_open(read_data="vm_storage_chaos:\n  action: kill_storage_service\n"))
    def test_no_storage_targets(self):
        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        self.assertEqual(result, 1)

    @patch("builtins.open", mock_open(read_data="vm_storage_chaos:\n  action: invalid\n  storage_targets:\n    - host: x\n"))
    @patch("krkn.scenario_plugins.vm_storage_chaos.vm_storage_chaos_scenario_plugin.SSHExecutor")
    def test_invalid_action(self, mock_ssh_cls):
        mock_ssh_cls.return_value = MagicMock(spec=SSHExecutor)
        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        self.assertEqual(result, 1)

    @patch("krkn.scenario_plugins.vm_storage_chaos.vm_storage_chaos_scenario_plugin.SSHExecutor")
    @patch(
        "builtins.open",
        mock_open(read_data=(
            "vm_storage_chaos:\n"
            "  action: kill_storage_service\n"
            "  storage_targets:\n"
            "    - host: 10.0.0.50\n"
            "      service: nfs-server\n"
            "  duration: 1\n"
        )),
    )
    def test_stop_service_failure(self, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (1, "", "service not found")
        mock_ssh_cls.return_value = mock_ssh

        scenario_telemetry = MagicMock(spec=ScenarioTelemetry)
        scenario_telemetry.affected_nodes = []

        result = self.plugin.run(
            "uuid", "test.yml", MagicMock(), scenario_telemetry
        )

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
