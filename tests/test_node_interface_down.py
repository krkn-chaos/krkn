#!/usr/bin/env python3

"""
Test suite for NodeInterfaceDownModule class

Usage:
    python -m coverage run -a -m unittest tests/test_node_interface_down.py -v
"""

import unittest
import queue
from unittest.mock import MagicMock, patch

from krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down import (
    NodeInterfaceDownModule,
)
from krkn.scenario_plugins.network_chaos_ng.models import (
    InterfaceDownConfig,
    NetworkChaosScenarioType,
)


def make_config(**overrides) -> InterfaceDownConfig:
    defaults = dict(
        id="node_interface_down",
        image="test-image",
        wait_duration=0,
        test_duration=60,
        label_selector="node-role.kubernetes.io/worker=",
        service_account="",
        taints=[],
        namespace="default",
        instance_count=1,
        target="",
        execution="serial",
        interfaces=["eth0"],
        ingress=False,
        egress=False,
        recovery_time=0,
    )
    defaults.update(overrides)
    return InterfaceDownConfig(**defaults)


class TestInterfaceDownConfig(unittest.TestCase):

    def test_valid_config(self):
        config = make_config()
        errors = config.validate()
        self.assertEqual(errors, [])

    def test_invalid_recovery_time_negative(self):
        config = make_config(recovery_time=-1)
        errors = config.validate()
        self.assertTrue(any("recovery_time" in e for e in errors))

    def test_invalid_recovery_time_not_int(self):
        config = make_config(recovery_time="30s")
        errors = config.validate()
        self.assertTrue(any("recovery_time" in e for e in errors))

    def test_zero_recovery_time_is_valid(self):
        config = make_config(recovery_time=0)
        errors = config.validate()
        self.assertEqual(errors, [])

    def test_invalid_execution(self):
        config = make_config(execution="random")
        errors = config.validate()
        self.assertTrue(any("execution" in e for e in errors))

    def test_invalid_wait_duration(self):
        config = make_config(wait_duration="ten")
        errors = config.validate()
        self.assertTrue(any("wait_duration" in e for e in errors))

    def test_invalid_test_duration(self):
        config = make_config(test_duration="sixty")
        errors = config.validate()
        self.assertTrue(any("test_duration" in e for e in errors))


