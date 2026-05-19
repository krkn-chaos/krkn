#!/usr/bin/env python3

"""
Test suite for StorageThrottleScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_storage_throttle_scenario_plugin.py -v
"""

import base64
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.storage_throttle.storage_throttle_scenario_plugin import (
    StorageThrottleScenarioPlugin,
    ThrottleParams,
)
from krkn.scenario_plugins.storage_throttle.storage_throttle_utils import (
    validate_cgroup_path as _validate_cgroup_path,
    validate_container_id as _validate_container_id,
    validate_maj_min as _validate_maj_min,
    validate_mount_path as _validate_mount_path,
    parse_byte_value as _parse_byte_value,
    parse_duration_value as _parse_duration_value,
)
from krkn.rollback.config import RollbackContent


class TestValidateShellInputs(unittest.TestCase):
    """Sanity checks for mount path and major:minor validation."""

    def test_validate_mount_path_ok(self):
        self.assertTrue(_validate_mount_path("/data"))
        self.assertTrue(_validate_mount_path("/var/lib/kubelet/pods/abc/volumes"))

    def test_validate_mount_path_rejects_shell_chars(self):
        self.assertFalse(_validate_mount_path("/data;rm -rf /"))
        self.assertFalse(_validate_mount_path("$(whoami)"))
        self.assertFalse(_validate_mount_path(""))

    def test_validate_mount_path_rejects_traversal(self):
        self.assertFalse(_validate_mount_path("/data/../etc/shadow"))
        self.assertFalse(_validate_mount_path("/.."))

    def test_validate_cgroup_path_ok(self):
        self.assertTrue(_validate_cgroup_path("/kubepods.slice/crio-abc.scope"))
        self.assertTrue(_validate_cgroup_path("/kubepods/abc123def456"))

    def test_validate_cgroup_path_rejects_bad(self):
        self.assertFalse(_validate_cgroup_path(""))
        self.assertFalse(_validate_cgroup_path("/kubepods/../etc"))
        self.assertFalse(_validate_cgroup_path("relative/path"))

    def test_validate_container_id_ok(self):
        self.assertTrue(_validate_container_id("abc123def456"))
        self.assertTrue(_validate_container_id("0123456789abcdef"))

    def test_validate_container_id_rejects_bad(self):
        self.assertFalse(_validate_container_id(""))
        self.assertFalse(_validate_container_id("abc;rm -rf /"))
        self.assertFalse(_validate_container_id("ABC123"))  # uppercase
        self.assertFalse(_validate_container_id("abc 123"))

    def test_validate_maj_min_ok(self):
        self.assertTrue(_validate_maj_min("8:16"))
        self.assertTrue(_validate_maj_min("259:0"))

    def test_validate_maj_min_rejects_bad(self):
        self.assertFalse(_validate_maj_min("8:16 foo"))
        self.assertFalse(_validate_maj_min("abc"))


class TestParseByteValue(unittest.TestCase):
    """Tests for _parse_byte_value — Kubernetes-style unit parsing.

    Supported binary suffixes: Ki (1024), Mi (1024^2), Gi (1024^3)
    Supported decimal suffixes: K (1000), M (1000^2), G (1000^3)
    """

    def test_plain_int(self):
        self.assertEqual(_parse_byte_value(1048576), 1048576)

    def test_plain_int_zero(self):
        self.assertEqual(_parse_byte_value(0), 0)

    def test_string_no_suffix(self):
        self.assertEqual(_parse_byte_value("1048576"), 1048576)

    def test_ki_suffix(self):
        self.assertEqual(_parse_byte_value("512Ki"), 524288)

    def test_mi_suffix(self):
        self.assertEqual(_parse_byte_value("1Mi"), 1048576)

    def test_gi_suffix(self):
        self.assertEqual(_parse_byte_value("1Gi"), 1073741824)

    def test_decimal_k_suffix(self):
        self.assertEqual(_parse_byte_value("500K"), 500000)

    def test_decimal_m_suffix(self):
        self.assertEqual(_parse_byte_value("5M"), 5000000)

    def test_decimal_g_suffix(self):
        self.assertEqual(_parse_byte_value("1G"), 1000000000)

    def test_fractional_value(self):
        self.assertEqual(_parse_byte_value("1.5Mi"), 1572864)

    def test_whitespace_handling(self):
        self.assertEqual(_parse_byte_value(" 1Mi "), 1048576)

    def test_invalid_suffix(self):
        with self.assertRaises(ValueError):
            _parse_byte_value("100Ti")

    def test_invalid_type(self):
        with self.assertRaises(ValueError):
            _parse_byte_value([100])

    def test_float_passthrough(self):
        self.assertEqual(_parse_byte_value(1048576.7), 1048576)


