#!/usr/bin/env python3

"""
Test suite for utils_network_chaos module

Usage:
    python -m coverage run -a -m unittest tests/test_utils_network_chaos.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch, call

from krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos import (
    get_build_tc_tree_commands,
    namespaced_tc_commands,
    get_egress_shaping_comand,
    get_clear_egress_shaping_commands,
    get_ingress_shaping_commands,
    get_clear_ingress_shaping_commands,
    node_qdisc_is_simple,
    common_set_limit_rules,
    common_delete_limit_rules,
    ROOT_HANDLE,
    CLASS_ID,
    NETEM_HANDLE,
)


class TestBuildTcTreeCommands(unittest.TestCase):

    def test_build_tc_tree_single_interface(self):
        """
        Test building tc tree commands for a single interface
        """
        devices = ["eth0"]
        result = get_build_tc_tree_commands(devices)

        self.assertEqual(len(result), 3)
        self.assertIn("tc qdisc add dev eth0 root handle 100: htb default 1", result)
        self.assertIn(
            "tc class add dev eth0 parent 100: classid 100:1 htb rate 1gbit", result
        )
        self.assertIn(
            "tc qdisc add dev eth0 parent 100:1 handle 101: netem delay 0ms loss 0%",
            result,
        )

    def test_build_tc_tree_multiple_interfaces(self):
        """
        Test building tc tree commands for multiple interfaces
        """
        devices = ["eth0", "eth1"]
        result = get_build_tc_tree_commands(devices)

        self.assertEqual(len(result), 6)
        # Verify commands for eth0
        self.assertIn("tc qdisc add dev eth0 root handle 100: htb default 1", result)
        # Verify commands for eth1
        self.assertIn("tc qdisc add dev eth1 root handle 100: htb default 1", result)

    def test_build_tc_tree_empty_list(self):
        """
        Test building tc tree commands with empty device list
        """
        devices = []
        result = get_build_tc_tree_commands(devices)

        self.assertEqual(len(result), 0)


class TestNamespacedTcCommands(unittest.TestCase):

    def test_namespaced_commands_single_pid(self):
        """
        Test wrapping commands with nsenter for single pid
        """
        pids = ["1234"]
        commands = ["tc qdisc add dev eth0 root handle 100: htb"]
        result = namespaced_tc_commands(pids, commands)

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0],
            "nsenter --target 1234 --net -- tc qdisc add dev eth0 root handle 100: htb",
        )

    def test_namespaced_commands_multiple_pids(self):
        """
        Test wrapping commands with nsenter for multiple pids
        """
        pids = ["1234", "5678"]
        commands = ["tc qdisc add dev eth0 root handle 100: htb"]
        result = namespaced_tc_commands(pids, commands)

        self.assertEqual(len(result), 2)
        self.assertIn(
            "nsenter --target 1234 --net -- tc qdisc add dev eth0 root handle 100: htb",
            result,
        )
        self.assertIn(
            "nsenter --target 5678 --net -- tc qdisc add dev eth0 root handle 100: htb",
            result,
        )

    def test_namespaced_commands_multiple_pids_and_commands(self):
        """
        Test wrapping multiple commands for multiple pids
        """
        pids = ["1234", "5678"]
        commands = ["tc qdisc add dev eth0 root", "tc class add dev eth0"]
        result = namespaced_tc_commands(pids, commands)

        self.assertEqual(len(result), 4)


class TestEgressShapingCommands(unittest.TestCase):

    def test_egress_shaping_with_all_params(self):
        """
        Test egress shaping commands with bandwidth, latency and loss
        """
        devices = ["eth0"]
        result = get_egress_shaping_comand(devices, "100", "50", "10")

        self.assertEqual(len(result), 2)
        self.assertIn(
            "tc class change dev eth0 parent 100: classid 100:1 htb rate 100mbit",
            result,
        )
        self.assertIn(
            "tc qdisc change dev eth0 parent 100:1 handle 101: netem delay 50ms loss 10%",
            result,
        )

    def test_egress_shaping_with_defaults(self):
        """
        Test egress shaping commands with None values defaults to 1gbit, 0ms, 0%
        """
        devices = ["eth0"]
        result = get_egress_shaping_comand(devices, None, None, None)

        self.assertEqual(len(result), 2)
        self.assertIn(
            "tc class change dev eth0 parent 100: classid 100:1 htb rate 1gbit", result
        )
        self.assertIn(
            "tc qdisc change dev eth0 parent 100:1 handle 101: netem delay 0ms loss 0%",
            result,
        )

    def test_egress_shaping_multiple_interfaces(self):
        """
        Test egress shaping for multiple interfaces
        """
        devices = ["eth0", "eth1"]
        result = get_egress_shaping_comand(devices, "100", "50", "10")

        self.assertEqual(len(result), 4)


class TestClearEgressShapingCommands(unittest.TestCase):

    def test_clear_egress_single_interface(self):
        """
        Test clear egress shaping for single interface
        """
        devices = ["eth0"]
        result = get_clear_egress_shaping_commands(devices)

        self.assertEqual(len(result), 1)
        self.assertIn("tc qdisc del dev eth0 root handle 100:", result)

    def test_clear_egress_multiple_interfaces(self):
        """
        Test clear egress shaping for multiple interfaces
        """
        devices = ["eth0", "eth1"]
        result = get_clear_egress_shaping_commands(devices)

        self.assertEqual(len(result), 2)
        self.assertIn("tc qdisc del dev eth0 root handle 100:", result)
        self.assertIn("tc qdisc del dev eth1 root handle 100:", result)


class TestIngressShapingCommands(unittest.TestCase):

    def test_ingress_shaping_with_all_params(self):
        """
        Test ingress shaping commands with bandwidth, latency and loss
        """
        devices = ["eth0"]
        result = get_ingress_shaping_commands(devices, "100", "50ms", "10")

        # Should have: modprobe, ip link add, ip link set, tc qdisc add ingress,
        # tc filter add, tc qdisc add root, tc class add, tc qdisc add netem
        self.assertGreater(len(result), 7)
        self.assertIn("modprobe ifb || true", result)
        self.assertIn("ip link add ifb0 type ifb || true", result)
        self.assertIn("ip link set ifb0 up || true", result)
        self.assertIn("tc qdisc add dev eth0 handle ffff: ingress || true", result)
        # Check that bandwidth, latency, loss are in commands
        self.assertTrue(any("100" in cmd for cmd in result))
        self.assertTrue(any("50ms" in cmd for cmd in result))
        self.assertTrue(any("10" in cmd for cmd in result))

    def test_ingress_shaping_with_defaults(self):
        """
        Test ingress shaping with None values uses defaults
        """
        devices = ["eth0"]
        result = get_ingress_shaping_commands(devices, None, None, None)

        self.assertGreater(len(result), 7)
        # Should use 1gbit, 0ms, 0% as defaults
        self.assertTrue(any("1gbit" in cmd for cmd in result))
        self.assertTrue(any("0ms" in cmd for cmd in result))
        self.assertTrue(any("0%" in cmd for cmd in result))

    def test_ingress_shaping_custom_ifb_device(self):
        """
        Test ingress shaping with custom ifb device name
        """
        devices = ["eth0"]
        result = get_ingress_shaping_commands(devices, "100", "50ms", "10", "ifb1")

        self.assertIn("ip link add ifb1 type ifb || true", result)
        self.assertIn("ip link set ifb1 up || true", result)


class TestClearIngressShapingCommands(unittest.TestCase):

    def test_clear_ingress_single_interface(self):
        """
        Test clear ingress shaping for single interface
        """
        devices = ["eth0"]
        result = get_clear_ingress_shaping_commands(devices)

        self.assertGreater(len(result), 3)
        self.assertIn("tc qdisc del dev eth0 ingress || true", result)
        self.assertIn("tc qdisc del dev ifb0 root handle 100: || true", result)
        self.assertIn("ip link set ifb0 down || true", result)
        self.assertIn("ip link del ifb0 || true", result)

    def test_clear_ingress_multiple_interfaces(self):
        """
        Test clear ingress shaping for multiple interfaces
        """
        devices = ["eth0", "eth1"]
        result = get_clear_ingress_shaping_commands(devices)

        self.assertIn("tc qdisc del dev eth0 ingress || true", result)
        self.assertIn("tc qdisc del dev eth1 ingress || true", result)

    def test_clear_ingress_custom_ifb_device(self):
        """
        Test clear ingress with custom ifb device
        """
        devices = ["eth0"]
        result = get_clear_ingress_shaping_commands(devices, "ifb1")

        self.assertIn("tc qdisc del dev ifb1 root handle 100: || true", result)
        self.assertIn("ip link set ifb1 down || true", result)
        self.assertIn("ip link del ifb1 || true", result)


class TestNodeQdiscIsSimple(unittest.TestCase):

    def test_node_qdisc_is_simple_with_simple_qdisc(self):
        """
        Test node_qdisc_is_simple returns True for simple qdisc (e.g., pfifo_fast)
        """
        mock_kubecli = MagicMock()
        mock_kubecli.exec_cmd_in_pod.return_value = (
            "qdisc pfifo_fast 0: root refcnt 2 bands 3 priomap  1 2 2 2"
        )

        result = node_qdisc_is_simple(mock_kubecli, "test-pod", "default", "eth0")

        self.assertTrue(result)
        mock_kubecli.exec_cmd_in_pod.assert_called_once_with(
            ["tc qdisc show dev eth0"], "test-pod", "default"
        )

    def test_node_qdisc_is_simple_with_htb(self):
        """
        Test node_qdisc_is_simple returns False for htb qdisc
        """
        mock_kubecli = MagicMock()
        mock_kubecli.exec_cmd_in_pod.return_value = (
            "qdisc htb 100: root refcnt 2 r2q 10 default 1"
        )

        result = node_qdisc_is_simple(mock_kubecli, "test-pod", "default", "eth0")

        self.assertFalse(result)

    def test_node_qdisc_is_simple_with_netem(self):
        """
        Test node_qdisc_is_simple returns False for netem qdisc
        """
        mock_kubecli = MagicMock()
        mock_kubecli.exec_cmd_in_pod.return_value = (
            "qdisc netem 101: root refcnt 2 limit 1000 delay 100ms"
        )

        result = node_qdisc_is_simple(mock_kubecli, "test-pod", "default", "eth0")

        self.assertFalse(result)

    def test_node_qdisc_is_simple_with_clsact(self):
        """
        Test node_qdisc_is_simple returns False for clsact qdisc
        """
        mock_kubecli = MagicMock()
        mock_kubecli.exec_cmd_in_pod.return_value = "qdisc clsact ffff: parent ffff:fff1"

        result = node_qdisc_is_simple(mock_kubecli, "test-pod", "default", "eth0")

        self.assertFalse(result)

    def test_node_qdisc_is_simple_with_multiple_lines(self):
        """
        Test node_qdisc_is_simple returns False when multiple qdisc lines exist
        """
        mock_kubecli = MagicMock()
        mock_kubecli.exec_cmd_in_pod.return_value = (
            "qdisc pfifo_fast 0: root\nqdisc htb 100: dev eth0"
        )

        result = node_qdisc_is_simple(mock_kubecli, "test-pod", "default", "eth0")

        self.assertFalse(result)

    def test_node_qdisc_is_simple_case_insensitive(self):
        """
        Test node_qdisc_is_simple check is case insensitive
        """
        mock_kubecli = MagicMock()
        mock_kubecli.exec_cmd_in_pod.return_value = "qdisc HTB 100: root"

        result = node_qdisc_is_simple(mock_kubecli, "test-pod", "default", "eth0")

        self.assertFalse(result)


class TestCommonSetLimitRules(unittest.TestCase):

    def setUp(self):
        """
        Set up mock kubecli for all tests
        """
        self.mock_kubecli = MagicMock()
        self.mock_kubecli.exec_cmd_in_pod.return_value = ""

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos.log_info")
    def test_set_egress_only(self, mock_log_info):
        """
        Test setting egress rules only
        """
        common_set_limit_rules(
            egress=True,
            ingress=False,
            interfaces=["eth0"],
            bandwidth="100",
            latency="50",
            loss="10",
            parallel=False,
            target="test-target",
            kubecli=self.mock_kubecli,
            network_chaos_pod_name="chaos-pod",
            namespace="default",
            pids=None,
        )

        # Should call exec_cmd_in_pod for egress rules (3 build + 2 shaping)
        self.assertGreaterEqual(self.mock_kubecli.exec_cmd_in_pod.call_count, 5)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos.log_info")
    def test_set_ingress_only(self, mock_log_info):
        """
        Test setting ingress rules only
        """
        common_set_limit_rules(
            egress=False,
            ingress=True,
            interfaces=["eth0"],
            bandwidth="100",
            latency="50",
            loss="10",
            parallel=False,
            target="test-target",
            kubecli=self.mock_kubecli,
            network_chaos_pod_name="chaos-pod",
            namespace="default",
            pids=None,
        )

        # Should call exec_cmd_in_pod for ingress rules
        self.assertGreater(self.mock_kubecli.exec_cmd_in_pod.call_count, 0)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos.log_info")
    def test_set_both_egress_and_ingress(self, mock_log_info):
        """
        Test setting both egress and ingress rules
        """
        common_set_limit_rules(
            egress=True,
            ingress=True,
            interfaces=["eth0"],
            bandwidth="100",
            latency="50",
            loss="10",
            parallel=False,
            target="test-target",
            kubecli=self.mock_kubecli,
            network_chaos_pod_name="chaos-pod",
            namespace="default",
            pids=None,
        )

        # Should call exec_cmd_in_pod for both egress and ingress
        self.assertGreater(self.mock_kubecli.exec_cmd_in_pod.call_count, 10)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos.log_info")
    def test_set_with_pids(self, mock_log_info):
        """
        Test setting rules with pids (namespace mode)
        """
        common_set_limit_rules(
            egress=True,
            ingress=False,
            interfaces=["eth0"],
            bandwidth="100",
            latency="50",
            loss="10",
            parallel=False,
            target="test-target",
            kubecli=self.mock_kubecli,
            network_chaos_pod_name="chaos-pod",
            namespace="default",
            pids=["1234"],
        )

        # Verify that commands include nsenter
        calls = self.mock_kubecli.exec_cmd_in_pod.call_args_list
        self.assertTrue(
            any("nsenter" in str(call) for call in calls),
            "Expected nsenter commands when pids are provided",
        )

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos.log_error")
    def test_set_with_command_failure(self, mock_log_error):
        """
        Test handling of command failures
        """
        # Simulate all commands failing
        self.mock_kubecli.exec_cmd_in_pod.return_value = "error"

        common_set_limit_rules(
            egress=True,
            ingress=False,
            interfaces=["eth0"],
            bandwidth="100",
            latency="50",
            loss="10",
            parallel=False,
            target="test-target",
            kubecli=self.mock_kubecli,
            network_chaos_pod_name="chaos-pod",
            namespace="default",
            pids=None,
        )

        # Should log error when all commands fail
        mock_log_error.assert_called()


class TestCommonDeleteLimitRules(unittest.TestCase):

    def setUp(self):
        """
        Set up mock kubecli for all tests
        """
        self.mock_kubecli = MagicMock()
        self.mock_kubecli.exec_cmd_in_pod.return_value = ""

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos.log_info")
    def test_delete_egress_only(self, mock_log_info):
        """
        Test deleting egress rules only
        """
        common_delete_limit_rules(
            egress=True,
            ingress=False,
            interfaces=["eth0"],
            network_chaos_pod_name="chaos-pod",
            network_chaos_namespace="default",
            kubecli=self.mock_kubecli,
            pids=None,
            parallel=False,
            target="test-target",
        )

        # Should call exec_cmd_in_pod for egress cleanup
        self.assertGreater(self.mock_kubecli.exec_cmd_in_pod.call_count, 0)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos.log_info")
    def test_delete_ingress_only(self, mock_log_info):
        """
        Test deleting ingress rules only
        """
        common_delete_limit_rules(
            egress=False,
            ingress=True,
            interfaces=["eth0"],
            network_chaos_pod_name="chaos-pod",
            network_chaos_namespace="default",
            kubecli=self.mock_kubecli,
            pids=None,
            parallel=False,
            target="test-target",
        )

        # Should call exec_cmd_in_pod for ingress cleanup
        self.assertGreater(self.mock_kubecli.exec_cmd_in_pod.call_count, 0)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos.log_info")
    def test_delete_both_egress_and_ingress(self, mock_log_info):
        """
        Test deleting both egress and ingress rules
        """
        common_delete_limit_rules(
            egress=True,
            ingress=True,
            interfaces=["eth0"],
            network_chaos_pod_name="chaos-pod",
            network_chaos_namespace="default",
            kubecli=self.mock_kubecli,
            pids=None,
            parallel=False,
            target="test-target",
        )

        # Should call exec_cmd_in_pod for both egress and ingress
        self.assertGreater(self.mock_kubecli.exec_cmd_in_pod.call_count, 3)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos.log_info")
    def test_delete_with_pids(self, mock_log_info):
        """
        Test deleting rules with pids (namespace mode)
        """
        common_delete_limit_rules(
            egress=True,
            ingress=False,
            interfaces=["eth0"],
            network_chaos_pod_name="chaos-pod",
            network_chaos_namespace="default",
            kubecli=self.mock_kubecli,
            pids=["1234"],
            parallel=False,
            target="test-target",
        )

        # Verify that commands include nsenter
        calls = self.mock_kubecli.exec_cmd_in_pod.call_args_list
        self.assertTrue(
            any("nsenter" in str(call) for call in calls),
            "Expected nsenter commands when pids are provided",
        )

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.utils_network_chaos.log_error")
    def test_delete_with_command_failure(self, mock_log_error):
        """
        Test handling of command failures during deletion
        """
        # Simulate all commands failing
        self.mock_kubecli.exec_cmd_in_pod.return_value = "error"

        common_delete_limit_rules(
            egress=True,
            ingress=False,
            interfaces=["eth0"],
            network_chaos_pod_name="chaos-pod",
            network_chaos_namespace="default",
            kubecli=self.mock_kubecli,
            pids=None,
            parallel=False,
            target="test-target",
        )

        # Should log error when all commands fail
        mock_log_error.assert_called()


if __name__ == "__main__":
    unittest.main()