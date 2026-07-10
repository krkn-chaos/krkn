#!/usr/bin/env python3

"""
Test suite for NodeNetworkFilterModule rollback / exception safety.

Usage:
    python -m coverage run -a -m unittest tests/test_node_network_filter.py -v

Assisted By: Claude Code
"""

import unittest
import queue
from unittest.mock import MagicMock, patch

from krkn.scenario_plugins.network_chaos_ng.modules.node_network_filter import (
    NodeNetworkFilterModule,
)
from krkn.scenario_plugins.network_chaos_ng.models import NetworkFilterConfig

MODULE = "krkn.scenario_plugins.network_chaos_ng.modules.node_network_filter"


class TestNodeNetworkFilterModuleRollback(unittest.TestCase):
    """
    Rollback / exception-safety tests for NodeNetworkFilterModule.

    Unlike the tc-based chaos modules, iptables cleanup is destructive:
    clean_network_rules() blindly deletes the rule at INPUT/OUTPUT position 1
    once per rule. Cleanup must therefore run ONLY when rules were actually
    applied. These tests lock that contract, in particular the case where an
    exception occurs after the rule lists are generated but before they are
    applied.
    """

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes

        self.config = NetworkFilterConfig(
            id="node_network_filter",
            image="test-image",
            wait_duration=1,
            test_duration=30,
            label_selector="",
            service_account="",
            taints=[],
            namespace="default",
            instance_count=1,
            target="worker-1",
            execution="serial",
            interfaces=["eth0"],
            ingress=True,
            egress=True,
            ports=[80],
            protocols=["tcp"],
        )

        self.module = NodeNetworkFilterModule(self.config, self.mock_kubecli)

    # ----- _rollback() unit behaviour -----------------------------------

    def test_rollback_cleans_rules_when_applied(self):
        """rules_applied=True -> iptables cleanup runs, then pod is deleted."""
        with patch(f"{MODULE}.clean_network_rules") as mock_clean:
            self.module._rollback(
                "chaos-pod", ["in-rule"], ["out-rule"], rules_applied=True
            )
        mock_clean.assert_called_once()
        args = mock_clean.call_args[0]
        self.assertEqual(args[1], ["in-rule"])  # input_rules
        self.assertEqual(args[2], ["out-rule"])  # output_rules
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "default")

    def test_rollback_skips_cleanup_when_not_applied(self):
        """rules_applied=False -> NO iptables cleanup, only pod deletion."""
        with patch(f"{MODULE}.clean_network_rules") as mock_clean:
            self.module._rollback(
                "chaos-pod", ["in-rule"], ["out-rule"], rules_applied=False
            )
        mock_clean.assert_not_called()
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "default")

    # ----- run() happy path ---------------------------------------------

    @patch(f"{MODULE}.clean_network_rules")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_rules")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_success_cleans_and_deletes_pod(
        self, mock_log, mock_sleep, mock_deploy, mock_generate, mock_apply, mock_clean
    ):
        """Successful run applies rules, then cleans them and deletes the pod."""
        mock_generate.return_value = (["in-rule"], ["out-rule"])

        self.module.run("worker-1")

        mock_apply.assert_called_once()
        mock_sleep.assert_called_once_with(30)
        mock_clean.assert_called_once()
        # cleanup targets exactly the generated rules
        clean_args = mock_clean.call_args[0]
        self.assertEqual(clean_args[1], ["in-rule"])
        self.assertEqual(clean_args[2], ["out-rule"])
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    # ----- run() exception paths ----------------------------------------

    @patch(f"{MODULE}.clean_network_rules")
    @patch(f"{MODULE}.generate_rules")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_exception_before_generate_deletes_pod_no_cleanup(
        self, mock_log, mock_deploy, mock_generate, mock_clean
    ):
        """Failure before any rules are generated: pod deleted, no iptables cleanup."""
        mock_deploy.side_effect = RuntimeError("deploy failed")

        with self.assertRaises(RuntimeError):
            self.module.run("worker-1")

        mock_generate.assert_not_called()
        mock_clean.assert_not_called()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(f"{MODULE}.clean_network_rules")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_rules")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_exception_after_generate_before_apply_does_not_clean(
        self, mock_log, mock_deploy, mock_generate, mock_apply, mock_clean
    ):
        """
        PRIMARY REGRESSION GUARD.

        Rules are generated but apply fails. Because rules were never applied,
        _rollback must NOT call clean_network_rules — otherwise it would delete
        unrelated pre-existing iptables rules from the node. The pod is still
        deleted.
        """
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        mock_apply.side_effect = RuntimeError("apply failed")

        with self.assertRaises(RuntimeError):
            self.module.run("worker-1")

        mock_clean.assert_not_called()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(f"{MODULE}.clean_network_rules")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_rules")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_exception_after_apply_cleans_and_deletes(
        self, mock_log, mock_sleep, mock_deploy, mock_generate, mock_apply, mock_clean
    ):
        """Interrupted after rules were applied: iptables cleanup and pod deletion both run."""
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        mock_sleep.side_effect = RuntimeError("interrupted")

        with self.assertRaises(RuntimeError):
            self.module.run("worker-1")

        mock_clean.assert_called_once()
        clean_args = mock_clean.call_args[0]
        self.assertEqual(clean_args[1], ["in-rule"])
        self.assertEqual(clean_args[2], ["out-rule"])
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    # ----- run() parallel / error_queue path ----------------------------

    @patch(f"{MODULE}.clean_network_rules")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_rules")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_error_queue_after_apply_cleans_and_reports(
        self, mock_log, mock_sleep, mock_deploy, mock_generate, mock_apply, mock_clean
    ):
        """Parallel mode: post-apply failure still rolls back and reports via the queue."""
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        mock_sleep.side_effect = RuntimeError("interrupted")

        error_queue = queue.Queue()
        self.module.run("worker-1", error_queue)

        self.assertFalse(error_queue.empty())
        self.assertEqual(error_queue.get(), "interrupted")
        mock_clean.assert_called_once()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(f"{MODULE}.clean_network_rules")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_rules")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_error_queue_before_apply_reports_without_cleanup(
        self, mock_log, mock_deploy, mock_generate, mock_apply, mock_clean
    ):
        """Parallel mode: pre-apply failure reports via the queue and does not clean firewall rules."""
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        mock_apply.side_effect = Exception("apply failed")

        error_queue = queue.Queue()
        self.module.run("worker-1", error_queue)

        self.assertFalse(error_queue.empty())
        self.assertEqual(error_queue.get(), "apply failed")
        mock_clean.assert_not_called()
        self.assertEqual(self.mock_kubernetes.delete_pod.call_count, 1)

    @patch(f"{MODULE}.clean_network_rules")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_rules")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_cleanup_runs_once_when_pod_deletion_fails(
        self, mock_log, mock_sleep, mock_deploy, mock_generate, mock_apply, mock_clean
    ):
        """
        If pod deletion fails after a successful cleanup, cleanup must NOT run a
        second time. clean_network_rules deletes INPUT/OUTPUT position 1 per
        rule, so a second pass would delete unrelated firewall rules. Rollback
        runs in `finally`, guaranteeing exactly one cleanup pass.
        """
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        self.mock_kubernetes.delete_pod.side_effect = Exception("api error")

        with self.assertRaises(Exception):
            self.module.run("worker-1")

        mock_clean.assert_called_once()

    @patch(f"{MODULE}.clean_network_rules")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_rules")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_parallel_cleanup_failure_reaches_error_queue(
        self, mock_log, mock_sleep, mock_deploy, mock_generate, mock_apply, mock_clean
    ):
        """
        Regression: in parallel mode a cleanup-time failure must be reported via
        error_queue (matching main), not escape as a raised exception.
        """
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        self.mock_kubernetes.delete_pod.side_effect = Exception("api 500 during delete")

        error_queue = queue.Queue()
        # Must not raise.
        self.module.run("worker-1", error_queue)

        self.assertFalse(error_queue.empty())
        self.assertEqual(error_queue.get(), "api 500 during delete")
        mock_clean.assert_called_once()

    @patch(f"{MODULE}.clean_network_rules")
    @patch(f"{MODULE}.apply_network_rules")
    @patch(f"{MODULE}.generate_rules")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_original_error_preserved_when_cleanup_also_fails(
        self, mock_log, mock_sleep, mock_deploy, mock_generate, mock_apply, mock_clean
    ):
        """
        Regression: if rollback cleanup ALSO fails, the original scenario error
        must still be reported (not the cleanup error, and not lost).
        """
        mock_generate.return_value = (["in-rule"], ["out-rule"])
        mock_sleep.side_effect = RuntimeError("scenario boom")
        mock_clean.side_effect = Exception("cleanup failed")

        error_queue = queue.Queue()
        self.module.run("worker-1", error_queue)

        self.assertEqual(error_queue.get(), "scenario boom")


if __name__ == "__main__":
    unittest.main()