class TestParseDurationValue(unittest.TestCase):
    """Tests for _parse_duration_value — time unit parsing.

    Supported suffixes: s (seconds), m (minutes x60), h (hours x3600)
    """

    def test_plain_int(self):
        self.assertEqual(_parse_duration_value(120), 120)

    def test_string_no_suffix(self):
        self.assertEqual(_parse_duration_value("120"), 120)

    def test_seconds_suffix(self):
        self.assertEqual(_parse_duration_value("30s"), 30)

    def test_minutes_suffix(self):
        self.assertEqual(_parse_duration_value("2m"), 120)

    def test_hours_suffix(self):
        self.assertEqual(_parse_duration_value("1h"), 3600)

    def test_fractional_minutes(self):
        self.assertEqual(_parse_duration_value("1.5m"), 90)

    def test_whitespace_handling(self):
        self.assertEqual(_parse_duration_value(" 5m "), 300)

    def test_invalid_suffix(self):
        with self.assertRaises(ValueError):
            _parse_duration_value("10d")

    def test_invalid_type(self):
        with self.assertRaises(ValueError):
            _parse_duration_value([60])

    def test_float_passthrough(self):
        self.assertEqual(_parse_duration_value(60.9), 60)


class TestStorageThrottleScenarioPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = StorageThrottleScenarioPlugin()

    def tearDown(self):
        self.plugin = None

    def test_get_scenario_types(self):
        result = self.plugin.get_scenario_types()
        self.assertEqual(result, ["storage_throttle_scenarios"])
        self.assertEqual(len(result), 1)


