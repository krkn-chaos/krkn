#!/usr/bin/env python3

"""
Test suite for PodNetworkChaosModule class

Usage:
    python -m coverage run -a -m unittest tests/test_pod_network_chaos.py -v

Assisted By: Claude Code
"""

import unittest
import queue
from unittest.mock import MagicMock, patch, call
from dataclasses import dataclass

from krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos import (
    PodNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosConfig,
    NetworkChaosScenarioType,
)


class TestPodNetworkChaosModule(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for PodNetworkChaosModule
        """
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes

        self.config = NetworkChaosConfig(
            id="test-pod-network-chaos",
            image="test-image",
            wait_duration=1,
            test_duration=30,
            label_selector="",
            service_account="",
            taints=[],
            namespace="default",
            instance_count=1,
            target="test-pod",
            execution="parallel",
            interfaces=["eth0"],
            ingress=True,
            egress=True,
            latency="100ms",
            loss="10",
            bandwidth="100mbit",
        )

        self.module = PodNetworkChaosModule(self.config, self.mock_kubecli)

    def test_initialization(self):
        """
        Test PodNetworkChaosModule initialization
        """
        self.assertEqual(self.module.config, self.config)
        self.assertEqual(self.module.kubecli, self.mock_kubecli)
        self.assertEqual(self.module.base_network_config, self.config)

    def test_get_config(self):
        """
        Test get_config returns correct scenario type and config
        """
        scenario_type, config = self.module.get_config()

        self.assertEqual(scenario_type, NetworkChaosScenarioType.Pod)
        self.assertEqual(config, self.config)

    def test_get_targets_with_target_name(self):
        """
        Test get_targets with specific pod target name
        """
        self.config.label_selector = ""
        self.config.target = "test-pod"
        self.mock_kubernetes.check_if_pod_exists.return_value = True

        targets = self.module.get_targets()

        self.assertEqual(targets, ["test-pod"])
        self.mock_kubernetes.check_if_pod_exists.assert_called_once_with(
            "test-pod", "default"
        )

    def test_get_targets_with_label_selector(self):
        """
        Test get_targets with label selector
        """
        self.config.label_selector = "app=nginx"
        self.mock_kubernetes.list_pods.return_value = ["pod1", "pod2", "pod3"]

        targets = self.module.get_targets()

        self.assertEqual(targets, ["pod1", "pod2", "pod3"])
        self.mock_kubernetes.list_pods.assert_called_once_with(
            "default", "app=nginx"
        )

    def test_get_targets_pod_not_found(self):
        """
        Test get_targets raises exception when pod doesn't exist
        """
        self.config.label_selector = ""
        self.config.target = "non-existent-pod"
        self.mock_kubernetes.check_if_pod_exists.return_value = False

        with self.assertRaises(Exception) as context:
            self.module.get_targets()

        self.assertIn("not found", str(context.exception))

    def test_get_targets_no_namespace(self):
        """
        Test get_targets raises exception when namespace not specified
        """
        self.config.namespace = None

        with self.assertRaises(Exception) as context:
            self.module.get_targets()

        self.assertIn("namespace not specified", str(context.exception))

    def test_get_targets_no_target_or_selector(self):
        """
        Test get_targets raises exception when neither target nor selector specified
        """
        self.config.label_selector = ""
        self.config.target = ""

        with self.assertRaises(Exception) as context:
            self.module.get_targets()

        self.assertIn("neither", str(context.exception))

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.time.sleep")
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_success(
        self,
        mock_log_info,
        mock_setup,
        mock_set_rules,
        mock_delete_rules,
        mock_sleep,
    ):
        """
        Test successful run of pod network chaos
        """
        # Mock pod info
        mock_pod_info = MagicMock()
        mock_pod_info.nodeName = "worker-1"
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info

        # Mock setup returns container_ids and interfaces
        mock_setup.return_value = (["container-123"], ["eth0"])

        # Mock get_pod_pids
        self.mock_kubernetes.get_pod_pids.return_value = ["1234"]

        self.module.run("test-pod")

        # Verify pod info was retrieved
        self.mock_kubernetes.get_pod_info.assert_called_once_with(
            "test-pod", "default"
        )

        # Verify setup was called
        mock_setup.assert_called_once()

        # Verify pids were resolved
        self.mock_kubernetes.get_pod_pids.assert_called_once()

        # Verify tc rules were set
        mock_set_rules.assert_called_once()

        # Verify sleep for test duration
        mock_sleep.assert_called_once_with(30)

        # Verify tc rules were deleted
        mock_delete_rules.assert_called_once()

        # Verify cleanup pod was deleted
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_pod_info_not_found(self, mock_log_info, mock_setup):
        """
        Test run raises exception when pod info cannot be retrieved
        """
        self.mock_kubernetes.get_pod_info.return_value = None

        with self.assertRaises(Exception) as context:
            self.module.run("test-pod")

        self.assertIn("impossible to retrieve infos", str(context.exception))

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_error")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_no_interfaces_detected(
        self, mock_log_info, mock_log_error, mock_setup
    ):
        """
        Test run handles case when no network interfaces detected
        """
        # Mock pod info
        mock_pod_info = MagicMock()
        mock_pod_info.nodeName = "worker-1"
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info

        # Mock setup returns empty interfaces
        mock_setup.return_value = (["container-123"], [])

        # Set config to auto-detect interfaces
        self.config.interfaces = []

        self.module.run("test-pod")

        # Verify error was logged
        mock_log_error.assert_called()
        self.assertIn("no network interface", str(mock_log_error.call_args))

        # The chaos pod is now cleaned up on the no-interface early return
        # (previously it was leaked).
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_no_container_id(self, mock_log_info, mock_setup):
        """
        Test run raises exception when container id cannot be resolved
        """
        # Mock pod info
        mock_pod_info = MagicMock()
        mock_pod_info.nodeName = "worker-1"
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info

        # Mock setup returns empty container_ids
        mock_setup.return_value = ([], ["eth0"])

        with self.assertRaises(Exception) as context:
            self.module.run("test-pod")

        self.assertIn("impossible to resolve container id", str(context.exception))

        # The chaos pod is now cleaned up before the exception propagates.
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_no_pids(self, mock_log_info, mock_setup):
        """
        Test run raises exception when pids cannot be resolved
        """
        # Mock pod info
        mock_pod_info = MagicMock()
        mock_pod_info.nodeName = "worker-1"
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info

        # Mock setup
        mock_setup.return_value = (["container-123"], ["eth0"])

        # Mock get_pod_pids returns empty
        self.mock_kubernetes.get_pod_pids.return_value = []

        with self.assertRaises(Exception) as context:
            self.module.run("test-pod")

        self.assertIn("impossible to resolve pid", str(context.exception))

        # The chaos pod is now cleaned up before the exception propagates.
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.time.sleep")
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_uses_configured_interfaces(
        self,
        mock_log_info,
        mock_setup,
        mock_set_rules,
        mock_delete_rules,
        mock_sleep,
    ):
        """
        Test run uses configured interfaces instead of detected ones
        """
        # Mock pod info
        mock_pod_info = MagicMock()
        mock_pod_info.nodeName = "worker-1"
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info

        # Mock setup returns different interfaces
        mock_setup.return_value = (["container-123"], ["eth0", "eth1"])

        # Mock get_pod_pids
        self.mock_kubernetes.get_pod_pids.return_value = ["1234"]

        # Set specific interfaces in config
        self.config.interfaces = ["eth2"]

        self.module.run("test-pod")

        # Verify set_rules was called with configured interfaces, not detected ones
        call_args = mock_set_rules.call_args
        # interfaces is the 3rd positional argument (index 2)
        self.assertEqual(call_args[0][2], ["eth2"])

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_with_error_queue(self, mock_log_info, mock_setup):
        """
        Test run with error_queue for parallel execution
        """
        # Mock pod info
        mock_pod_info = MagicMock()
        mock_pod_info.nodeName = "worker-1"
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info

        # Mock setup to raise exception
        mock_setup.side_effect = Exception("Test error")

        error_queue = queue.Queue()
        self.module.run("test-pod", error_queue)

        # Verify error was put in queue instead of raising
        self.assertFalse(error_queue.empty())
        error = error_queue.get()
        self.assertEqual(error, "Test error")

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.time.sleep")
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_passes_correct_pids(
        self,
        mock_log_info,
        mock_setup,
        mock_set_rules,
        mock_delete_rules,
        mock_sleep,
    ):
        """
        Test run passes pids correctly to set and delete rules
        """
        # Mock pod info
        mock_pod_info = MagicMock()
        mock_pod_info.nodeName = "worker-1"
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info

        # Mock setup
        mock_setup.return_value = (["container-123"], ["eth0"])

        # Mock get_pod_pids
        test_pids = ["1234", "5678"]
        self.mock_kubernetes.get_pod_pids.return_value = test_pids

        self.module.run("test-pod")

        # Verify set_rules was called with pids
        set_call_args = mock_set_rules.call_args
        # pids is the last positional argument
        self.assertEqual(set_call_args[0][-1], test_pids)

        # Verify delete_rules was called with pids
        delete_call_args = mock_delete_rules.call_args
        # pids is argument at index 6
        self.assertEqual(delete_call_args[0][6], test_pids)

    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.time.sleep")
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_ingress_egress_flags(
        self,
        mock_log_info,
        mock_setup,
        mock_set_rules,
        mock_delete_rules,
        mock_sleep,
    ):
        """
        Test run passes ingress and egress flags correctly
        """
        # Mock pod info
        mock_pod_info = MagicMock()
        mock_pod_info.nodeName = "worker-1"
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info

        # Mock setup
        mock_setup.return_value = (["container-123"], ["eth0"])

        # Mock get_pod_pids
        self.mock_kubernetes.get_pod_pids.return_value = ["1234"]

        # Set specific ingress/egress config
        self.config.ingress = False
        self.config.egress = True

        self.module.run("test-pod")

        # Verify set_rules was called with correct egress/ingress flags
        set_call_args = mock_set_rules.call_args
        # egress is 1st arg (index 0), ingress is 2nd arg (index 1)
        self.assertEqual(set_call_args[0][0], True)  # egress
        self.assertEqual(set_call_args[0][1], False)  # ingress

        # Verify delete_rules was called with correct flags
        delete_call_args = mock_delete_rules.call_args
        self.assertEqual(delete_call_args[0][0], True)  # egress
        self.assertEqual(delete_call_args[0][1], False)  # ingress


class TestPodNetworkChaosModuleRollback(unittest.TestCase):
    """
    Rollback / exception-safety tests for PodNetworkChaosModule.

    Modeled on TestVmiNetworkChaosModuleRollback. Verifies that the chaos pod
    and any applied tc rules (in the target pod netns via nsenter/pids) are
    cleaned up on the exception path and on the no-interface early return, and
    that tc cleanup is gated on rules actually having been applied.
    """

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes

        self.config = NetworkChaosConfig(
            id="test-pod-network-chaos",
            image="test-image",
            wait_duration=1,
            test_duration=30,
            label_selector="",
            service_account="",
            taints=[],
            namespace="default",
            instance_count=1,
            target="test-pod",
            execution="parallel",
            interfaces=["eth0"],
            ingress=True,
            egress=True,
            latency="100ms",
            loss="10",
            bandwidth="100mbit",
        )

        self.module = PodNetworkChaosModule(self.config, self.mock_kubecli)

        self.mock_pod_info = MagicMock()
        self.mock_pod_info.nodeName = "worker-1"
        self.mock_kubernetes.get_pod_info.return_value = self.mock_pod_info

    def test_rollback_calls_delete_limit_rules_when_rules_applied(self):
        """When rules were applied, _rollback removes tc rules (with pids) then deletes the pod."""
        with patch(
            "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_delete_limit_rules"
        ) as mock_del:
            self.module._rollback(
                "chaos-pod", ["eth0"], pids=["1234"], rules_applied=True
            )
        mock_del.assert_called_once()
        del_args = mock_del.call_args[0]
        self.assertEqual(del_args[2], ["eth0"])  # interfaces
        self.assertEqual(del_args[6], ["1234"])  # pids
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "default")

    def test_rollback_skips_delete_limit_rules_when_not_applied(self):
        """When no rules were applied, _rollback deletes only the pod."""
        with patch(
            "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_delete_limit_rules"
        ) as mock_del:
            self.module._rollback(
                "chaos-pod", ["eth0"], pids=["1234"], rules_applied=False
            )
        mock_del.assert_not_called()
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "default")

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_rollback_deletes_pod_on_exception_before_tc(
        self, mock_log_info, mock_setup, mock_del
    ):
        """Exception before tc is applied (no pids): pod deleted, no tc cleanup."""
        mock_setup.return_value = (["container-123"], ["eth0"])
        self.mock_kubernetes.get_pod_pids.return_value = []  # raises before tc

        with self.assertRaises(Exception):
            self.module.run("test-pod")

        mock_del.assert_not_called()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_rollback_calls_delete_limit_rules_on_exception_after_tc(
        self, mock_log_info, mock_sleep, mock_setup, mock_set, mock_del
    ):
        """Interrupted after tc is applied: tc cleanup and pod deletion both run."""
        mock_setup.return_value = (["container-123"], ["eth0"])
        self.mock_kubernetes.get_pod_pids.return_value = ["1234"]
        mock_sleep.side_effect = RuntimeError("interrupted")

        with self.assertRaises(RuntimeError):
            self.module.run("test-pod")

        mock_del.assert_called_once()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_delete_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.common_set_limit_rules"
    )
    @patch(
        "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.setup_network_chaos_ng_scenario"
    )
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.time.sleep")
    @patch("krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos.log_info")
    def test_run_rollback_passes_correct_pids_on_exception(
        self, mock_log_info, mock_sleep, mock_setup, mock_set, mock_del
    ):
        """Rollback on the exception path targets the correct interfaces and pids."""
        mock_setup.return_value = (["container-123"], ["eth0"])
        self.mock_kubernetes.get_pod_pids.return_value = ["1234", "5678"]
        mock_sleep.side_effect = RuntimeError("interrupted")

        with self.assertRaises(RuntimeError):
            self.module.run("test-pod")

        del_args = mock_del.call_args[0]
        self.assertEqual(del_args[2], ["eth0"])  # interfaces
        self.assertEqual(del_args[6], ["1234", "5678"])  # pids


if __name__ == "__main__":
    unittest.main()