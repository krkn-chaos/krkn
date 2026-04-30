#!/usr/bin/env python3

"""
Test suite for VmiNetworkChaosModule

Usage:
    python -m unittest tests/test_vmi_network_chaos.py -v
    python -m coverage run -a -m unittest tests/test_vmi_network_chaos.py -v
"""

import queue
import unittest
from unittest.mock import MagicMock, patch

from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosScenarioType,
    NetworkChaosConfig,
)
from krkn.scenario_plugins.network_chaos_ng.modules.vmi_network_chaos import (
    VmiNetworkChaosModule,
)

MODULE = "krkn.scenario_plugins.network_chaos_ng.modules.vmi_network_chaos"


def _make_config(**overrides):
    defaults = dict(
        id="vmi_network_chaos",
        image="quay.io/krkn-chaos/krkn-network-chaos:latest",
        wait_duration=300,
        test_duration=60,
        label_selector="",
        service_account="",
        taints=[],
        namespace="virt-density-udn-3",
        instance_count=1,
        execution="serial",
        target=".*",
        interfaces=[],
        ingress=True,
        egress=True,
        latency="100ms",
        loss="10",
        bandwidth="100mbit",
    )
    defaults.update(overrides)
    return NetworkChaosConfig(**defaults)


def _make_container(name, ready=True, container_id="containerd://abc123"):
    c = MagicMock()
    c.name = name
    c.ready = ready
    c.containerId = container_id
    return c


class TestVmiNetworkChaosModuleInit(unittest.TestCase):

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.config = _make_config()
        self.module = VmiNetworkChaosModule(self.config, self.mock_kubecli)

    def test_initialization(self):
        self.assertEqual(self.module.config, self.config)
        self.assertEqual(self.module.kubecli, self.mock_kubecli)

    def test_get_config(self):
        scenario_type, config = self.module.get_config()
        self.assertEqual(scenario_type, NetworkChaosScenarioType.VMI)
        self.assertEqual(config, self.config)


class TestVmiNetworkChaosModuleGetTargets(unittest.TestCase):

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes
        self.config = _make_config(
            namespace="virt-density-udn-3",
            target="virt-server-.*",
        )
        self.module = VmiNetworkChaosModule(self.config, self.mock_kubecli)

    def test_get_targets_success(self):
        vmis = [
            {"metadata": {"name": "virt-server-1", "namespace": "virt-density-udn-3"}},
            {"metadata": {"name": "virt-server-2", "namespace": "virt-density-udn-3"}},
        ]
        self.mock_kubernetes.get_vmis.return_value = vmis

        result = self.module.get_targets()

        self.assertEqual(
            result,
            [
                "virt-density-udn-3/virt-server-1",
                "virt-density-udn-3/virt-server-2",
            ],
        )
        self.mock_kubernetes.get_vmis.assert_called_once_with(
            "virt-server-.*", "virt-density-udn-3", label_selector=None
        )

    def test_get_targets_no_namespace_raises(self):
        self.config.namespace = None
        with self.assertRaises(Exception) as ctx:
            self.module.get_targets()
        self.assertIn("namespace not specified", str(ctx.exception))

    def test_get_targets_no_vmis_returns_empty(self):
        self.mock_kubernetes.get_vmis.return_value = []
        result = self.module.get_targets()
        self.assertEqual(result, [])

    def test_get_targets_regex_filters_namespace(self):
        vmis = [
            {"metadata": {"name": "virt-server-1", "namespace": "virt-density-udn-3"}},
            {"metadata": {"name": "virt-server-2", "namespace": "other-namespace"}},
        ]
        self.mock_kubernetes.get_vmis.return_value = vmis
        result = self.module.get_targets()
        self.assertIn("virt-density-udn-3/virt-server-1", result)
        self.assertNotIn("other-namespace/virt-server-2", result)

    def test_get_targets_passes_label_selector(self):
        self.config.label_selector = "app=myapp"
        self.mock_kubernetes.get_vmis.return_value = []
        self.module.get_targets()
        self.mock_kubernetes.get_vmis.assert_called_once_with(
            "virt-server-.*", "virt-density-udn-3", label_selector="app=myapp"
        )

    def test_get_targets_empty_label_selector_passes_none(self):
        self.config.label_selector = ""
        self.mock_kubernetes.get_vmis.return_value = []
        self.module.get_targets()
        self.mock_kubernetes.get_vmis.assert_called_once_with(
            "virt-server-.*", "virt-density-udn-3", label_selector=None
        )


