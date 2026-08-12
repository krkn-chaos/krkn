#!/usr/bin/env python3

"""
Test suite for GpuDeviceScenarioPlugin and GPU utilities

Usage:
    python -m coverage run -a -m unittest tests/test_gpu_device_scenario_plugin.py -v
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

from krkn_lib.k8s import KrknKubernetes

from krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin import (
    GpuDeviceScenarioPlugin,
)
from krkn.scenario_plugins.gpu_device.models.models import InputParams
from krkn.utils.gpu import (
    discover_gpu_nodes,
    get_node_gpu_allocatable,
    validate_gpu_operator_present,
    find_gpu_operator_pods,
    wait_for_gpu_allocatable,
    validate_gpu_health_on_node,
)


class TestGpuDeviceScenarioPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = GpuDeviceScenarioPlugin()

    def tearDown(self):
        self.plugin = None

    def test_get_scenario_types(self):
        result = self.plugin.get_scenario_types()
        self.assertEqual(result, ["gpu_device_plugin_scenarios"])
        self.assertEqual(len(result), 1)


class TestInputParams(unittest.TestCase):

    def test_defaults(self):
        params = InputParams({})
        self.assertEqual(params.namespace, "nvidia-gpu-operator")
        self.assertEqual(params.node_selector, "")
        self.assertEqual(params.number_of_nodes, 1)
        self.assertEqual(
            params.pod_label_selector, "app=nvidia-device-plugin-daemonset"
        )
        self.assertEqual(params.recovery_timeout, 120)
        self.assertTrue(params.expected_recovery)
        self.assertTrue(params.verify_allocatable)
        self.assertEqual(params.krkn_pod_recovery_time, 120)
        self.assertTrue(params.validate_gpu_health)

    def test_explicit_values(self):
        config = {
            "namespace": "custom-ns",
            "node_selector": "gpu=true",
            "number_of_nodes": 3,
            "pod_label_selector": "app=custom-plugin",
            "recovery_timeout": 300,
            "expected_recovery": False,
            "verify_allocatable": False,
            "krkn_pod_recovery_time": 60,
            "validate_gpu_health": False,
        }
        params = InputParams(config)
        self.assertEqual(params.namespace, "custom-ns")
        self.assertEqual(params.node_selector, "gpu=true")
        self.assertEqual(params.number_of_nodes, 3)
        self.assertEqual(params.pod_label_selector, "app=custom-plugin")
        self.assertEqual(params.recovery_timeout, 300)
        self.assertFalse(params.expected_recovery)
        self.assertFalse(params.verify_allocatable)
        self.assertEqual(params.krkn_pod_recovery_time, 60)
        self.assertFalse(params.validate_gpu_health)

    def test_partial_config_uses_defaults(self):
        params = InputParams({"namespace": "my-ns"})
        self.assertEqual(params.namespace, "my-ns")
        self.assertEqual(params.recovery_timeout, 120)
        self.assertTrue(params.verify_allocatable)


class TestGpuUtils(unittest.TestCase):

    def _make_mock_node(self, name, gpu_count):
        node = MagicMock()
        node.metadata.name = name
        node.status.allocatable = (
            {"nvidia.com/gpu": str(gpu_count)} if gpu_count > 0 else {}
        )
        return node

    def test_discover_gpu_nodes(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.list_nodes.return_value = ["node1", "node2", "node3"]

        node1 = self._make_mock_node("node1", 2)
        node2 = self._make_mock_node("node2", 0)
        node3 = self._make_mock_node("node3", 1)
        kubecli.cli.read_node.side_effect = lambda name: {
            "node1": node1,
            "node2": node2,
            "node3": node3,
        }[name]

        result = discover_gpu_nodes(kubecli)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], {"name": "node1", "gpu_count": 2})
        self.assertEqual(result[1], {"name": "node3", "gpu_count": 1})

    def test_discover_gpu_nodes_none_found(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.list_nodes.return_value = ["node1"]

        node1 = self._make_mock_node("node1", 0)
        kubecli.cli.read_node.return_value = node1

        result = discover_gpu_nodes(kubecli)
        self.assertEqual(result, [])

    def test_get_node_gpu_allocatable(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        node = self._make_mock_node("gpu-node", 4)
        kubecli.cli.read_node.return_value = node

        count = get_node_gpu_allocatable(kubecli, "gpu-node")
        self.assertEqual(count, 4)

    def test_get_node_gpu_allocatable_no_gpu(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        node = self._make_mock_node("cpu-node", 0)
        kubecli.cli.read_node.return_value = node

        count = get_node_gpu_allocatable(kubecli, "cpu-node")
        self.assertEqual(count, 0)

    def test_get_node_gpu_allocatable_none_allocatable(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        node = MagicMock()
        node.status.allocatable = None
        kubecli.cli.read_node.return_value = node

        count = get_node_gpu_allocatable(kubecli, "node")
        self.assertEqual(count, 0)

    def test_validate_gpu_operator_present_success(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.list_pods.return_value = ["pod1", "pod2"]

        self.assertTrue(
            validate_gpu_operator_present(kubecli, "nvidia-gpu-operator")
        )

    def test_validate_gpu_operator_present_no_pods(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.list_pods.return_value = []

        self.assertFalse(
            validate_gpu_operator_present(kubecli, "nvidia-gpu-operator")
        )

    def test_validate_gpu_operator_present_exception(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.list_pods.side_effect = Exception("namespace not found")

        self.assertFalse(
            validate_gpu_operator_present(kubecli, "nonexistent")
        )

    def test_find_gpu_operator_pods(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = [
            ("nvidia-device-plugin-abc", "nvidia-gpu-operator")
        ]

        pods = find_gpu_operator_pods(
            kubecli,
            "nvidia-gpu-operator",
            "app=nvidia-device-plugin-daemonset",
        )

        self.assertEqual(len(pods), 1)
        self.assertEqual(pods[0][0], "nvidia-device-plugin-abc")
        kubecli.select_pods_by_namespace_pattern_and_label.assert_called_once_with(
            namespace_pattern="^nvidia-gpu-operator$",
            label_selector="app=nvidia-device-plugin-daemonset",
            field_selector="status.phase=Running",
        )

    @patch("krkn.utils.gpu.time.sleep", return_value=None)
    def test_wait_for_gpu_allocatable_success(self, mock_sleep):
        kubecli = MagicMock(spec=KrknKubernetes)
        node_recovering = self._make_mock_node("node1", 0)
        node_recovered = self._make_mock_node("node1", 2)
        kubecli.cli.read_node.side_effect = [
            node_recovering,
            node_recovered,
        ]

        result = wait_for_gpu_allocatable(kubecli, "node1", 2, 60)
        self.assertTrue(result)

    @patch("krkn.utils.gpu.time.sleep", return_value=None)
    def test_wait_for_gpu_allocatable_timeout(self, mock_sleep):
        kubecli = MagicMock(spec=KrknKubernetes)
        node = self._make_mock_node("node1", 0)
        kubecli.cli.read_node.return_value = node

        result = wait_for_gpu_allocatable(kubecli, "node1", 2, 1)
        self.assertFalse(result)

    def test_validate_gpu_health_on_node_success(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = [
            ("nvidia-driver-daemonset-abc", "nvidia-gpu-operator")
        ]
        kubecli.exec_cmd_in_pod.return_value = (
            "NVIDIA A30, GPU-abc123, 24576 MiB"
        )

        result = validate_gpu_health_on_node(kubecli, "gpu-node")

        self.assertTrue(result)
        kubecli.select_pods_by_namespace_pattern_and_label.assert_called_once_with(
            namespace_pattern="^nvidia-gpu-operator$",
            label_selector="app.kubernetes.io/component=nvidia-driver",
            field_selector="spec.nodeName=gpu-node,status.phase=Running",
        )
        kubecli.exec_cmd_in_pod.assert_called_once()

    def test_validate_gpu_health_on_node_failure(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = [
            ("nvidia-driver-daemonset-abc", "nvidia-gpu-operator")
        ]
        kubecli.exec_cmd_in_pod.side_effect = Exception(
            "nvidia-smi not found"
        )

        result = validate_gpu_health_on_node(kubecli, "gpu-node")

        self.assertFalse(result)

    def test_validate_gpu_health_on_node_no_driver_pod(self):
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = []

        result = validate_gpu_health_on_node(kubecli, "gpu-node")

        self.assertFalse(result)

    def test_validate_gpu_health_on_node_error_output(self):
        """nvidia-smi error message should fail health check even though it contains 'NVIDIA'"""
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = [
            ("nvidia-driver-daemonset-abc", "nvidia-gpu-operator")
        ]
        kubecli.exec_cmd_in_pod.return_value = (
            "NVIDIA-SMI has failed because it couldn't communicate "
            "with the NVIDIA driver."
        )

        result = validate_gpu_health_on_node(kubecli, "gpu-node")

        self.assertFalse(result)

    def test_validate_gpu_health_on_node_empty_output(self):
        """Empty nvidia-smi output should fail health check"""
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = [
            ("nvidia-driver-daemonset-abc", "nvidia-gpu-operator")
        ]
        kubecli.exec_cmd_in_pod.return_value = ""

        result = validate_gpu_health_on_node(kubecli, "gpu-node")

        self.assertFalse(result)

    def test_validate_gpu_health_custom_namespace(self):
        """Health check should use the provided namespace"""
        kubecli = MagicMock(spec=KrknKubernetes)
        kubecli.select_pods_by_namespace_pattern_and_label.return_value = [
            ("nvidia-driver-daemonset-abc", "custom-ns")
        ]
        kubecli.exec_cmd_in_pod.return_value = (
            "NVIDIA A30, GPU-abc123, 24576 MiB"
        )

        result = validate_gpu_health_on_node(
            kubecli, "gpu-node", namespace="custom-ns"
        )

        self.assertTrue(result)
        kubecli.select_pods_by_namespace_pattern_and_label.assert_called_once_with(
            namespace_pattern="^custom-ns$",
            label_selector="app.kubernetes.io/component=nvidia-driver",
            field_selector="spec.nodeName=gpu-node,status.phase=Running",
        )


class TestGpuDeviceDisruption(unittest.TestCase):

    def setUp(self):
        self.plugin = GpuDeviceScenarioPlugin()
        self.kubecli = MagicMock(spec=KrknKubernetes)

    def tearDown(self):
        self.plugin = None
        self.kubecli = None

    def _make_pod_info(self, node_name):
        pod_info = MagicMock()
        pod_info.spec.node_name = node_name
        return pod_info

    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.validate_gpu_operator_present")
    def test_preflight_fails_no_gpu_operator(self, mock_validate):
        mock_validate.return_value = False
        config = InputParams({})
        telemetry = MagicMock()

        result = self.plugin._run_disruption(config, self.kubecli, telemetry)

        self.assertEqual(result, 1)
        mock_validate.assert_called_once()

    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.validate_gpu_operator_present")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.find_gpu_operator_pods")
    def test_preflight_fails_no_device_plugin_pods(
        self, mock_find, mock_validate
    ):
        mock_validate.return_value = True
        mock_find.return_value = []
        config = InputParams({})
        telemetry = MagicMock()

        result = self.plugin._run_disruption(config, self.kubecli, telemetry)

        self.assertEqual(result, 1)

    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.validate_gpu_operator_present")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.find_gpu_operator_pods")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.discover_gpu_nodes")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.get_node_gpu_allocatable")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.validate_gpu_health_on_node")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.wait_for_gpu_allocatable")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.select_and_monitor_by_namespace_pattern_and_label")
    def test_successful_disruption_and_recovery(
        self,
        mock_monitor,
        mock_wait_alloc,
        mock_health,
        mock_get_alloc,
        mock_discover,
        mock_find_pods,
        mock_validate_op,
    ):
        mock_validate_op.return_value = True
        mock_find_pods.return_value = [
            ("nvidia-device-plugin-abc", "nvidia-gpu-operator")
        ]
        mock_discover.return_value = [{"name": "gpu-node", "gpu_count": 1}]
        mock_get_alloc.return_value = 1
        mock_health.return_value = True
        mock_wait_alloc.return_value = True

        # Mock pod info for node matching
        self.kubecli.read_pod.return_value = self._make_pod_info("gpu-node")

        # Mock monitoring future
        mock_snapshot = MagicMock()
        mock_status = MagicMock()
        mock_status.unrecovered = []
        mock_snapshot.get_pods_status.return_value = mock_status
        mock_future = MagicMock()
        mock_future.result.return_value = mock_snapshot
        mock_monitor.return_value = mock_future

        # Mock rollback handler
        self.plugin.rollback_handler = MagicMock()

        config = InputParams(
            {"verify_allocatable": True, "validate_gpu_health": True}
        )
        telemetry = MagicMock()

        result = self.plugin._run_disruption(config, self.kubecli, telemetry)

        self.assertEqual(result, 0)
        self.kubecli.delete_pod.assert_called_once_with(
            "nvidia-device-plugin-abc", "nvidia-gpu-operator"
        )
        mock_wait_alloc.assert_called_once()
        # Pre + post health checks
        self.assertEqual(mock_health.call_count, 2)

    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.validate_gpu_operator_present")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.find_gpu_operator_pods")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.discover_gpu_nodes")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.get_node_gpu_allocatable")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.select_and_monitor_by_namespace_pattern_and_label")
    def test_recovery_timeout_unrecovered_pods(
        self,
        mock_monitor,
        mock_get_alloc,
        mock_discover,
        mock_find_pods,
        mock_validate_op,
    ):
        mock_validate_op.return_value = True
        mock_find_pods.return_value = [
            ("nvidia-device-plugin-abc", "nvidia-gpu-operator")
        ]
        mock_discover.return_value = [{"name": "gpu-node", "gpu_count": 1}]
        mock_get_alloc.return_value = 1

        self.kubecli.read_pod.return_value = self._make_pod_info("gpu-node")

        unrecovered_pod = MagicMock()
        unrecovered_pod.name = "nvidia-device-plugin-abc"
        mock_snapshot = MagicMock()
        mock_status = MagicMock()
        mock_status.unrecovered = [unrecovered_pod]
        mock_snapshot.get_pods_status.return_value = mock_status
        mock_future = MagicMock()
        mock_future.result.return_value = mock_snapshot
        mock_monitor.return_value = mock_future

        self.plugin.rollback_handler = MagicMock()

        config = InputParams({"validate_gpu_health": False})
        telemetry = MagicMock()

        result = self.plugin._run_disruption(config, self.kubecli, telemetry)

        self.assertEqual(result, 1)

    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.validate_gpu_operator_present")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.find_gpu_operator_pods")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.discover_gpu_nodes")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.get_node_gpu_allocatable")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.validate_gpu_health_on_node")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.wait_for_gpu_allocatable")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.select_and_monitor_by_namespace_pattern_and_label")
    def test_allocatable_not_restored(
        self,
        mock_monitor,
        mock_wait_alloc,
        mock_health,
        mock_get_alloc,
        mock_discover,
        mock_find_pods,
        mock_validate_op,
    ):
        mock_validate_op.return_value = True
        mock_find_pods.return_value = [
            ("nvidia-device-plugin-abc", "nvidia-gpu-operator")
        ]
        mock_discover.return_value = [{"name": "gpu-node", "gpu_count": 1}]
        mock_get_alloc.return_value = 1
        mock_health.return_value = True
        mock_wait_alloc.return_value = False

        self.kubecli.read_pod.return_value = self._make_pod_info("gpu-node")

        mock_snapshot = MagicMock()
        mock_status = MagicMock()
        mock_status.unrecovered = []
        mock_snapshot.get_pods_status.return_value = mock_status
        mock_future = MagicMock()
        mock_future.result.return_value = mock_snapshot
        mock_monitor.return_value = mock_future

        self.plugin.rollback_handler = MagicMock()

        config = InputParams(
            {"verify_allocatable": True, "validate_gpu_health": False}
        )
        telemetry = MagicMock()

        result = self.plugin._run_disruption(config, self.kubecli, telemetry)

        self.assertEqual(result, 1)
        mock_wait_alloc.assert_called_once()

    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.validate_gpu_operator_present")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.find_gpu_operator_pods")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.discover_gpu_nodes")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.get_node_gpu_allocatable")
    @patch("krkn.scenario_plugins.gpu_device.gpu_device_scenario_plugin.select_and_monitor_by_namespace_pattern_and_label")
    def test_expected_recovery_false_returns_success(
        self,
        mock_monitor,
        mock_get_alloc,
        mock_discover,
        mock_find_pods,
        mock_validate_op,
    ):
        """When expected_recovery=False and pods don't recover, scenario should pass"""
        mock_validate_op.return_value = True
        mock_find_pods.return_value = [
            ("nvidia-device-plugin-abc", "nvidia-gpu-operator")
        ]
        mock_discover.return_value = [{"name": "gpu-node", "gpu_count": 1}]
        mock_get_alloc.return_value = 1

        self.kubecli.read_pod.return_value = self._make_pod_info("gpu-node")

        unrecovered_pod = MagicMock()
        unrecovered_pod.name = "nvidia-device-plugin-abc"
        mock_snapshot = MagicMock()
        mock_status = MagicMock()
        mock_status.unrecovered = [unrecovered_pod]
        mock_snapshot.get_pods_status.return_value = mock_status
        mock_future = MagicMock()
        mock_future.result.return_value = mock_snapshot
        mock_monitor.return_value = mock_future

        self.plugin.rollback_handler = MagicMock()

        config = InputParams({
            "expected_recovery": False,
            "validate_gpu_health": False,
        })
        telemetry = MagicMock()

        result = self.plugin._run_disruption(config, self.kubecli, telemetry)

        # Should return 0 (success) since we don't expect recovery
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
