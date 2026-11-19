#!/usr/bin/env python3

"""
Test suite for PodNetworkFilterModule PID resolution, cleanup re-resolution
and post-cleanup verification (issue #1711).

Usage:
    python -m unittest tests/test_pod_network_filter.py -v
    python -m coverage run -a -m unittest tests/test_pod_network_filter.py -v
"""

import queue
import unittest
from unittest.mock import MagicMock, call, patch

from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosScenarioType,
    NetworkFilterConfig,
)
from krkn.scenario_plugins.network_chaos_ng.modules.pod_network_filter import (
    PodNetworkFilterModule,
)

MODULE = "krkn.scenario_plugins.network_chaos_ng.modules.pod_network_filter"


def _make_config(**overrides):
    defaults = dict(
        id="pod_network_filter",
        image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-network-chaos",
        wait_duration=1,
        test_duration=10,
        label_selector="",
        service_account="",
        taints=[],
        namespace="test-ns",
        instance_count=1,
        execution="serial",
        target="target-pod",
        interfaces=[],
        ingress=False,
        egress=True,
        ports=[443],
        protocols=["tcp"],
    )
    defaults.update(overrides)
    return NetworkFilterConfig(**defaults)


def _make_pod_info(node_name="node-1"):
    pod_info = MagicMock()
    pod_info.nodeName = node_name
    return pod_info


class PodFilterTestBase(unittest.TestCase):
    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes

        self.config = _make_config()
        self.module = PodNetworkFilterModule(self.config, self.mock_kubecli)

        # default behaviors for a healthy single-container target
        self.mock_kubernetes.check_if_pod_exists.return_value = True
        self.mock_kubernetes.get_pod_info.return_value = _make_pod_info()
        self.mock_kubernetes.get_container_ids.return_value = ["abc123"]
        self.mock_kubernetes.get_pod_pids.return_value = ["1111"]
        # netns filter returns the same pids (all non-host-netns)
        self.mock_kubernetes.exec_cmd_in_pod.return_value = "1111"


class TestResolveTargetPids(PodFilterTestBase):
    """Host-netns PID filtering at resolution time (fix 1, plugin side)."""

    def test_host_netns_pids_are_filtered_out(self):
        # krkn-lib returns conmon (host netns) + container process;
        # the plugin's defensive filter must drop conmon
        self.mock_kubernetes.get_pod_pids.return_value = ["17097", "17099"]
        self.mock_kubernetes.exec_cmd_in_pod.return_value = "17099"

        pids = self.module._resolve_target_pids(
            "target-pod", "abc123", "helper-pod", "helper-ctr", False
        )
        self.assertEqual(pids, ["17099"])

    def test_filter_command_uses_readlink_netns_comparison(self):
        self.module._resolve_target_pids(
            "target-pod", "abc123", "helper-pod", "helper-ctr", False
        )
        cmd = self.mock_kubernetes.exec_cmd_in_pod.call_args[0][0][0]
        self.assertIn("readlink /proc/$p/ns/net", cmd)
        self.assertIn("readlink /proc/1/ns/net", cmd)
        self.assertIn("1111", cmd)

    def test_falls_back_to_raw_pids_when_filter_output_empty(self):
        # readlink unavailable or no output: keep raw list rather than
        # failing the scenario at resolution time
        self.mock_kubernetes.exec_cmd_in_pod.return_value = ""
        pids = self.module._resolve_target_pids(
            "target-pod", "abc123", "helper-pod", "helper-ctr", False
        )
        self.assertEqual(pids, ["1111"])

    def test_returns_none_when_pod_gone(self):
        self.mock_kubernetes.check_if_pod_exists.return_value = False
        pids = self.module._resolve_target_pids(
            "target-pod", "abc123", "helper-pod", "helper-ctr", False
        )
        self.assertIsNone(pids)

    def test_returns_none_when_no_pids_resolved(self):
        self.mock_kubernetes.get_pod_pids.return_value = None
        pids = self.module._resolve_target_pids(
            "target-pod", "abc123", "helper-pod", "helper-ctr", False
        )
        self.assertIsNone(pids)

    def test_backoff_container_falls_back_to_netns_path(self):
        """Container in CrashLoopBackOff back-off: no live PID, but the
        pod exists — resolution must return the netns file path marker."""
        self.mock_kubernetes.get_pod_pids.return_value = None
        self.mock_kubernetes.exec_cmd_in_pod.return_value = (
            "netnspath:/var/run/netns/abc-123"
        )

        pids = self.module._resolve_target_pids(
            "target-pod", "abc123", "helper-pod", "helper-ctr", False,
            pod_ip="10.1.2.3",
        )
        self.assertEqual(pids, ["netnspath:/var/run/netns/abc-123"])
        cmd = self.mock_kubernetes.exec_cmd_in_pod.call_args[0][0][0]
        self.assertIn("/proc/1/root/var/run/netns/*", cmd)
        self.assertIn("10.1.2.3", cmd)

    def test_backoff_without_pod_ip_returns_none(self):
        self.mock_kubernetes.get_pod_pids.return_value = None
        pids = self.module._resolve_target_pids(
            "target-pod", "abc123", "helper-pod", "helper-ctr", False,
            pod_ip=None,
        )
        self.assertIsNone(pids)