class TestVmiNetworkChaosModuleRun(unittest.TestCase):

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes
        self.config = _make_config(
            namespace="virt-density-udn-.*",
            target="virt-server-.*",
            test_duration=60,
            interfaces=[],
            latency="100ms",
            loss="10",
            bandwidth="100mbit",
        )
        self.module = VmiNetworkChaosModule(self.config, self.mock_kubecli)

        self.mock_kubernetes.get_vmi.return_value = {
            "status": {"nodeName": "worker-1"}
        }
        self.mock_kubernetes.list_pods.return_value = [
            "virt-launcher-virt-server-3-abc12"
        ]

        compute = _make_container("compute", ready=True, container_id="containerd://deadbeef")
        virt_launcher = _make_container("virt-launcher", ready=False, container_id="")
        mock_pod_info = MagicMock()
        mock_pod_info.containers = [virt_launcher, compute]
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info
        self.mock_kubernetes.get_pod_pids.return_value = ["100", "101", "102"]

    # ------------------------------------------------------------------ success

    @patch(f"{MODULE}.common_delete_limit_rules")
    @patch(f"{MODULE}.common_set_limit_rules")
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_success(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_set, mock_del
    ):
        self.module.run("virt-density-udn-3/virt-server-3")

        mock_deploy.assert_called_once()
        mock_find.assert_called_once()
        mock_tap.assert_called_once()
        mock_set.assert_called_once()
        mock_sleep.assert_called_once_with(60)
        mock_del.assert_called_once()
        self.mock_kubernetes.delete_pod.assert_called_once()

    @patch(f"{MODULE}.common_delete_limit_rules")
    @patch(f"{MODULE}.common_set_limit_rules")
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_uses_resolved_namespace_not_regex(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_set, mock_del
    ):
        """Kubernetes calls must use the real namespace, not the regex pattern."""
        self.module.run("virt-density-udn-3/virt-server-3")

        self.mock_kubernetes.get_vmi.assert_called_once_with(
            "virt-server-3", "virt-density-udn-3"
        )
        deploy_config = mock_deploy.call_args[0][0]
        self.assertEqual(deploy_config.namespace, "virt-density-udn-3")
        self.assertNotEqual(deploy_config.namespace, "virt-density-udn-.*")

    # ------------------------------------------------------------------ chaos config passed correctly

    @patch(f"{MODULE}.common_delete_limit_rules")
    @patch(f"{MODULE}.common_set_limit_rules")
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_passes_latency_loss_bandwidth_to_set_limit_rules(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_set, mock_del
    ):
        self.module.run("virt-density-udn-3/virt-server-3")

        call_kwargs = {
            k: v
            for k, v in zip(
                ["egress", "ingress", "interfaces", "bandwidth", "latency", "loss"],
                mock_set.call_args[0],
            )
        }
        self.assertEqual(call_kwargs["latency"], "100ms")
        self.assertEqual(call_kwargs["loss"], "10")
        self.assertEqual(call_kwargs["bandwidth"], "100mbit")

    @patch(f"{MODULE}.common_delete_limit_rules")
    @patch(f"{MODULE}.common_set_limit_rules")
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_passes_netns_pid_as_pids_list(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_set, mock_del
    ):
        """common_set_limit_rules must receive [netns_pid], not the full pids list."""
        self.module.run("virt-density-udn-3/virt-server-3")

        call_kwargs = mock_set.call_args[1]
        self.assertEqual(call_kwargs["pids"], ["101"])

    @patch(f"{MODULE}.common_delete_limit_rules")
    @patch(f"{MODULE}.common_set_limit_rules")
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_passes_tap_iface_as_interfaces_list(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_set, mock_del
    ):
        """common_set_limit_rules must receive [iface], not config.interfaces."""
        self.module.run("virt-density-udn-3/virt-server-3")

        iface_arg = mock_set.call_args[0][2]
        self.assertEqual(iface_arg, ["tap0"])

    # ------------------------------------------------------------------ error paths

    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_vmi_not_found_raises(self, mock_log, mock_deploy):
        self.mock_kubernetes.get_vmi.return_value = None
        with self.assertRaises(Exception) as ctx:
            self.module.run("virt-density-udn-3/virt-server-3")
        self.assertIn("not found", str(ctx.exception))

    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_vmi_no_node_raises(self, mock_log, mock_deploy):
        self.mock_kubernetes.get_vmi.return_value = {"status": {}}
        with self.assertRaises(Exception) as ctx:
            self.module.run("virt-density-udn-3/virt-server-3")
        self.assertIn("unable to determine node", str(ctx.exception))

    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_no_virt_launcher_pod_raises(self, mock_log, mock_deploy):
        self.mock_kubernetes.list_pods.return_value = []
        with self.assertRaises(Exception) as ctx:
            self.module.run("virt-density-udn-3/virt-server-3")
        self.assertIn("no virt-launcher pod found", str(ctx.exception))

    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_no_pod_info_raises(self, mock_log, mock_deploy):
        self.mock_kubernetes.get_pod_info.return_value = None
        with self.assertRaises(Exception) as ctx:
            self.module.run("virt-density-udn-3/virt-server-3")
        self.assertIn("impossible to retrieve info", str(ctx.exception))

    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_no_pids_raises(self, mock_log, mock_deploy):
        self.mock_kubernetes.get_pod_pids.return_value = None
        with self.assertRaises(Exception) as ctx:
            self.module.run("virt-density-udn-3/virt-server-3")
        self.assertIn("impossible to resolve PIDs", str(ctx.exception))

    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value=None)
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_no_netns_pid_raises(self, mock_log, mock_deploy, mock_find):
        with self.assertRaises(Exception) as ctx:
            self.module.run("virt-density-udn-3/virt-server-3")
        self.assertIn("could not find a PID", str(ctx.exception))

    # ------------------------------------------------------------------ error queue

    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_error_queue_captures_exception(self, mock_log, mock_deploy):
        self.mock_kubernetes.get_vmi.return_value = None
        error_queue = queue.Queue()
        self.module.run("virt-density-udn-3/virt-server-3", error_queue)
        self.assertFalse(error_queue.empty())
        self.assertIn("not found", error_queue.get())


