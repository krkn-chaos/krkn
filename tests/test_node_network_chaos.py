#!/usr/bin/env python3

"""
Test suite for NodeNetworkChaosModule class

Usage:
    python -m coverage run -a -m unittest tests/test_node_network_chaos.py -v

Assisted By: Claude Code
"""

import unittest
import queue
from unittest.mock import MagicMock, patch, call

from krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos import (
    NodeNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosConfig,
    NetworkChaosScenarioType,
)


class TestNodeNetworkChaosModule(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for NodeNetworkChaosModule
        """
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes

        self.config = NetworkChaosConfig(
            id="test-node-network-chaos",
            image="test-image",
            wait_duration=1,
            test_duration=30,
            label_selector="",
            service_account="",
            taints=[],
            namespace="default",
            instance_count=1,
            target="worker-1",
            execution="parallel",
            interfaces=["eth0"],
            ingress=True,
            egress=True,
            latency="100ms",
            loss="10",
            bandwidth="100mbit",
            force=False,
        )

        self.module = NodeNetworkChaosModule(self.config, self.mock_kubecli)

    def test_initialization(self):
        """
        Test NodeNetworkChaosModule initialization
        """
        self.assertEqual(self.module.config, self.config)
        self.assertEqual(self.module.kubecli, self.mock_kubecli)
        self.assertEqual(self.module.base_network_config, self.config)

    def test_get_config(self):
        """
        Test get_config returns correct scenario type and config
        """
        scenario_type, config = self.module.get_config()

        self.assertEqual(scenario_type, NetworkChaosScenarioType.Node)
        self.assertEqual(config, self.config)

    def test_get_targets_with_target_name(self):
        """
        Test get_targets with specific node target name
        """
        self.config.label_selector = ""
        self.config.target = "worker-1"
        self.mock_kubernetes.list_nodes.return_value = ["worker-1", "worker-2"]

        targets = self.module.get_targets()

        self.assertEqual(targets, ["worker-1"])

    def test_get_targets_with_label_selector(self):
        """
        Test get_targets with label selector
        """
        self.config.label_selector = "node-role.kubernetes.io/worker="
        self.mock_kubernetes.list_nodes.return_value = ["worker-1", "worker-2"]

        targets = self.module.get_targets()

        self.assertEqual(targets, ["worker-1", "worker-2"])
        self.mock_kubernetes.list_nodes.assert_called_once_with(
            "node-role.kubernetes.io/worker="
        )

    def test_get_targets_node_not_found(self):
        """
        Test get_targets raises exception when node doesn't exist
        """
        self.config.label_selector = ""
        self.config.target = "non-existent-node"
        self.mock_kubernetes.list_nodes.return_value = ["worker-1", "worker-2"]

        with self.assertRaises(Exception) as context:
            self.module.get_targets()

        self.assertIn("not found", str(context.exception))

    def test_get_targets_no_target_or_selector(self):
        """
        Test get_targets raises exception when neither target nor selector specified
        """
        self.config.label_selector = ""
        self.config.target = ""

        with self.assertRaises(Exception) as context:
            self.module.get_targets()

        self.assertIn("neither", str(context.exception))

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.node_qdisc_is_simple"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.time.sleep")
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_info")
    def test_run_success(
        self,
        mock_log_info,
        mock_setup,
        mock_set_rules,
        mock_delete_rules,
        mock_sleep,
        mock_qdisc_is_simple,
    ):
        """
        Test successful run of node network chaos
        """
        # Mock setup returns container_ids and interfaces
        mock_setup.return_value = (["container-123"], ["eth0"])

        # Mock qdisc check - simple qdisc
        mock_qdisc_is_simple.return_value = True

        self.module.run("worker-1")

        # Verify setup was called with node name
        mock_setup.assert_called_once()
        setup_args = mock_setup.call_args[0]
        # Node name should be passed as target and is_node=True (8th arg, index 7)
        self.assertEqual(setup_args[7], True)  # is_node flag

        # Verify qdisc was checked
        mock_qdisc_is_simple.assert_called_once()

        # Verify tc rules were set (with pids=None for node scenario)
        mock_set_rules.assert_called_once()
        set_call_args = mock_set_rules.call_args
        # pids should be None (last argument)
        self.assertIsNone(set_call_args[0][-1])

        # Verify sleep for test duration
        mock_sleep.assert_called_once_with(30)

        # Verify tc rules were deleted
        mock_delete_rules.assert_called_once()
        delete_call_args = mock_delete_rules.call_args
        # pids should be None (7th argument, index 6)
        self.assertIsNone(delete_call_args[0][6])

        # Verify cleanup pod was deleted
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.node_qdisc_is_simple"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_error")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_info")
    def test_run_no_interfaces_detected(
        self, mock_log_info, mock_log_error, mock_setup, mock_qdisc_is_simple
    ):
        """
        Test run handles case when no network interfaces detected
        """
        # Mock setup returns empty interfaces
        mock_setup.return_value = (["container-123"], [])

        # Set config to auto-detect interfaces
        self.config.interfaces = []

        self.module.run("worker-1")

        # Verify error was logged
        mock_log_error.assert_called()
        self.assertIn("no network interface", str(mock_log_error.call_args))

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.node_qdisc_is_simple"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_warning"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_info")
    def test_run_complex_qdisc_without_force(
        self, mock_log_info, mock_log_warning, mock_setup, mock_qdisc_is_simple
    ):
        """
        Test run skips chaos when complex qdisc exists and force=False
        """
        # Mock setup
        mock_setup.return_value = (["container-123"], ["eth0"])

        # Mock qdisc check - complex qdisc
        mock_qdisc_is_simple.return_value = False

        # force is False
        self.config.force = False

        self.module.run("worker-1")

        # Verify warning was logged
        mock_log_warning.assert_called()
        self.assertIn("already has tc rules", str(mock_log_warning.call_args))

        # Verify cleanup pod was still deleted
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.node_qdisc_is_simple"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.time.sleep")
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_warning"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_info")
    def test_run_complex_qdisc_with_force(
        self,
        mock_log_info,
        mock_log_warning,
        mock_setup,
        mock_set_rules,
        mock_delete_rules,
        mock_sleep,
        mock_qdisc_is_simple,
    ):
        """
        Test run proceeds with chaos when complex qdisc exists and force=True
        """
        # Mock setup
        mock_setup.return_value = (["container-123"], ["eth0"])

        # Mock qdisc check - complex qdisc
        mock_qdisc_is_simple.return_value = False

        # force is True
        self.config.force = True

        self.module.run("worker-1")

        # Verify warning was logged about forcing
        mock_log_warning.assert_called()
        self.assertIn("forcing", str(mock_log_warning.call_args))

        # Verify sleep for safety warning (10 seconds)
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        self.assertIn(10, sleep_calls)

        # Verify tc rules were set
        mock_set_rules.assert_called_once()

        # Verify tc rules were deleted
        mock_delete_rules.assert_called_once()

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.node_qdisc_is_simple"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.time.sleep")
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_info")
    def test_run_uses_configured_interfaces(
        self,
        mock_log_info,
        mock_setup,
        mock_set_rules,
        mock_delete_rules,
        mock_sleep,
        mock_qdisc_is_simple,
    ):
        """
        Test run uses configured interfaces instead of detected ones
        """
        # Mock setup returns different interfaces
        mock_setup.return_value = (["container-123"], ["eth0", "eth1"])

        # Mock qdisc check - simple qdisc
        mock_qdisc_is_simple.return_value = True

        # Set specific interfaces in config
        self.config.interfaces = ["eth2"]

        self.module.run("worker-1")

        # Verify set_rules was called with configured interfaces
        call_args = mock_set_rules.call_args
        # interfaces is the 3rd positional argument (index 2)
        self.assertEqual(call_args[0][2], ["eth2"])

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.node_qdisc_is_simple"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_info")
    def test_run_with_error_queue(
        self, mock_log_info, mock_setup, mock_qdisc_is_simple
    ):
        """
        Test run with error_queue for parallel execution
        """
        # Mock setup to raise exception
        mock_setup.side_effect = Exception("Test error")

        error_queue = queue.Queue()
        self.module.run("worker-1", error_queue)

        # Verify error was put in queue instead of raising
        self.assertFalse(error_queue.empty())
        error = error_queue.get()
        self.assertEqual(error, "Test error")

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.node_qdisc_is_simple"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.time.sleep")
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_info")
    def test_run_ingress_egress_flags(
        self,
        mock_log_info,
        mock_setup,
        mock_set_rules,
        mock_delete_rules,
        mock_sleep,
        mock_qdisc_is_simple,
    ):
        """
        Test run passes ingress and egress flags correctly
        """
        # Mock setup
        mock_setup.return_value = (["container-123"], ["eth0"])

        # Mock qdisc check
        mock_qdisc_is_simple.return_value = True

        # Set specific ingress/egress config
        self.config.ingress = False
        self.config.egress = True

        self.module.run("worker-1")

        # Verify set_rules was called with correct egress/ingress flags
        set_call_args = mock_set_rules.call_args
        # egress is 1st arg (index 0), ingress is 2nd arg (index 1)
        self.assertEqual(set_call_args[0][0], True)  # egress
        self.assertEqual(set_call_args[0][1], False)  # ingress

        # Verify delete_rules was called with correct flags
        delete_call_args = mock_delete_rules.call_args
        self.assertEqual(delete_call_args[0][0], True)  # egress
        self.assertEqual(delete_call_args[0][1], False)  # ingress

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.node_qdisc_is_simple"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_warning"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_info")
    def test_run_mixed_simple_and_complex_qdisc(
        self, mock_log_info, mock_log_warning, mock_setup, mock_qdisc_is_simple
    ):
        """
        Test run with multiple interfaces where some have complex qdisc
        """
        # Mock setup with multiple interfaces
        mock_setup.return_value = (["container-123"], ["eth0", "eth1"])

        # Set config to use detected interfaces
        self.config.interfaces = []
        self.config.force = False

        # Mock qdisc check - eth0 simple, eth1 complex
        mock_qdisc_is_simple.side_effect = [True, False]

        self.module.run("worker-1")

        # Verify warning about complex qdisc on eth1
        mock_log_warning.assert_called()
        warning_message = str(mock_log_warning.call_args)
        self.assertIn("already has tc rules", warning_message)

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.node_qdisc_is_simple"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.time.sleep")
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.node_network_chaos.log_info")
    def test_run_checks_qdisc_for_all_interfaces(
        self,
        mock_log_info,
        mock_setup,
        mock_set_rules,
        mock_delete_rules,
        mock_sleep,
        mock_qdisc_is_simple,
    ):
        """
        Test run checks qdisc for all interfaces
        """
        # Mock setup with multiple interfaces
        mock_setup.return_value = (["container-123"], ["eth0", "eth1", "eth2"])

        # Set config to use detected interfaces
        self.config.interfaces = []

        # All interfaces simple
        mock_qdisc_is_simple.return_value = True

        self.module.run("worker-1")

        # Verify qdisc was checked for all 3 interfaces
        self.assertEqual(mock_qdisc_is_simple.call_count, 3)


if __name__ == "__main__":
    unittest.main()