#!/usr/bin/env python3

"""
Test suite for PodNetworkFilterModule rollback / exception safety.

Usage:
    python -m coverage run -a -m unittest tests/test_pod_network_filter.py -v

Assisted By: Claude Code
"""

import unittest
import queue
from unittest.mock import MagicMock, patch

from krkn.scenario_plugins.network_chaos_ng.modules.pod_network_filter import (
    PodNetworkFilterModule,
)
from krkn.scenario_plugins.network_chaos_ng.models import NetworkFilterConfig

MODULE = "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_filter"


class TestPodNetworkFilterModuleRollback(unittest.TestCase):
    """
    Rollback / exception-safety tests for PodNetworkFilterModule.

    Same destructive-cleanup contract as the node filter, but cleanup is
    namespaced (nsenter into the target pod netns via pids) and there is an
    additional no-interface early-return path that previously leaked the pod.
    """

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes

        self.config = NetworkFilterConfig(
            id="pod_network_filter",
            image="test-image",
            wait_duration=1,
            test_duration=30,
            label_selector="",
            service_account="",
            taints=[],
            namespace="default",
            instance_count=1,
            target="test-pod",
            execution="serial",
            interfaces=["eth0"],
            ingress=True,
            egress=True,
            ports=[80],
            protocols=["tcp"],
        )

        self.module = PodNetworkFilterModule(self.config, self.mock_kubecli)

        # Default happy-path resolution for the k8s client calls made by run().
        mock_pod_info = MagicMock()
        mock_pod_info.nodeName = "worker-1"
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info
        self.mock_kubernetes.get_container_ids.return_value = ["container-123"]
        self.mock_kubernetes.get_pod_pids.return_value = ["1234"]

    # ----- _rollback() unit behaviour -----------------------------------

    def test_rollback_cleans_rules_when_applied(self):
        """rules_applied=True -> namespaced iptables cleanup runs (with pids), then pod deleted."""
        with patch(f"{MODULE}.clean_network_rules_namespaced") as mock_clean:
            self.module._rollback(
                "chaos-pod",
                ["in-rule"],
                ["out-rule"],
                pids=["1234"],
                rules_applied=True,
            )
        mock_clean.assert_called_once()
        args = mock_clean.call_args[0]
        self.assertEqual(args[1], ["in-rule"])  # input_rules
        self.assertEqual(args[2], ["out-rule"])  # output_rules
        self.assertEqual(args[5], ["1234"])  # pids
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "default")

    def test_rollback_skips_cleanup_when_not_applied(self):
        """rules_applied=False -> NO iptables cleanup, only pod deletion."""
        with patch(f"{MODULE}.clean_network_rules_namespaced") as mock_clean:
            self.module._rollback(
                "chaos-pod",
                ["in-rule"],
                ["out-rule"],
                pids=["1234"],
                rules_applied=False,
            )
        mock_clean.assert_not_called()
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "default")

    # ----- run() happy path ---------------------------------------------

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_namespaced_rules")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_success_cleans_and_deletes_pod(
        self, mock_log, mock_sleep, mock_setup, mock_generate, mock_apply, mock_clean
    ):
        """Successful run applies rules, then cleans them (with pids) and deletes the pod."""
        mock_setup.return_value = (["container-123"], ["eth0"])
        mock_generate.return_value = (["in-rule"], ["out-rule"])

        self.module.run("test-pod")

        mock_apply.assert_called_once()
        mock_sleep.assert_called_once_with(30)
        mock_clean.assert_called_once()
        clean_args = mock_clean.call_args[0]
        self.assertEqual(clean_args[1], ["in-rule"])
        self.assertEqual(clean_args[2], ["out-rule"])
        self.assertEqual(clean_args[5], ["1234"])  # pids threaded to cleanup
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    # ----- run() early return (no interface) ----------------------------

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.log_error")
    @patch(f"{MODULE}.log_info")
    def test_run_no_interface_early_return_deletes_pod(
        self, mock_log, mock_log_error, mock_setup, mock_clean
    ):
        """No interface detected: pod is now cleaned up on the early return (was leaked)."""
        self.config.interfaces = []
        mock_setup.return_value = (["container-123"], [])

        self.module.run("test-pod")

        mock_log_error.assert_called()
        mock_clean.assert_not_called()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.log_error")
    @patch(f"{MODULE}.log_info")
    def test_run_no_interface_skip_stays_graceful_when_pod_deletion_fails_serial(
        self, mock_log, mock_log_error, mock_setup, mock_clean
    ):
        """
        Serial parity with main: the no-interface skip must return normally even
        if pod deletion fails. A cleanup failure must not become a scenario error.
        """
        self.config.interfaces = []
        mock_setup.return_value = (["container-123"], [])
        self.mock_kubernetes.delete_pod.side_effect = Exception("delete failed on skip path")

        # Must not raise.
        result = self.module.run("test-pod")

        self.assertIsNone(result)
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)
        mock_clean.assert_not_called()

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.log_error")
    @patch(f"{MODULE}.log_info")
    def test_run_no_interface_skip_stays_graceful_when_pod_deletion_fails_parallel(
        self, mock_log, mock_log_error, mock_setup, mock_clean
    ):
        """
        Parallel parity with main: the no-interface skip must leave error_queue
        empty even if pod deletion fails during cleanup.
        """
        self.config.interfaces = []
        mock_setup.return_value = (["container-123"], [])
        self.mock_kubernetes.delete_pod.side_effect = Exception("delete failed on skip path")

        error_queue = queue.Queue()
        self.module.run("test-pod", error_queue)

        self.assertTrue(error_queue.empty())
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)
        mock_clean.assert_not_called()

    # ----- run() exception paths ----------------------------------------

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.generate_namespaced_rules")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.log_info")
    def test_run_exception_before_generate_deletes_pod_no_cleanup(
        self, mock_log, mock_setup, mock_generate, mock_clean
    ):
        """Failure before rules are generated (no pids): pod deleted, no iptables cleanup."""
        mock_setup.return_value = (["container-123"], ["eth0"])
        self.mock_kubernetes.get_pod_pids.return_value = []  # raises before generate

        with self.assertRaises(Exception):
            self.module.run("test-pod")

        mock_generate.assert_not_called()
        mock_clean.assert_not_called()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_namespaced_rules")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.log_info")
    def test_run_exception_after_generate_before_apply_does_not_clean(
        self, mock_log, mock_setup, mock_generate, mock_apply, mock_clean
    ):
        """
        PRIMARY REGRESSION GUARD.

        Namespaced rules are generated but apply fails. Because rules were never
        applied, _rollback must NOT call clean_network_rules_namespaced —
        otherwise it would delete unrelated iptables rules inside the target
        pod's network namespace. The pod is still deleted.
        """
        mock_setup.return_value = (["container-123"], ["eth0"])
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        mock_apply.side_effect = RuntimeError("apply failed")

        with self.assertRaises(RuntimeError):
            self.module.run("test-pod")

        mock_clean.assert_not_called()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_namespaced_rules")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_exception_after_apply_cleans_and_deletes(
        self, mock_log, mock_sleep, mock_setup, mock_generate, mock_apply, mock_clean
    ):
        """Interrupted after rules were applied: namespaced cleanup and pod deletion both run."""
        mock_setup.return_value = (["container-123"], ["eth0"])
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        mock_sleep.side_effect = RuntimeError("interrupted")

        with self.assertRaises(RuntimeError):
            self.module.run("test-pod")

        mock_clean.assert_called_once()
        clean_args = mock_clean.call_args[0]
        self.assertEqual(clean_args[5], ["1234"])  # pids
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    # ----- run() parallel / error_queue path ----------------------------

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_namespaced_rules")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_error_queue_after_apply_cleans_and_reports(
        self, mock_log, mock_sleep, mock_setup, mock_generate, mock_apply, mock_clean
    ):
        """Parallel mode: post-apply failure still rolls back and reports via the queue."""
        mock_setup.return_value = (["container-123"], ["eth0"])
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        mock_sleep.side_effect = RuntimeError("interrupted")

        error_queue = queue.Queue()
        self.module.run("test-pod", error_queue)

        self.assertFalse(error_queue.empty())
        self.assertEqual(error_queue.get(), "interrupted")
        mock_clean.assert_called_once()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_namespaced_rules")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.log_info")
    def test_run_error_queue_before_apply_reports_without_cleanup(
        self, mock_log, mock_setup, mock_generate, mock_apply, mock_clean
    ):
        """Parallel mode: pre-apply failure reports via the queue and does not clean firewall rules."""
        mock_setup.return_value = (["container-123"], ["eth0"])
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        mock_apply.side_effect = Exception("apply failed")

        error_queue = queue.Queue()
        self.module.run("test-pod", error_queue)

        self.assertFalse(error_queue.empty())
        self.assertEqual(error_queue.get(), "apply failed")
        mock_clean.assert_not_called()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_namespaced_rules")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_cleanup_runs_once_when_pod_deletion_fails(
        self, mock_log, mock_sleep, mock_setup, mock_generate, mock_apply, mock_clean
    ):
        """
        If pod deletion fails after a successful cleanup, namespaced cleanup must
        NOT run a second time (it would delete unrelated rules inside the pod
        netns). Rollback runs in `finally`, guaranteeing exactly one cleanup pass.
        """
        mock_setup.return_value = (["container-123"], ["eth0"])
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        self.mock_kubernetes.delete_pod.side_effect = Exception("api error")

        with self.assertRaises(Exception):
            self.module.run("test-pod")

        mock_clean.assert_called_once()

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_namespaced_rules")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_parallel_cleanup_failure_reaches_error_queue(
        self, mock_log, mock_sleep, mock_setup, mock_generate, mock_apply, mock_clean
    ):
        """
        Regression: in parallel mode a cleanup-time failure must be reported via
        error_queue (matching main), not escape as a raised exception.
        """
        mock_setup.return_value = (["container-123"], ["eth0"])
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        self.mock_kubernetes.delete_pod.side_effect = Exception("api 500 during delete")

        error_queue = queue.Queue()
        # Must not raise.
        self.module.run("test-pod", error_queue)

        self.assertFalse(error_queue.empty())
        self.assertEqual(error_queue.get(), "api 500 during delete")
        mock_clean.assert_called_once()

    @patch(f"{MODULE}.clean_network_rules_namespaced")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_namespaced_rules")
    @patch(f"{MODULE}.setup_network_chaos_ng_scenario")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_original_error_preserved_when_cleanup_also_fails(
        self, mock_log, mock_sleep, mock_setup, mock_generate, mock_apply, mock_clean
    ):
        """
        Regression: if rollback cleanup ALSO fails, the original scenario error
        must still be reported (not the cleanup error, and not lost).
        """
        mock_setup.return_value = (["container-123"], ["eth0"])
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        mock_sleep.side_effect = RuntimeError("scenario boom")
        mock_clean.side_effect = Exception("cleanup failed")

        error_queue = queue.Queue()
        self.module.run("test-pod", error_queue)

        self.assertEqual(error_queue.get(), "scenario boom")


if __name__ == "__main__":
    unittest.main()
