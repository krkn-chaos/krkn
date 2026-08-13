#!/usr/bin/env python3

"""
Test suite for standalone mode extensions to existing plugins
(hogs, network chaos, time actions).

Usage:
    python -m coverage run -a -m unittest tests/test_standalone_extensions.py -v
"""

import unittest
import sys
from unittest.mock import MagicMock, patch, mock_open

sys.modules['boto3'] = MagicMock()
sys.modules['jinja2'] = MagicMock()

from krkn_lib.models.krkn import HogConfig, HogType
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor


class TestHogsStandaloneExtension(unittest.TestCase):
    """Test standalone SSH delivery path in HogsScenarioPlugin."""

    def setUp(self):
        from krkn.scenario_plugins.hogs.hogs_scenario_plugin import (
            HogsScenarioPlugin,
        )
        self.plugin = HogsScenarioPlugin()

    def test_build_stress_command_cpu(self):
        config = HogConfig()
        config.type = HogType.cpu
        config.workers = 4
        config.cpu_load_percentage = 80
        config.duration = 60
        cmd = self.plugin._build_stress_command(config)
        self.assertIn("--cpu 4", cmd)
        self.assertIn("--cpu-load 80", cmd)
        self.assertIn("--timeout 60s", cmd)

    def test_build_stress_command_memory(self):
        config = HogConfig()
        config.type = HogType.memory
        config.workers = 2
        config.memory_vm_bytes = "512M"
        config.duration = 120
        cmd = self.plugin._build_stress_command(config)
        self.assertIn("--vm 2", cmd)
        self.assertIn("--vm-bytes 512M", cmd)
        self.assertIn("--vm-keep", cmd)

    def test_build_stress_command_io(self):
        config = HogConfig()
        config.type = HogType.io
        config.workers = 1
        config.io_write_bytes = "2G"
        config.duration = 30
        cmd = self.plugin._build_stress_command(config)
        self.assertIn("--iomix 1", cmd)
        self.assertIn("--iomix-bytes 2G", cmd)

    @patch("krkn.scenario_plugins.hogs.hogs_scenario_plugin.SSHExecutor")
    def test_run_standalone_success(self, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.side_effect = [
            (0, "/usr/bin/stress-ng\n", ""),  # which stress-ng
            (0, "4\n", ""),                   # nproc
            (0, "done\n", ""),                # stress-ng execution
        ]
        mock_ssh_cls.return_value = mock_ssh

        scenario = {
            "hog-type": "cpu",
            "node-selector": "",
            "targets": ["10.0.0.1"],
            "duration": 1,
            "cpu-load-percentage": 50,
        }

        result = self.plugin._run_standalone(scenario, ["10.0.0.1"])
        self.assertEqual(result, 0)

    @patch("krkn.scenario_plugins.hogs.hogs_scenario_plugin.SSHExecutor")
    def test_run_standalone_stress_ng_not_found(self, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (1, "", "not found")
        mock_ssh_cls.return_value = mock_ssh

        scenario = {
            "hog-type": "cpu",
            "node-selector": "",
            "targets": ["10.0.0.1"],
            "duration": 1,
        }

        with self.assertRaises(Exception) as ctx:
            self.plugin._run_standalone(scenario, ["10.0.0.1"])
        self.assertIn("stress-ng not found", str(ctx.exception))

    @patch(
        "builtins.open",
        mock_open(
            read_data="hog-type: cpu\nnode-selector: ''\ntargets:\n  - 10.0.0.1\nduration: 1\nworkers: 2\n"
        ),
    )
    @patch("krkn.scenario_plugins.hogs.hogs_scenario_plugin.SSHExecutor")
    def test_run_dispatches_to_standalone(self, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.side_effect = [
            (0, "/usr/bin/stress-ng\n", ""),  # which stress-ng
            (0, "done\n", ""),                # stress-ng execution
        ]
        mock_ssh_cls.return_value = mock_ssh

        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        self.assertEqual(result, 0)


class TestNetworkChaosStandaloneExtension(unittest.TestCase):
    """Test standalone SSH delivery path in NetworkChaosScenarioPlugin."""

    def setUp(self):
        from krkn.scenario_plugins.network_chaos.network_chaos_scenario_plugin import (
            NetworkChaosScenarioPlugin,
        )
        self.plugin = NetworkChaosScenarioPlugin()

    def test_get_egress_cmd_reuse(self):
        """Verify get_egress_cmd builds tc commands regardless of mode."""
        cmd = self.plugin.get_egress_cmd(
            "serial", ["eth0"], "latency", {"latency": "100ms"}, duration=60
        )
        self.assertIn("tc qdisc add", cmd)
        self.assertIn("netem", cmd)
        self.assertIn("delay", cmd)
        self.assertIn("100ms", cmd)
        self.assertIn("tc qdisc del", cmd)

    @patch("krkn.scenario_plugins.network_chaos.network_chaos_scenario_plugin.SSHExecutor")
    def test_run_standalone_success(self, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "eth0\n", "")
        mock_ssh_cls.return_value = mock_ssh

        test_dict = {
            "targets": ["10.0.0.1"],
            "ssh_user": "root",
            "ssh_private_key": "~/.ssh/id_rsa",
            "duration": 1,
            "interfaces": ["eth0"],
            "execution": "serial",
            "egress": {"latency": "50ms"},
        }

        result = self.plugin._run_standalone(test_dict, ["10.0.0.1"])
        self.assertEqual(result, 0)

    @patch(
        "builtins.open",
        mock_open(
            read_data="network_chaos:\n  targets:\n    - 10.0.0.1\n  duration: 1\n  interfaces:\n    - eth0\n  execution: serial\n  egress:\n    latency: 50ms\n"
        ),
    )
    @patch("krkn.scenario_plugins.network_chaos.network_chaos_scenario_plugin.SSHExecutor")
    def test_run_dispatches_to_standalone(self, mock_ssh_cls):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "", "")
        mock_ssh_cls.return_value = mock_ssh

        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        self.assertEqual(result, 0)


class TestTimeActionsStandaloneExtension(unittest.TestCase):
    """Test standalone SSH delivery path in TimeActionsScenarioPlugin."""

    def setUp(self):
        from krkn.scenario_plugins.time_actions.time_actions_scenario_plugin import (
            TimeActionsScenarioPlugin,
        )
        self.plugin = TimeActionsScenarioPlugin()

    @patch("krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.datetime")
    @patch("krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.SSHExecutor")
    @patch("krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.time")
    def test_run_standalone_success(self, mock_time, mock_ssh_cls, mock_datetime):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "ok\n", "")
        mock_ssh_cls.return_value = mock_ssh
        mock_time.sleep = MagicMock()
        import datetime as real_dt
        now = real_dt.datetime.utcnow()
        mock_datetime.datetime.utcnow.return_value = now
        mock_datetime.timedelta = real_dt.timedelta
        mock_datetime.MINYEAR = real_dt.MINYEAR

        time_scenario = {
            "action": "skew_time",
            "targets": ["10.0.0.1"],
            "ssh_user": "root",
            "ssh_private_key": "~/.ssh/id_rsa",
            "duration": 1,
            "disable_ntp": False,
        }

        result = self.plugin._run_standalone(time_scenario, ["10.0.0.1"])
        mock_ssh.execute.assert_called()

    @patch(
        "builtins.open",
        mock_open(
            read_data="time_scenarios:\n  - action: skew_time\n    targets:\n      - 10.0.0.1\n    duration: 1\n    disable_ntp: false\n"
        ),
    )
    @patch("krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.datetime")
    @patch("krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.SSHExecutor")
    @patch("krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.time")
    def test_run_dispatches_to_standalone(self, mock_time, mock_ssh_cls, mock_datetime):
        mock_ssh = MagicMock(spec=SSHExecutor)
        mock_ssh.execute.return_value = (0, "ok\n", "")
        mock_ssh_cls.return_value = mock_ssh
        mock_time.sleep = MagicMock()
        import datetime as real_dt
        now = real_dt.datetime.utcnow()
        mock_datetime.datetime.utcnow.return_value = now
        mock_datetime.timedelta = real_dt.timedelta
        mock_datetime.MINYEAR = real_dt.MINYEAR

        result = self.plugin.run("uuid", "test.yml", MagicMock(), MagicMock())
        mock_ssh.execute.assert_called()


if __name__ == "__main__":
    unittest.main()
