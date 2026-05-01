#!/usr/bin/env python3

"""
Test suite for VmiNetworkFilterModule

Usage:
    python -m unittest tests/test_vmi_network_filter.py -v
    python -m coverage run -a -m unittest tests/test_vmi_network_filter.py -v
"""

import queue
import unittest
from unittest.mock import MagicMock, call, patch

from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosScenarioType,
    NetworkFilterConfig,
)
from krkn.scenario_plugins.network_chaos_ng.modules.vmi_network_filter import (
    VmiNetworkFilterModule,
)

MODULE = "krkn.scenario_plugins.network_chaos_ng.modules.vmi_network_filter"


def _make_config(**overrides):
    defaults = dict(
        id="vmi_network_filter",
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
        ports=[],
        protocols=["tcp", "udp"],
    )
    defaults.update(overrides)
    return NetworkFilterConfig(**defaults)


def _make_container(name, ready=True, container_id="containerd://abc123"):
    c = MagicMock()
    c.name = name
    c.ready = ready
    c.containerId = container_id
    return c


class TestVmiNetworkFilterModuleInit(unittest.TestCase):

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.config = _make_config()
        self.module = VmiNetworkFilterModule(self.config, self.mock_kubecli)

    def test_initialization(self):
        self.assertEqual(self.module.config, self.config)
        self.assertEqual(self.module.kubecli, self.mock_kubecli)
        self.assertEqual(self.module.base_network_config, self.config)

    def test_get_config(self):
        scenario_type, config = self.module.get_config()
        self.assertEqual(scenario_type, NetworkChaosScenarioType.VMI)
        self.assertEqual(config, self.config)


class TestVmiNetworkFilterModuleGetTargets(unittest.TestCase):

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes
        self.config = _make_config(
            namespace="virt-density-udn-3",
            target="virt-server-.*",
        )
        self.module = VmiNetworkFilterModule(self.config, self.mock_kubecli)

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

    def test_get_targets_regex_filters_name(self):
        self.config.target = "virt-server-1"
        vmis = [
            {"metadata": {"name": "virt-server-1", "namespace": "virt-density-udn-3"}},
            {"metadata": {"name": "virt-server-10", "namespace": "virt-density-udn-3"}},
        ]
        self.mock_kubernetes.get_vmis.return_value = vmis

        result = self.module.get_targets()

        # re.match("virt-server-1", "virt-server-10") matches (prefix), both included
        self.assertIn("virt-density-udn-3/virt-server-1", result)

    def test_get_targets_regex_filters_namespace(self):
        self.config.namespace = "virt-density-udn-3"
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