class TestVerifyRulesRemoved(PodFilterTestBase):
    """Post-cleanup verification (fix 3)."""

    def test_surviving_rules_raise_with_details(self):
        surviving = "-A OUTPUT -p tcp --dport 443 -j DROP\n"
        self.mock_kubernetes.exec_cmd_in_pod.return_value = surviving
        with self.assertRaises(Exception) as ctx:
            self.module._verify_rules_removed(
                "target-pod", ["2222"], "helper-pod", "helper-ctr", False
            )
        self.assertIn("survived cleanup", str(ctx.exception))
        self.assertIn("-A OUTPUT -p tcp --dport 443 -j DROP", str(ctx.exception))
        self.assertIn("nsenter", str(ctx.exception))

    def test_clean_namespace_passes(self):
        self.mock_kubernetes.exec_cmd_in_pod.return_value = ""
        # must not raise
        self.module._verify_rules_removed(
            "target-pod", ["2222"], "helper-pod", "helper-ctr", False
        )

    def test_skipped_when_target_gone(self):
        # no cleanup pids (pod destroyed) — nothing to verify
        self.module._verify_rules_removed(
            "target-pod", None, "helper-pod", "helper-ctr", False
        )
        self.mock_kubernetes.exec_cmd_in_pod.assert_not_called()

    def test_verification_targets_cleanup_netns(self):
        self.mock_kubernetes.exec_cmd_in_pod.return_value = ""
        self.module._verify_rules_removed(
            "target-pod", ["2222"], "helper-pod", "helper-ctr", False
        )
        cmd = self.mock_kubernetes.exec_cmd_in_pod.call_args[0][0][0]
        self.assertIn("nsenter --target 2222 --net", cmd)
        self.assertIn("DROP", cmd)


@patch(f"{MODULE}.setup_network_chaos_ng_scenario")
@patch(f"{MODULE}.generate_namespaced_rules")
@patch(f"{MODULE}.apply_network_rules")
@patch(f"{MODULE}.clean_network_rules_namespaced")
@patch(f"{MODULE}.time.sleep")
class TestRunCleanupReResolution(PodFilterTestBase):
    """Cleanup re-resolves PIDs instead of reusing apply-time ones (fix 2)."""

    def test_container_restart_gets_fresh_pids_for_cleanup(
        self, mock_sleep, mock_clean, mock_apply, mock_generate, mock_setup
    ):
        mock_setup.return_value = (["abc123"], ["eth0"])
        mock_generate.return_value = ([], ["rule-apply"])

        # first resolution (apply): pids [1111]; second (cleanup): [3333]
        self.mock_kubernetes.get_pod_pids.side_effect = [["1111"], ["3333"]]
        self.mock_kubernetes.exec_cmd_in_pod.side_effect = ["1111", "3333", ""]

        self.module.run("target-pod")

        # cleanup must be called with the fresh pids, not the stale ones
        self.assertEqual(mock_clean.call_count, 1)
        self.assertEqual(mock_clean.call_args[0][5], ["3333"])
        # apply used the original pids
        self.assertEqual(mock_generate.call_args[0][2], ["1111"])

    def test_target_pod_gone_skips_cleanup_but_verifies_nothing(
        self, mock_sleep, mock_clean, mock_apply, mock_generate, mock_setup
    ):
        mock_setup.return_value = (["abc123"], ["eth0"])
        mock_generate.return_value = ([], ["rule-apply"])

        # apply resolves pids; at cleanup time the target is gone
        self.mock_kubernetes.get_pod_pids.return_value = ["1111"]
        self.mock_kubernetes.exec_cmd_in_pod.side_effect = ["1111"]
        self.mock_kubernetes.check_if_pod_exists.side_effect = [True, False]

        self.module.run("target-pod")

        # cleanup never runs (netns destroyed with the pod)
        mock_clean.assert_not_called()
        # and the run still completes without raising
        self.mock_kubernetes.delete_pod.assert_called_once()

    def test_no_restart_reuses_same_pids(
        self, mock_sleep, mock_clean, mock_apply, mock_generate, mock_setup
    ):
        mock_setup.return_value = (["abc123"], ["eth0"])
        mock_generate.return_value = ([], ["rule-apply"])

        self.mock_kubernetes.get_pod_pids.return_value = ["1111"]
        self.mock_kubernetes.exec_cmd_in_pod.side_effect = ["1111", "1111", ""]

        self.module.run("target-pod")

        self.assertEqual(mock_clean.call_count, 1)
        self.assertEqual(mock_clean.call_args[0][5], ["1111"])

    def test_surviving_rules_fail_the_run(
        self, mock_sleep, mock_clean, mock_apply, mock_generate, mock_setup
    ):
        mock_setup.return_value = (["abc123"], ["eth0"])
        mock_generate.return_value = ([], ["rule-apply"])

        self.mock_kubernetes.get_pod_pids.return_value = ["1111"]
        # resolution filter ok, verification finds a surviving DROP
        self.mock_kubernetes.exec_cmd_in_pod.side_effect = [
            "1111",  # apply-time filter
            "1111",  # cleanup-time filter
            "-A OUTPUT -p tcp --dport 443 -j DROP\n",  # verification
        ]

        with self.assertRaises(Exception) as ctx:
            self.module.run("target-pod")
        self.assertIn("survived cleanup", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