class TestVmiNetworkChaosModuleRollback(unittest.TestCase):

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes
        self.config = _make_config(
            namespace="virt-density-udn-3",
            target="virt-server-.*",
            test_duration=60,
            interfaces=[],
        )
        self.module = VmiNetworkChaosModule(self.config, self.mock_kubecli)

        self.mock_kubernetes.get_vmi.return_value = {"status": {"nodeName": "worker-1"}}
        self.mock_kubernetes.list_pods.return_value = ["virt-launcher-virt-server-3-abc12"]
        compute = _make_container("compute", ready=True, container_id="containerd://deadbeef")
        mock_pod_info = MagicMock()
        mock_pod_info.containers = [compute]
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info
        self.mock_kubernetes.get_pod_pids.return_value = ["100", "101", "102"]

    def test_rollback_calls_delete_limit_rules_then_delete_when_chaos_applied(self):
        with patch(f"{MODULE}.common_delete_limit_rules") as mock_del:
            self.module._rollback("ns", "chaos-pod", "101", "tap0")
        mock_del.assert_called_once()
        del_args = mock_del.call_args[0]
        self.assertEqual(del_args[2], ["tap0"])   # interfaces
        self.assertEqual(del_args[6], ["101"])    # pids
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "ns")

    def test_rollback_skips_delete_limit_rules_when_chaos_not_applied(self):
        with patch(f"{MODULE}.common_delete_limit_rules") as mock_del:
            self.module._rollback("ns", "chaos-pod")
        mock_del.assert_not_called()
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "ns")

    @patch(f"{MODULE}.common_delete_limit_rules")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_rollback_deletes_pod_on_error_before_chaos(
        self, mock_log, mock_deploy, mock_del
    ):
        """Pod deployed but setup fails before chaos: delete only, no limit rules."""
        self.mock_kubernetes.get_pod_info.return_value = None
        with self.assertRaises(Exception):
            self.module.run("virt-density-udn-3/virt-server-3")
        self.mock_kubernetes.delete_pod.assert_called_once()
        mock_del.assert_not_called()

    @patch(f"{MODULE}.common_delete_limit_rules")
    @patch(f"{MODULE}.common_set_limit_rules")
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_rollback_calls_delete_limit_rules_on_error_after_chaos(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_set, mock_del
    ):
        """If interrupted after chaos is applied, delete_limit_rules and delete_pod called."""
        mock_sleep.side_effect = RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            self.module.run("virt-density-udn-3/virt-server-3")
        mock_del.assert_called_once()
        self.mock_kubernetes.delete_pod.assert_called_once()

    @patch(f"{MODULE}.common_delete_limit_rules")
    @patch(f"{MODULE}.common_set_limit_rules")
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_rollback_passes_correct_pid_and_iface_on_error(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_set, mock_del
    ):
        mock_sleep.side_effect = RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            self.module.run("virt-density-udn-3/virt-server-3")
        del_args = mock_del.call_args[0]
        self.assertEqual(del_args[2], ["tap0"])   # interfaces
        self.assertEqual(del_args[6], ["101"])    # pids


if __name__ == "__main__":
    unittest.main()