class TestVmiNetworkFilterModuleRun(unittest.TestCase):

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes
        self.config = _make_config(
            namespace="virt-density-udn-.*",
            target="virt-server-.*",
            test_duration=60,
            interfaces=[],
        )
        self.module = VmiNetworkFilterModule(self.config, self.mock_kubecli)

        # common happy-path mocks
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

    # ------------------------------------------------------------------ helpers

    def _patch_run(self):
        """Return a context-manager stack that patches all external calls in run."""
        return [
            patch(f"{MODULE}.deploy_network_chaos_ng_pod"),
            patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101"),
            patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0"),
            patch(f"{MODULE}.apply_tc_vmi_chaos"),
            patch(f"{MODULE}.clean_tc_vmi_chaos"),
            patch(f"{MODULE}.time.sleep"),
            patch(f"{MODULE}.log_info"),
            patch(f"{MODULE}.log_error"),
        ]

    # ------------------------------------------------------------------ success

    @patch(f"{MODULE}.clean_tc_vmi_chaos")
    @patch(f"{MODULE}.apply_tc_vmi_chaos", return_value=([], []))
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_success(
        self,
        mock_log,
        mock_sleep,
        mock_deploy,
        mock_find_pid,
        mock_tap,
        mock_apply,
        mock_clean,
    ):
        self.module.run("virt-density-udn-3/virt-server-3")

        mock_deploy.assert_called_once()
        mock_find_pid.assert_called_once()
        mock_tap.assert_called_once()
        mock_apply.assert_called_once()
        mock_sleep.assert_called_once_with(60)
        mock_clean.assert_called_once()
        self.mock_kubernetes.delete_pod.assert_called_once()

    @patch(f"{MODULE}.clean_tc_vmi_chaos")
    @patch(f"{MODULE}.apply_tc_vmi_chaos", return_value=([], []))
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_uses_resolved_namespace_not_regex(
        self,
        mock_log,
        mock_sleep,
        mock_deploy,
        mock_find_pid,
        mock_tap,
        mock_apply,
        mock_clean,
    ):
        """Kubernetes calls must use the real namespace, not the regex pattern."""
        self.module.run("virt-density-udn-3/virt-server-3")

        # get_vmi called with the resolved namespace
        self.mock_kubernetes.get_vmi.assert_called_once_with(
            "virt-server-3", "virt-density-udn-3"
        )
        # deploy called with scoped_config (namespace = resolved), not regex
        deploy_config = mock_deploy.call_args[0][0]
        self.assertEqual(deploy_config.namespace, "virt-density-udn-3")
        self.assertNotEqual(deploy_config.namespace, "virt-density-udn-.*")

    # ------------------------------------------------------------------ vmi not found

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

    # ------------------------------------------------------------------ virt-launcher pod

    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_no_virt_launcher_pod_raises(self, mock_log, mock_deploy):
        self.mock_kubernetes.list_pods.return_value = []

        with self.assertRaises(Exception) as ctx:
            self.module.run("virt-density-udn-3/virt-server-3")

        self.assertIn("no virt-launcher pod found", str(ctx.exception))

    # ------------------------------------------------------------------ compute container

    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_no_pod_info_raises(self, mock_log, mock_deploy):
        self.mock_kubernetes.get_pod_info.return_value = None

        with self.assertRaises(Exception) as ctx:
            self.module.run("virt-density-udn-3/virt-server-3")

        self.assertIn("impossible to retrieve info", str(ctx.exception))

    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_compute_not_ready_raises(self, mock_log, mock_deploy):
        compute = _make_container("compute", ready=False, container_id="containerd://abc")
        mock_pod_info = MagicMock()
        mock_pod_info.containers = [compute]
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info

        with self.assertRaises(Exception) as ctx:
            self.module.run("virt-density-udn-3/virt-server-3")

        self.assertIn("compute container", str(ctx.exception))
        self.assertIn("not ready", str(ctx.exception))

    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_no_compute_container_raises(self, mock_log, mock_deploy):
        other = _make_container("virt-launcher", ready=True, container_id="containerd://abc")
        mock_pod_info = MagicMock()
        mock_pod_info.containers = [other]
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info

        with self.assertRaises(Exception) as ctx:
            self.module.run("virt-density-udn-3/virt-server-3")

        self.assertIn("compute container", str(ctx.exception))

    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_strips_container_id_prefix(self, mock_log, mock_deploy, mock_find):
        """containerd:// prefix must be stripped before passing to get_pod_pids."""
        compute = _make_container(
            "compute", ready=True, container_id="containerd://deadbeef123"
        )
        mock_pod_info = MagicMock()
        mock_pod_info.containers = [compute]
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info
        self.mock_kubernetes.get_pod_pids.return_value = ["100"]

        with patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0"), \
             patch(f"{MODULE}.apply_tc_vmi_chaos", return_value=([], [])), \
             patch(f"{MODULE}.clean_tc_vmi_chaos"), \
             patch(f"{MODULE}.time.sleep"):
            self.module.run("virt-density-udn-3/virt-server-3")

        call_kwargs = self.mock_kubernetes.get_pod_pids.call_args[1]
        self.assertEqual(call_kwargs["pod_container_id"], "deadbeef123")

    # ------------------------------------------------------------------ pids / netns

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

    @patch(f"{MODULE}.clean_tc_vmi_chaos")
    @patch(f"{MODULE}.apply_tc_vmi_chaos", return_value=([], []))
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_no_error_queue_raises_directly(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_apply, mock_clean
    ):
        mock_apply.side_effect = RuntimeError("tc failed")

        with self.assertRaises(RuntimeError):
            self.module.run("virt-density-udn-3/virt-server-3")

    # ------------------------------------------------------------------ apply / clean called correctly

    @patch(f"{MODULE}.clean_tc_vmi_chaos")
    @patch(f"{MODULE}.apply_tc_vmi_chaos", return_value=([], []))
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_apply_and_clean_called_with_tap_and_pid(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_apply, mock_clean
    ):
        self.module.run("virt-density-udn-3/virt-server-3")

        apply_args = mock_apply.call_args[0]
        self.assertEqual(apply_args[3], "101")   # pid
        self.assertEqual(apply_args[4], "tap0")  # iface

        clean_args = mock_clean.call_args[0]
        self.assertEqual(clean_args[3], "101")   # pid
        self.assertEqual(clean_args[4], "tap0")  # iface

    @patch(f"{MODULE}.clean_tc_vmi_chaos")
    @patch(f"{MODULE}.apply_tc_vmi_chaos", return_value=([], []))
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_chaos_pod_deleted_after_clean(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_apply, mock_clean
    ):
        """Chaos pod must be cleaned up even after a successful run."""
        self.module.run("virt-density-udn-3/virt-server-3")
        self.mock_kubernetes.delete_pod.assert_called_once()
        # namespace passed to delete_pod must be the resolved one
        delete_ns = self.mock_kubernetes.delete_pod.call_args[0][1]
        self.assertEqual(delete_ns, "virt-density-udn-3")