class TestNodeInterfaceDownModule(unittest.TestCase):

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes
        # Default: target node is immediately Ready after recovery
        self.mock_kubernetes.list_ready_nodes.return_value = ["worker-1"]

        self.config = make_config()
        self.module = NodeInterfaceDownModule(self.config, self.mock_kubecli)

    def test_initialization(self):
        self.assertEqual(self.module.config, self.config)
        self.assertEqual(self.module.kubecli, self.mock_kubecli)
        self.assertEqual(self.module.base_network_config, self.config)

    def test_get_config(self):
        scenario_type, config = self.module.get_config()
        self.assertEqual(scenario_type, NetworkChaosScenarioType.Node)
        self.assertEqual(config, self.config)

    def test_get_targets_with_label_selector(self):
        self.mock_kubernetes.list_ready_nodes.return_value = ["worker-1", "worker-2"]
        targets = self.module.get_targets()
        self.assertEqual(targets, ["worker-1", "worker-2"])
        self.mock_kubernetes.list_ready_nodes.assert_called_once_with(
            "node-role.kubernetes.io/worker="
        )

    def test_get_targets_with_target_name(self):
        self.config.label_selector = ""
        self.config.target = "worker-1"
        self.mock_kubernetes.list_ready_nodes.return_value = ["worker-1", "worker-2"]
        targets = self.module.get_targets()
        self.assertEqual(targets, ["worker-1"])

    def test_get_targets_node_not_found(self):
        self.config.label_selector = ""
        self.config.target = "non-existent"
        self.mock_kubernetes.list_ready_nodes.return_value = ["worker-1", "worker-2"]
        with self.assertRaises(Exception) as ctx:
            self.module.get_targets()
        self.assertIn("not found", str(ctx.exception))

    def test_get_targets_no_target_or_selector(self):
        self.config.label_selector = ""
        self.config.target = ""
        with self.assertRaises(Exception) as ctx:
            self.module.get_targets()
        self.assertIn("neither", str(ctx.exception))

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_brings_interface_down_and_up_in_single_command(self, _mock_log, _mock_deploy, _mock_sleep):
        self.config.interfaces = ["eth0"]

        self.module.run("worker-1")

        exec_calls = [str(c) for c in self.mock_kubernetes.exec_cmd_in_pod.call_args_list]
        self.assertEqual(len(exec_calls), 1)
        cmd = exec_calls[0]
        self.assertIn("ip link set eth0 down", cmd)
        self.assertIn("ip link set eth0 up", cmd)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_recovery_is_scheduled_before_interface_goes_down(self, _mock_log, _mock_deploy, mock_sleep):
        self.config.interfaces = ["eth0"]
        self.config.test_duration = 30

        self.module.run("worker-1")

        exec_calls = [str(c) for c in self.mock_kubernetes.exec_cmd_in_pod.call_args_list]
        cmd = exec_calls[0]
        # Background recovery (sleep + up) must appear before the down command
        self.assertIn("sleep 30", cmd)
        up_pos = cmd.index("ip link set eth0 up")
        down_pos = cmd.index("ip link set eth0 down")
        self.assertLess(up_pos, down_pos)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_sleeps_test_duration(self, mock_log, mock_deploy, mock_sleep):
        self.config.test_duration = 45
        self.config.recovery_time = 0

        self.module.run("worker-1")

        sleep_values = [c[0][0] for c in mock_sleep.call_args_list]
        self.assertIn(45, sleep_values)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_sleeps_recovery_time_when_set(self, mock_log, mock_deploy, mock_sleep):
        self.config.test_duration = 30
        self.config.recovery_time = 15

        self.module.run("worker-1")

        sleep_values = [c[0][0] for c in mock_sleep.call_args_list]
        self.assertIn(30, sleep_values)
        self.assertIn(15, sleep_values)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_no_recovery_sleep_when_zero(self, mock_log, mock_deploy, mock_sleep):
        self.config.test_duration = 30
        self.config.recovery_time = 0

        self.module.run("worker-1")

        sleep_values = [c[0][0] for c in mock_sleep.call_args_list]
        self.assertIn(30, sleep_values)
        self.assertNotIn(0, sleep_values)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_polls_node_readiness_after_sleep(self, mock_log, mock_deploy, mock_sleep):
        self.module.run("worker-1")

        self.mock_kubernetes.list_ready_nodes.assert_called()

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_error")
    def test_run_logs_error_when_node_does_not_recover(self, mock_log_error, mock_log, mock_deploy, mock_sleep):
        self.mock_kubernetes.list_ready_nodes.return_value = []

        self.module.run("worker-1")

        mock_log_error.assert_called()
        self.assertIn("Ready", str(mock_log_error.call_args))

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_deletes_pod_on_success(self, mock_log, mock_deploy, mock_sleep):
        self.module.run("worker-1")

        self.mock_kubernetes.delete_pod.assert_called_once()

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_deletes_pod_even_when_node_does_not_recover(self, mock_log, mock_deploy, mock_sleep):
        self.mock_kubernetes.list_ready_nodes.return_value = []

        self.module.run("worker-1")

        self.mock_kubernetes.delete_pod.assert_called_once()

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_multiple_interfaces(self, mock_log, mock_deploy, mock_sleep):
        self.config.interfaces = ["eth0", "eth1", "bond0"]

        self.module.run("worker-1")

        exec_calls = [str(c) for c in self.mock_kubernetes.exec_cmd_in_pod.call_args_list]
        self.assertEqual(len(exec_calls), 1)
        cmd = exec_calls[0]
        for iface in ["eth0", "eth1", "bond0"]:
            self.assertIn(f"ip link set {iface} down", cmd)
            self.assertIn(f"ip link set {iface} up", cmd)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.get_pod_default_interface")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_auto_detects_default_interface(self, mock_log, mock_get_iface, mock_deploy, mock_sleep):
        self.config.interfaces = []
        mock_get_iface.return_value = "ens3"

        self.module.run("worker-1")

        mock_get_iface.assert_called_once()
        exec_calls = [str(c) for c in self.mock_kubernetes.exec_cmd_in_pod.call_args_list]
        cmd = exec_calls[0]
        self.assertIn("ip link set ens3 down", cmd)
        self.assertIn("ip link set ens3 up", cmd)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.get_pod_default_interface")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_error")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_aborts_when_no_interface_detected(self, mock_log, mock_log_error, mock_get_iface, mock_deploy):
        self.config.interfaces = []
        mock_get_iface.return_value = ""

        self.module.run("worker-1")

        mock_log_error.assert_called()
        self.assertIn("could not detect", str(mock_log_error.call_args).lower())
        self.mock_kubernetes.delete_pod.assert_called_once()
        self.mock_kubernetes.exec_cmd_in_pod.assert_not_called()

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_raises_exception_without_error_queue(self, mock_log, mock_deploy):
        mock_deploy.side_effect = Exception("deploy failed")

        with self.assertRaises(Exception) as ctx:
            self.module.run("worker-1")

        self.assertIn("deploy failed", str(ctx.exception))

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.deploy_network_chaos_ng_pod")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_interface_down.log_info")
    def test_run_puts_error_in_queue_for_parallel(self, mock_log, mock_deploy):
        mock_deploy.side_effect = Exception("deploy failed")

        error_queue = queue.Queue()
        self.module.run("worker-1", error_queue)

        self.assertFalse(error_queue.empty())
        self.assertEqual(error_queue.get(), "deploy failed")


if __name__ == "__main__":
    unittest.main()