class TestResolveTargetPod(unittest.TestCase):

    def setUp(self):
        self.plugin = StorageThrottleScenarioPlugin()

    def tearDown(self):
        self.plugin = None

    def test_resolve_by_pod_name(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        result = self.plugin._resolve_pod_name(
            mock_k8s, "", "my-pod", "default"
        )
        self.assertEqual(result, "my-pod")
        mock_k8s.get_pvc_info.assert_not_called()

    def test_resolve_by_pvc_name(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_pvc = MagicMock()
        mock_pvc.podNames = ["pvc-pod-1", "pvc-pod-2"]
        mock_k8s.get_pvc_info.return_value = mock_pvc

        result = self.plugin._resolve_pod_name(
            mock_k8s, "my-pvc", "", "default"
        )
        self.assertIn(result, ["pvc-pod-1", "pvc-pod-2"])

    def test_resolve_pvc_no_pods(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_pvc = MagicMock()
        mock_pvc.podNames = []
        mock_k8s.get_pvc_info.return_value = mock_pvc

        result = self.plugin._resolve_pod_name(
            mock_k8s, "my-pvc", "", "default"
        )
        self.assertEqual(result, "")

    def test_resolve_pvc_overrides_pod_name(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_pvc = MagicMock()
        mock_pvc.podNames = ["from-pvc"]
        mock_k8s.get_pvc_info.return_value = mock_pvc

        result = self.plugin._resolve_pod_name(
            mock_k8s, "my-pvc", "ignored-pod", "default"
        )
        self.assertEqual(result, "from-pvc")

    def test_resolve_pvc_not_found(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.get_pvc_info.return_value = None

        result = self.plugin._resolve_pod_name(
            mock_k8s, "missing-pvc", "", "default"
        )
        self.assertEqual(result, "")


class TestFindPvcMount(unittest.TestCase):

    def test_find_mount_success(self):
        mock_pod = MagicMock()
        mock_volume = MagicMock()
        mock_volume.pvcName = "test-pvc"
        mock_volume.name = "vol1"
        mock_pod.volumes = [mock_volume]

        mock_container = MagicMock()
        mock_container.name = "app"
        mock_vol_mount = MagicMock()
        mock_vol_mount.name = "vol1"
        mock_vol_mount.mountPath = "/data"
        mock_container.volumeMounts = [mock_vol_mount]
        mock_pod.containers = [mock_container]

        container, path = StorageThrottleScenarioPlugin._find_pvc_mount(
            mock_pod, ""
        )
        self.assertEqual(container, "app")
        self.assertEqual(path, "/data")

    def test_find_mount_specific_path(self):
        mock_pod = MagicMock()
        mock_volume = MagicMock()
        mock_volume.pvcName = "test-pvc"
        mock_volume.name = "vol1"
        mock_pod.volumes = [mock_volume]

        mock_container = MagicMock()
        mock_container.name = "app"
        mock_mount1 = MagicMock()
        mock_mount1.name = "vol1"
        mock_mount1.mountPath = "/data"
        mock_mount2 = MagicMock()
        mock_mount2.name = "other-vol"
        mock_mount2.mountPath = "/logs"
        mock_container.volumeMounts = [mock_mount2, mock_mount1]
        mock_pod.containers = [mock_container]

        container, path = StorageThrottleScenarioPlugin._find_pvc_mount(
            mock_pod, "/data"
        )
        self.assertEqual(container, "app")
        self.assertEqual(path, "/data")

    def test_find_mount_no_pvc(self):
        mock_pod = MagicMock()
        mock_volume = MagicMock()
        mock_volume.pvcName = None
        mock_pod.volumes = [mock_volume]

        container, path = StorageThrottleScenarioPlugin._find_pvc_mount(
            mock_pod, ""
        )
        self.assertIsNone(container)
        self.assertIsNone(path)

    def test_find_mount_filters_by_pvc_name(self):
        """With multiple PVCs, only the requested pvc_name is selected."""
        mock_pod = MagicMock()

        vol_logs = MagicMock()
        vol_logs.pvcName = "logs-pvc"
        vol_logs.name = "logs-vol"

        vol_data = MagicMock()
        vol_data.pvcName = "data-pvc"
        vol_data.name = "data-vol"

        mock_pod.volumes = [vol_logs, vol_data]

        mount_logs = MagicMock()
        mount_logs.name = "logs-vol"
        mount_logs.mountPath = "/logs"

        mount_data = MagicMock()
        mount_data.name = "data-vol"
        mount_data.mountPath = "/data"

        mock_container = MagicMock()
        mock_container.name = "app"
        mock_container.volumeMounts = [mount_logs, mount_data]
        mock_pod.containers = [mock_container]

        container, path = StorageThrottleScenarioPlugin._find_pvc_mount(
            mock_pod, "", "data-pvc"
        )
        self.assertEqual(container, "app")
        self.assertEqual(path, "/data")

    def test_find_mount_pvc_name_not_found(self):
        """Returns None when requested pvc_name doesn't match any volume."""
        mock_pod = MagicMock()
        vol = MagicMock()
        vol.pvcName = "other-pvc"
        vol.name = "vol1"
        mock_pod.volumes = [vol]

        mount = MagicMock()
        mount.name = "vol1"
        mount.mountPath = "/data"
        mock_container = MagicMock()
        mock_container.name = "app"
        mock_container.volumeMounts = [mount]
        mock_pod.containers = [mock_container]

        container, path = StorageThrottleScenarioPlugin._find_pvc_mount(
            mock_pod, "", "missing-pvc"
        )
        self.assertIsNone(container)
        self.assertIsNone(path)


class TestGetDeviceMajMin(unittest.TestCase):

    def test_success(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = "8:16\n"

        result = StorageThrottleScenarioPlugin._get_device_maj_min(
            mock_k8s, "pod", "ns", "container", "/data"
        )
        self.assertEqual(result, "8:16")

    def test_empty_output(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = ""

        result = StorageThrottleScenarioPlugin._get_device_maj_min(
            mock_k8s, "pod", "ns", "container", "/data"
        )
        self.assertEqual(result, "")

    def test_none_output(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = None

        result = StorageThrottleScenarioPlugin._get_device_maj_min(
            mock_k8s, "pod", "ns", "container", "/data"
        )
        self.assertEqual(result, "")

    def test_invalid_mount_path_rejected(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        result = StorageThrottleScenarioPlugin._get_device_maj_min(
            mock_k8s, "pod", "ns", "container", "/data/../etc"
        )
        self.assertEqual(result, "")
        mock_k8s.exec_cmd_in_pod.assert_not_called()


class TestGetContainerId(unittest.TestCase):

    def test_crio_container_id(self):
        mock_pod = MagicMock()
        mock_c = MagicMock()
        mock_c.name = "app"
        mock_c.containerId = "cri-o://abc123def456"
        mock_pod.containers = [mock_c]

        result = StorageThrottleScenarioPlugin._get_container_id(mock_pod, "app")
        self.assertEqual(result, "abc123def456")

    def test_containerd_container_id(self):
        mock_pod = MagicMock()
        mock_c = MagicMock()
        mock_c.name = "app"
        mock_c.containerId = "containerd://abc123def456"
        mock_pod.containers = [mock_c]

        result = StorageThrottleScenarioPlugin._get_container_id(mock_pod, "app")
        self.assertEqual(result, "abc123def456")

    def test_container_not_found(self):
        mock_pod = MagicMock()
        mock_c = MagicMock()
        mock_c.name = "other"
        mock_c.containerId = "cri-o://abc123"
        mock_pod.containers = [mock_c]

        result = StorageThrottleScenarioPlugin._get_container_id(mock_pod, "app")
        self.assertEqual(result, "")

    def test_empty_container_id(self):
        mock_pod = MagicMock()
        mock_c = MagicMock()
        mock_c.name = "app"
        mock_c.containerId = ""
        mock_pod.containers = [mock_c]

        result = StorageThrottleScenarioPlugin._get_container_id(mock_pod, "app")
        self.assertEqual(result, "")

    def test_pod_not_found(self):
        result = StorageThrottleScenarioPlugin._get_container_id(None, "app")
        self.assertEqual(result, "")

    def test_non_hex_container_id_rejected(self):
        mock_pod = MagicMock()
        mock_c = MagicMock()
        mock_c.name = "app"
        mock_c.containerId = "cri-o://UPPERCASE_NOT_HEX"
        mock_pod.containers = [mock_c]

        result = StorageThrottleScenarioPlugin._get_container_id(mock_pod, "app")
        self.assertEqual(result, "")

    def test_shell_injection_container_id_rejected(self):
        mock_pod = MagicMock()
        mock_c = MagicMock()
        mock_c.name = "app"
        mock_c.containerId = "cri-o://abc;rm -rf /"
        mock_pod.containers = [mock_c]

        result = StorageThrottleScenarioPlugin._get_container_id(mock_pod, "app")
        self.assertEqual(result, "")


class TestDetectCgroupVersion(unittest.TestCase):

    def setUp(self):
        self.plugin = StorageThrottleScenarioPlugin()

    def tearDown(self):
        self.plugin = None

    def test_cgroup_v2(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = "cgroup2fs\n"

        result = self.plugin._detect_cgroup_version(mock_k8s, "priv-pod", "default")
        self.assertEqual(result, "v2")

    def test_cgroup_v1(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = "tmpfs\n"

        result = self.plugin._detect_cgroup_version(mock_k8s, "priv-pod", "default")
        self.assertEqual(result, "v1")

    def test_cgroup_unknown(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = None

        result = self.plugin._detect_cgroup_version(mock_k8s, "priv-pod", "default")
        self.assertEqual(result, "v1")


class TestFindHostCgroupPath(unittest.TestCase):

    def setUp(self):
        self.plugin = StorageThrottleScenarioPlugin()

    def tearDown(self):
        self.plugin = None

    def test_cgroup_v2_scope_found(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = (
            "/sys/fs/cgroup/kubepods.slice/crio-abc123def456.scope\n"
        )

        result = self.plugin._find_host_cgroup_path(
            mock_k8s, "priv-pod", "abc123def456789", "v2", "default"
        )
        self.assertEqual(result, "/kubepods.slice/crio-abc123def456.scope")

    def test_cgroup_v2_dir_fallback(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.side_effect = [
            "",  # scope search returns nothing
            "/sys/fs/cgroup/kubepods/abc123def456\n",  # dir search
        ]

        result = self.plugin._find_host_cgroup_path(
            mock_k8s, "priv-pod", "abc123def456789", "v2", "default"
        )
        self.assertEqual(result, "/kubepods/abc123def456")

    def test_cgroup_v1(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = (
            "/sys/fs/cgroup/blkio/kubepods/abc123def456.scope\n"
        )

        result = self.plugin._find_host_cgroup_path(
            mock_k8s, "priv-pod", "abc123def456789", "v1", "default"
        )
        self.assertEqual(result, "/kubepods/abc123def456.scope")

    def test_not_found(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = ""

        result = self.plugin._find_host_cgroup_path(
            mock_k8s, "priv-pod", "abc123def456789", "v2", "default"
        )
        self.assertEqual(result, "")


class TestApplyRemoveThrottle(unittest.TestCase):

    def setUp(self):
        self.plugin = StorageThrottleScenarioPlugin()

    def tearDown(self):
        self.plugin = None

    def _make_params(self, **overrides):
        defaults = dict(
            pvc_name="", pod_name="app-pod", namespace="default",
            throttle_type="bandwidth", read_iops=100, write_iops=50,
            read_bps=1048576, write_bps=524288, duration=60,
            mount_path="", image="quay.io/krkn-chaos/krkn:tools",
        )
        defaults.update(overrides)
        return ThrottleParams(**defaults)

    def test_apply_throttle_v2_bandwidth(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = "8:16 rbps=1048576 wbps=524288"

        self.plugin._apply_throttle(
            mock_k8s, "priv-pod", "/kubepods/crio-abc.scope", "v2",
            "8:16", self._make_params(throttle_type="bandwidth"), "default",
        )

        calls = mock_k8s.exec_cmd_in_pod.call_args_list
        self.assertEqual(len(calls), 2)  # echo + cat
        echo_cmd = calls[0][0][0][3]
        self.assertIn("rbps=1048576", echo_cmd)
        self.assertIn("wbps=524288", echo_cmd)

    def test_apply_throttle_v2_iops(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = "8:16 riops=100 wiops=50"

        self.plugin._apply_throttle(
            mock_k8s, "priv-pod", "/kubepods/crio-abc.scope", "v2",
            "8:16", self._make_params(throttle_type="iops"), "default",
        )

        calls = mock_k8s.exec_cmd_in_pod.call_args_list
        echo_cmd = calls[0][0][0][3]
        self.assertIn("riops=100", echo_cmd)
        self.assertIn("wiops=50", echo_cmd)

    def test_apply_throttle_v2_both(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = ""

        self.plugin._apply_throttle(
            mock_k8s, "priv-pod", "/kubepods/crio-abc.scope", "v2",
            "8:16", self._make_params(throttle_type="both"), "default",
        )

        calls = mock_k8s.exec_cmd_in_pod.call_args_list
        echo_cmd = calls[0][0][0][3]
        self.assertIn("rbps=1048576", echo_cmd)
        self.assertIn("wiops=50", echo_cmd)

    def test_apply_throttle_v1_bandwidth(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = ""

        self.plugin._apply_throttle(
            mock_k8s, "priv-pod", "/kubepods/abc", "v1",
            "8:16", self._make_params(throttle_type="bandwidth"), "default",
        )

        calls = mock_k8s.exec_cmd_in_pod.call_args_list
        # 2 writes (read_bps, write_bps) + 4 cat verifications
        self.assertEqual(len(calls), 6)

    def test_remove_throttle_v2(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = ""

        self.plugin._remove_throttle(
            mock_k8s, "priv-pod", "/kubepods/crio-abc.scope", "v2", "8:16",
            "default",
        )

        calls = mock_k8s.exec_cmd_in_pod.call_args_list
        self.assertEqual(len(calls), 1)
        echo_cmd = calls[0][0][0][3]
        self.assertIn("rbps=max", echo_cmd)
        self.assertIn("wbps=max", echo_cmd)

    def test_remove_throttle_v1(self):
        mock_k8s = MagicMock(spec=KrknKubernetes)
        mock_k8s.exec_cmd_in_pod.return_value = ""

        self.plugin._remove_throttle(
            mock_k8s, "priv-pod", "/kubepods/abc", "v1", "8:16", "default",
        )

        calls = mock_k8s.exec_cmd_in_pod.call_args_list
        # 4 writes (one for each blkio file)
        self.assertEqual(len(calls), 4)


class TestRunScenario(unittest.TestCase):

    def setUp(self):
        self.plugin = StorageThrottleScenarioPlugin()

    def tearDown(self):
        self.plugin = None

    def create_scenario_file(self, config: dict, temp_dir: str) -> str:
        path = os.path.join(temp_dir, "scenario.yaml")
        with open(path, "w") as f:
            yaml.dump(config, f)
        return path

    def test_run_missing_namespace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "pvc_name": "test-pvc",
                }
            }
            path = self.create_scenario_file(config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)

    def test_run_missing_pvc_and_pod(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                }
            }
            path = self.create_scenario_file(config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)

    def test_run_invalid_throttle_type(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "test-pod",
                    "throttle_type": "invalid",
                }
            }
            path = self.create_scenario_file(config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)

    def test_run_pod_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "nonexistent",
                    "throttle_type": "bandwidth",
                }
            }
            path = self.create_scenario_file(config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_k8s = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_k8s
            mock_k8s.get_pod_info.return_value = None
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)

    def test_run_scenario_file_not_found(self):
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_st = MagicMock()

        result = self.plugin.run(
            run_uuid="uuid", scenario="/nonexistent/path.yaml",
            lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
        )
        self.assertEqual(result, 1)

    def test_run_invalid_config_mount_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "test-pod",
                    "mount_path": "/bad path",
                    "throttle_type": "bandwidth",
                }
            }
            path = self.create_scenario_file(config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)
            mock_telemetry.get_lib_kubernetes.assert_not_called()

    def test_run_zero_duration_rejected(self):
        """run() returns 1 when duration is zero."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "test-pod",
                    "throttle_type": "bandwidth",
                    "duration": 0,
                }
            }
            path = self.create_scenario_file(config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)
            mock_telemetry.get_lib_kubernetes.assert_not_called()

    def test_run_negative_iops_rejected(self):
        """run() returns 1 when an IOPS value is negative."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "test-pod",
                    "throttle_type": "iops",
                    "read_iops": -10,
                }
            }
            path = self.create_scenario_file(config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)
            mock_telemetry.get_lib_kubernetes.assert_not_called()

    def test_run_invalid_byte_suffix_rejected(self):
        """run() returns 1 with clean error when byte value has invalid suffix."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "test-pod",
                    "throttle_type": "bandwidth",
                    "read_bps": "10Ti",
                }
            }
            path = self.create_scenario_file(config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)
            mock_telemetry.get_lib_kubernetes.assert_not_called()

    def test_run_invalid_duration_suffix_rejected(self):
        """run() returns 1 with clean error when duration has invalid suffix."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "test-pod",
                    "throttle_type": "bandwidth",
                    "duration": "10d",
                }
            }
            path = self.create_scenario_file(config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)
            mock_telemetry.get_lib_kubernetes.assert_not_called()

    def test_run_invalid_maj_min_from_mountinfo(self):
        """run() returns 1 when /proc/self/mountinfo returns invalid major:minor."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "app-pod",
                    "throttle_type": "bandwidth",
                }
            }
            path = self.create_scenario_file(config, temp_dir)

            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "pvc1"
            mock_volume.name = "vol1"
            mock_pod.volumes = [mock_volume]

            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "vol1"
            mock_vol_mount.mountPath = "/data"

            mock_container = MagicMock()
            mock_container.name = "app"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_k8s = MagicMock(spec=KrknKubernetes)
            mock_telemetry.get_lib_kubernetes.return_value = mock_k8s
            mock_k8s.get_pod_info.return_value = mock_pod

            mock_k8s.exec_cmd_in_pod.return_value = "BADVALUE\n"
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)

    def test_run_cgroup_path_not_found(self):
        """run() returns 1 and cleans up when cgroup path discovery fails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "app-pod",
                    "throttle_type": "bandwidth",
                }
            }
            path = self.create_scenario_file(config, temp_dir)

            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "pvc1"
            mock_volume.name = "vol1"
            mock_pod.volumes = [mock_volume]

            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "vol1"
            mock_vol_mount.mountPath = "/data"

            mock_container = MagicMock()
            mock_container.name = "app"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_container.containerId = "cri-o://abc123def4567890123456789012"
            mock_pod.containers = [mock_container]
            mock_pod.nodeName = "worker-1"

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_k8s = MagicMock(spec=KrknKubernetes)
            mock_telemetry.get_lib_kubernetes.return_value = mock_k8s
            mock_k8s.get_pod_info.return_value = mock_pod

            mock_k8s.deploy_io_throttle_pod.return_value = "io-throttle-12345"
            mock_k8s.exec_cmd_in_pod.side_effect = [
                "8:16\n",       # _get_device_maj_min
                "cgroup2fs\n",  # _detect_cgroup_version
                "",             # _find_host_cgroup_path scope search
                "",             # _find_host_cgroup_path dir fallback
            ]
            mock_st = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )
            self.assertEqual(result, 1)
            mock_k8s.deploy_io_throttle_pod.assert_called_once()
            mock_k8s.delete_pod.assert_called_once()

    @patch(
        "krkn.scenario_plugins.storage_throttle."
        "storage_throttle_scenario_plugin.time.sleep"
    )
    def test_run_happy_path(self, mock_sleep):
        """Full success path through run() with mocks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "app-pod",
                    "throttle_type": "bandwidth",
                    "duration": 45,
                }
            }
            path = self.create_scenario_file(config, temp_dir)

            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "pvc1"
            mock_volume.name = "vol1"
            mock_pod.volumes = [mock_volume]

            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "vol1"
            mock_vol_mount.mountPath = "/data"

            mock_container = MagicMock()
            mock_container.name = "app"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_container.containerId = "cri-o://abc123def4567890123456789012"
            mock_pod.containers = [mock_container]
            mock_pod.nodeName = "worker-1"

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_k8s = MagicMock(spec=KrknKubernetes)
            mock_telemetry.get_lib_kubernetes.return_value = mock_k8s
            mock_k8s.get_pod_info.return_value = mock_pod

            mock_k8s.deploy_io_throttle_pod.return_value = "io-throttle-12345"
            mock_k8s.exec_cmd_in_pod.side_effect = [
                "8:16\n",
                "cgroup2fs\n",
                "/sys/fs/cgroup/kubepods.slice/crio-abc.scope\n",
                "",
                "8:16 rbps=1048576 wbps=524288\n",
                "",
            ]
            mock_st = MagicMock()

            # Avoid RollbackHandler persisting to disk during unit tests
            self.plugin.rollback_handler.set_rollback_callable = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )

            self.assertEqual(result, 0)
            mock_k8s.deploy_io_throttle_pod.assert_called_once()
            mock_k8s.create_pod.assert_not_called()
            mock_k8s.delete_pod.assert_called_once()
            self.assertEqual(mock_k8s.exec_cmd_in_pod.call_count, 6)
            self.assertEqual(mock_sleep.call_count, 2)


    @patch(
        "krkn.scenario_plugins.storage_throttle."
        "storage_throttle_scenario_plugin.time.sleep"
    )
    def test_run_removes_throttle_on_wait_failure(self, mock_sleep):
        """Throttle is removed even when _wait_with_progress raises."""
        mock_sleep.side_effect = RuntimeError("simulated failure")

        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "storage_throttle_scenario": {
                    "namespace": "default",
                    "pod_name": "app-pod",
                    "throttle_type": "bandwidth",
                    "duration": 60,
                }
            }
            path = self.create_scenario_file(config, temp_dir)

            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "pvc1"
            mock_volume.name = "vol1"
            mock_pod.volumes = [mock_volume]

            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "vol1"
            mock_vol_mount.mountPath = "/data"

            mock_container = MagicMock()
            mock_container.name = "app"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_container.containerId = "cri-o://abc123def4567890123456789012"
            mock_pod.containers = [mock_container]
            mock_pod.nodeName = "worker-1"

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_k8s = MagicMock(spec=KrknKubernetes)
            mock_telemetry.get_lib_kubernetes.return_value = mock_k8s
            mock_k8s.get_pod_info.return_value = mock_pod

            mock_k8s.deploy_io_throttle_pod.return_value = "io-throttle-12345"
            mock_k8s.exec_cmd_in_pod.side_effect = [
                "8:16\n",       # _get_device_maj_min
                "cgroup2fs\n",  # _detect_cgroup_version
                "/sys/fs/cgroup/kubepods.slice/crio-abc.scope\n",  # scope
                "",             # _apply_throttle echo
                "8:16 rbps=1048576 wbps=524288\n",  # _apply_throttle cat
                "",             # _remove_throttle (in finally cleanup)
            ]
            mock_st = MagicMock()
            self.plugin.rollback_handler.set_rollback_callable = MagicMock()

            result = self.plugin.run(
                run_uuid="uuid", scenario=path,
                lib_telemetry=mock_telemetry, scenario_telemetry=mock_st,
            )

            self.assertEqual(result, 1)
            mock_k8s.deploy_io_throttle_pod.assert_called_once()
            mock_k8s.delete_pod.assert_called_once()
            # 6 exec calls: maj_min, cgroup_ver, cgroup_path, apply echo, apply cat, remove in finally
            self.assertEqual(mock_k8s.exec_cmd_in_pod.call_count, 6)


class TestRollbackThrottle(unittest.TestCase):

    def test_rollback_success_v2_stored_cgroup(self):
        """Rollback uses stored cgroup_path (single chroot exec for v2 reset)."""
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_k8s = MagicMock()
        mock_telemetry.get_lib_kubernetes.return_value = mock_k8s
        mock_k8s.exec_cmd_in_pod.return_value = ""

        rollback_data = {
            "priv_pod_name": "io-throttle-12345",
            "maj_min": "8:16",
            "cgroup_path": "/kubepods.slice/crio-abc123.scope",
            "cgroup_version": "v2",
        }
        encoded = base64.b64encode(
            json.dumps(rollback_data).encode("utf-8")
        ).decode("utf-8")

        content = RollbackContent(
            namespace="default", resource_identifier=encoded
        )

        StorageThrottleScenarioPlugin.rollback_throttle(
            content, mock_telemetry
        )

        mock_k8s.exec_cmd_in_pod.assert_called_once()
        mock_k8s.delete_pod.assert_called_once_with(
            "io-throttle-12345", "default"
        )

    def test_rollback_missing_cgroup_data_still_deletes_pod(self):
        """Rollback without cgroup_path logs a warning but still deletes the pod."""
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_k8s = MagicMock()
        mock_telemetry.get_lib_kubernetes.return_value = mock_k8s

        rollback_data = {
            "priv_pod_name": "io-throttle-12345",
            "maj_min": "8:16",
        }
        encoded = base64.b64encode(
            json.dumps(rollback_data).encode("utf-8")
        ).decode("utf-8")

        content = RollbackContent(
            namespace="default", resource_identifier=encoded
        )

        StorageThrottleScenarioPlugin.rollback_throttle(
            content, mock_telemetry
        )

        mock_k8s.exec_cmd_in_pod.assert_not_called()
        mock_k8s.delete_pod.assert_called_once_with(
            "io-throttle-12345", "default"
        )

    @patch(
        "krkn.scenario_plugins.storage_throttle."
        "storage_throttle_scenario_plugin.logging"
    )
    def test_rollback_invalid_data(self, mock_logging):
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)

        content = RollbackContent(
            namespace="default", resource_identifier="bad-data!!!"
        )

        StorageThrottleScenarioPlugin.rollback_throttle(
            content, mock_telemetry
        )

        mock_logging.error.assert_called_once()
        error_msg = mock_logging.error.call_args[0][0]
        self.assertIn("Failed to rollback", error_msg)


if __name__ == "__main__":
    unittest.main()