class TestVmiNetworkFilterModuleRollback(unittest.TestCase):

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
        self.module = VmiNetworkFilterModule(self.config, self.mock_kubecli)

        self.mock_kubernetes.get_vmi.return_value = {
            "status": {"nodeName": "worker-1"}
        }
        self.mock_kubernetes.list_pods.return_value = [
            "virt-launcher-virt-server-3-abc12"
        ]

        compute = _make_container("compute", ready=True, container_id="containerd://deadbeef")
        mock_pod_info = MagicMock()
        mock_pod_info.containers = [compute]
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info
        self.mock_kubernetes.get_pod_pids.return_value = ["100", "101", "102"]

    # ------------------------------------------------------------------ _rollback directly

    def test_rollback_calls_clean_then_delete_when_tc_applied(self):
        input_rules = ["nsenter ... iptables -I INPUT 1 -i tap0 -p tcp -j DROP"]
        output_rules = ["nsenter ... iptables -I OUTPUT 1 -p tcp -j DROP"]
        with patch(f"{MODULE}.clean_tc_vmi_chaos") as mock_clean:
            self.module._rollback("ns", "chaos-pod", "101", "tap0", input_rules, output_rules)

        mock_clean.assert_called_once_with(
            self.mock_kubernetes, "chaos-pod", "ns", "101", "tap0", input_rules, output_rules
        )
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "ns")

    def test_rollback_skips_clean_when_no_rules(self):
        with patch(f"{MODULE}.clean_tc_vmi_chaos") as mock_clean:
            self.module._rollback("ns", "chaos-pod")

        mock_clean.assert_not_called()
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "ns")

    def test_rollback_skips_clean_when_rules_none_but_pid_set(self):
        """Chaos pod deployed, netns_pid found, but rules never applied: skip clean."""
        with patch(f"{MODULE}.clean_tc_vmi_chaos") as mock_clean:
            self.module._rollback("ns", "chaos-pod", "101", "tap0", None, None)

        mock_clean.assert_not_called()
        self.mock_kubernetes.delete_pod.assert_called_once_with("chaos-pod", "ns")

    # ------------------------------------------------------------------ rollback from run: error before tc

    @patch(f"{MODULE}.clean_tc_vmi_chaos")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_rollback_deletes_pod_on_error_before_tc(
        self, mock_log, mock_deploy, mock_clean
    ):
        """Pod deployed but setup fails before tc is applied: delete only, no clean."""
        self.mock_kubernetes.get_pod_info.return_value = None

        with self.assertRaises(Exception):
            self.module.run("virt-density-udn-3/virt-server-3")

        self.mock_kubernetes.delete_pod.assert_called_once()
        mock_clean.assert_not_called()

    @patch(f"{MODULE}.clean_tc_vmi_chaos")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.log_info")
    def test_run_rollback_does_not_clean_when_no_netns_pid(
        self, mock_log, mock_deploy, mock_clean
    ):
        """No netns_pid resolved means tc was never applied: clean must not be called."""
        with patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value=None):
            with self.assertRaises(Exception):
                self.module.run("virt-density-udn-3/virt-server-3")

        mock_clean.assert_not_called()
        self.mock_kubernetes.delete_pod.assert_called_once()

    # ------------------------------------------------------------------ rollback from run: error after tc

    @patch(f"{MODULE}.clean_tc_vmi_chaos")
    @patch(f"{MODULE}.apply_tc_vmi_chaos", return_value=(["in_rule"], ["out_rule"]))
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_rollback_cleans_tc_and_deletes_pod_on_error_after_tc(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_apply, mock_clean
    ):
        """If interrupted after tc is applied, both clean and delete must be called."""
        mock_sleep.side_effect = RuntimeError("interrupted")

        with self.assertRaises(RuntimeError):
            self.module.run("virt-density-udn-3/virt-server-3")

        mock_clean.assert_called_once()
        self.mock_kubernetes.delete_pod.assert_called_once()

    @patch(f"{MODULE}.clean_tc_vmi_chaos")
    @patch(f"{MODULE}.apply_tc_vmi_chaos", return_value=(["in_rule"], ["out_rule"]))
    @patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0")
    @patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101")
    @patch(f"{MODULE}.deploy_network_chaos_ng_pod")
    @patch(f"{MODULE}.time.sleep")
    @patch(f"{MODULE}.log_info")
    def test_run_rollback_passes_correct_pid_iface_and_rules_to_clean(
        self, mock_log, mock_sleep, mock_deploy, mock_find, mock_tap, mock_apply, mock_clean
    ):
        """Clean must receive the resolved netns_pid, iface, and the rules returned by apply."""
        mock_sleep.side_effect = RuntimeError("interrupted")

        with self.assertRaises(RuntimeError):
            self.module.run("virt-density-udn-3/virt-server-3")

        clean_args = mock_clean.call_args[0]
        self.assertEqual(clean_args[3], "101")          # netns_pid
        self.assertEqual(clean_args[4], "tap0")         # iface
        self.assertEqual(clean_args[5], ["in_rule"])    # input_rules from apply
        self.assertEqual(clean_args[6], ["out_rule"])   # output_rules from apply


class TestVmiNetworkFilterPortsProtocols(unittest.TestCase):

    def setUp(self):
        self.mock_kubecli = MagicMock()
        self.mock_kubernetes = MagicMock()
        self.mock_kubecli.get_lib_kubernetes.return_value = self.mock_kubernetes

        self.mock_kubernetes.get_vmi.return_value = {"status": {"nodeName": "worker-1"}}
        self.mock_kubernetes.list_pods.return_value = ["virt-launcher-virt-server-3-abc12"]
        compute = _make_container("compute", ready=True, container_id="containerd://deadbeef")
        mock_pod_info = MagicMock()
        mock_pod_info.containers = [compute]
        self.mock_kubernetes.get_pod_info.return_value = mock_pod_info
        self.mock_kubernetes.get_pod_pids.return_value = ["100", "101", "102"]

    def _run_and_capture_apply(self, **config_overrides):
        config = _make_config(**config_overrides)
        module = VmiNetworkFilterModule(config, self.mock_kubecli)
        with patch(f"{MODULE}.deploy_network_chaos_ng_pod"), \
             patch(f"{MODULE}.find_virt_launcher_netns_pid", return_value="101"), \
             patch(f"{MODULE}.get_vmi_tap_interface", return_value="tap0"), \
             patch(f"{MODULE}.apply_tc_vmi_chaos", return_value=([], [])) as mock_apply, \
             patch(f"{MODULE}.clean_tc_vmi_chaos"), \
             patch(f"{MODULE}.time.sleep"), \
             patch(f"{MODULE}.log_info"):
            module.run("virt-density-udn-3/virt-server-3")
        return mock_apply

    def test_apply_receives_specific_ports(self):
        mock_apply = self._run_and_capture_apply(ports=[53, 80, 443])
        config_arg = mock_apply.call_args[0][5]
        self.assertEqual(config_arg.ports, [53, 80, 443])

    def test_apply_receives_empty_ports_for_all_traffic(self):
        mock_apply = self._run_and_capture_apply(ports=[])
        config_arg = mock_apply.call_args[0][5]
        self.assertEqual(config_arg.ports, [])

    def test_apply_receives_tcp_only_protocol(self):
        mock_apply = self._run_and_capture_apply(protocols=["tcp"])
        config_arg = mock_apply.call_args[0][5]
        self.assertEqual(config_arg.protocols, ["tcp"])

    def test_apply_receives_udp_only_protocol(self):
        mock_apply = self._run_and_capture_apply(protocols=["udp"])
        config_arg = mock_apply.call_args[0][5]
        self.assertEqual(config_arg.protocols, ["udp"])

    def test_apply_receives_both_protocols(self):
        mock_apply = self._run_and_capture_apply(protocols=["tcp", "udp"])
        config_arg = mock_apply.call_args[0][5]
        self.assertIn("tcp", config_arg.protocols)
        self.assertIn("udp", config_arg.protocols)

    def test_apply_receives_dns_ports_with_both_protocols(self):
        """DNS blackout: port 53 on tcp and udp."""
        mock_apply = self._run_and_capture_apply(ports=[53], protocols=["tcp", "udp"])
        config_arg = mock_apply.call_args[0][5]
        self.assertEqual(config_arg.ports, [53])
        self.assertIn("tcp", config_arg.protocols)
        self.assertIn("udp", config_arg.protocols)

    def test_apply_receives_management_ports(self):
        """Management plane loss: SSH + HTTPS + k8s API."""
        mock_apply = self._run_and_capture_apply(ports=[22, 443, 6443], protocols=["tcp"])
        config_arg = mock_apply.call_args[0][5]
        self.assertEqual(config_arg.ports, [22, 443, 6443])
        self.assertEqual(config_arg.protocols, ["tcp"])

    def test_apply_config_has_resolved_namespace_not_regex(self):
        """The config passed to apply must use the real namespace from the target string."""
        mock_apply = self._run_and_capture_apply(namespace="virt-density-udn-.*")
        config_arg = mock_apply.call_args[0][5]
        self.assertEqual(config_arg.namespace, "virt-density-udn-3")
        self.assertNotEqual(config_arg.namespace, "virt-density-udn-.*")


if __name__ == "__main__":
    unittest.main()
