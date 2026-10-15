#!/usr/bin/env python3

"""Tests for the guest-level VMI storage scenario."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from krkn.scenario_plugins.vmi_pvc_fill.vmi_pvc_fill_scenario_plugin import (
    VmiPvcFillScenarioPlugin,
    _run_virtctl,
)


class TestVmiPvcFillScenarioPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = VmiPvcFillScenarioPlugin()
        self.config = {
            "vmi_pvc_fill_scenario": {
                "vmi_name": "vm1",
                "namespace": "default",
                "device_path": "/dev/vdb",
                "mount_path": "/mnt/data",
                "format_device": True,
                "fill_percentage": 75,
                "duration": 10,
                "pvc_name": "vm-disk",
            }
        }

    def _scenario_file(self):
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        self.addCleanup(Path(handle.name).unlink)
        yaml.safe_dump(self.config, handle)
        handle.close()
        return handle.name

    def test_get_scenario_types(self):
        self.assertEqual(self.plugin.get_scenario_types(), ["vmi_pvc_fill_scenarios"])

    def test_parse_config_requires_safe_target_values(self):
        params = self.plugin._parse_config(self._scenario_file())
        self.assertEqual(params.vmi_name, "vm1")
        self.assertTrue(params.format_device)

        self.config["vmi_pvc_fill_scenario"]["device_path"] = "/dev/vda;rm"
        with self.assertRaises(ValueError):
            self.plugin._parse_config(self._scenario_file())

    def test_run_returns_failure_for_invalid_configuration(self):
        self.config["vmi_pvc_fill_scenario"]["vmi_name"] = ""
        self.config["vmi_pvc_fill_scenario"]["pvc_name"] = ""

        result = self.plugin.run(
            "run-id", self._scenario_file(), MagicMock(), MagicMock()
        )

        self.assertEqual(result, 1)

    def test_run_returns_failure_when_vmi_cannot_be_resolved(self):
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value.get_vmi.return_value = None

        result = self.plugin.run(
            "run-id", self._scenario_file(), telemetry, MagicMock()
        )

        self.assertEqual(result, 1)

    def test_guest_command_formats_fills_and_cleans_up(self):
        params = self.plugin._parse_config(self._scenario_file())
        command = self.plugin._guest_command(params)
        self.assertIn("mkfs -t ext4", command)
        self.assertIn("fallocate", command)
        self.assertIn("sleep 10", command)
        self.assertIn("trap cleanup EXIT", command)
        self.assertIn('belongs to $mounted_source, not $device', command)
        self.assertIn('filesystem is already at or above', command)
        self.assertIn('bs=1M count="$full_blocks"', command)

    @patch("krkn.scenario_plugins.vmi_pvc_fill.vmi_pvc_fill_scenario_plugin.subprocess.run")
    def test_virtctl_command_uses_vmi_and_namespace(self, mock_run):
        params = self.plugin._parse_config(self._scenario_file())
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        _run_virtctl(params, "true", timeout=30)

        args = mock_run.call_args.args[0]
        self.assertIn("root@vmi/vm1", args)
        self.assertIn("--namespace", args)
        self.assertIn("default", args)
        self.assertIn("--command", args)
        self.assertIn("true", args)

    @patch("krkn.scenario_plugins.vmi_pvc_fill.vmi_pvc_fill_scenario_plugin._run_virtctl")
    def test_run_returns_success(self, mock_virtctl):
        lib_k8s = MagicMock()
        lib_k8s.get_vmi.return_value = {
            "status": {"phase": "Running", "nodeName": "worker-1"}
        }
        lib_k8s.list_pods.return_value = ["virt-launcher-vm1"]
        lib_k8s.cli.read_namespaced_pod.return_value = {
            "metadata": {"uid": "uid-vm1"},
            "status": {"phase": "Running"},
            "spec": {
                "nodeName": "worker-1",
                "volumes": [{
                    "name": "disk",
                    "persistentVolumeClaim": {"claimName": "vm-disk"},
                }],
                "containers": [{
                    "name": "compute",
                    "volumeDevices": [{
                        "name": "disk",
                        "devicePath": "/dev/vdb",
                    }],
                }],
            },
        }
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value = lib_k8s

        result = self.plugin.run(
            "run-id", self._scenario_file(), telemetry, MagicMock()
        )
        self.assertEqual(result, 0)
        mock_virtctl.assert_called_once()

    @patch("krkn.scenario_plugins.vmi_pvc_fill.vmi_pvc_fill_scenario_plugin.fill_filesystem_pvc")
    def test_filesystem_pvc_uses_shared_filesystem_service(self, mock_fill):
        self.config["vmi_pvc_fill_scenario"].update({
            "pvc_name": "filesystem-pvc",
            "device_path": "",
        })
        mock_fill.return_value = (0, {})
        lib_k8s = MagicMock()
        lib_k8s.get_vmi.return_value = {
            "status": {"phase": "Running", "nodeName": "worker-1"}
        }
        lib_k8s.list_pods.return_value = ["virt-launcher-vm1"]
        lib_k8s.cli.read_namespaced_pod.return_value = {
            "metadata": {"uid": "uid-vm1"},
            "status": {"phase": "Running"},
            "spec": {
                "nodeName": "worker-1",
                "volumes": [{
                    "name": "disk",
                    "persistentVolumeClaim": {"claimName": "filesystem-pvc"},
                }],
                "containers": [{
                    "name": "app",
                    "volumeMounts": [{"name": "disk", "mountPath": "/data"}],
                }],
            },
        }
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value = lib_k8s

        result = self.plugin.run(
            "run-id", self._scenario_file(), telemetry, MagicMock()
        )

        self.assertEqual(result, 0)
        mock_fill.assert_called_once()

    @patch("krkn.scenario_plugins.vmi_pvc_fill.vmi_pvc_fill_scenario_plugin.fill_filesystem_pvc")
    def test_run_returns_failure_when_filesystem_fill_fails(self, mock_fill):
        self.config["vmi_pvc_fill_scenario"].update({
            "pvc_name": "filesystem-pvc",
            "device_path": "",
        })
        mock_fill.return_value = (1, None)
        lib_k8s = MagicMock()
        lib_k8s.get_vmi.return_value = {
            "status": {"phase": "Running", "nodeName": "worker-1"}
        }
        lib_k8s.list_pods.return_value = ["virt-launcher-vm1"]
        lib_k8s.cli.read_namespaced_pod.return_value = {
            "metadata": {"uid": "uid-vm1"},
            "status": {"phase": "Running"},
            "spec": {
                "nodeName": "worker-1",
                "volumes": [{
                    "name": "disk",
                    "persistentVolumeClaim": {"claimName": "filesystem-pvc"},
                }],
                "containers": [{
                    "name": "app",
                    "volumeMounts": [{"name": "disk", "mountPath": "/data"}],
                }],
            },
        }
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value = lib_k8s

        result = self.plugin.run(
            "run-id", self._scenario_file(), telemetry, MagicMock()
        )

        self.assertEqual(result, 1)

    @patch("krkn.scenario_plugins.vmi_pvc_fill.vmi_pvc_fill_scenario_plugin._run_virtctl")
    def test_run_returns_failure_when_guest_command_fails(self, mock_virtctl):
        mock_virtctl.side_effect = RuntimeError("guest command failed")
        lib_k8s = MagicMock()
        lib_k8s.get_vmi.return_value = {
            "status": {"phase": "Running", "nodeName": "worker-1"}
        }
        lib_k8s.list_pods.return_value = ["virt-launcher-vm1"]
        lib_k8s.cli.read_namespaced_pod.return_value = {
            "metadata": {"uid": "uid-vm1"},
            "status": {"phase": "Running"},
            "spec": {
                "nodeName": "worker-1",
                "volumes": [{
                    "name": "disk",
                    "persistentVolumeClaim": {"claimName": "vm-disk"},
                }],
                "containers": [{
                    "name": "compute",
                    "volumeDevices": [{
                        "name": "disk",
                        "devicePath": "/dev/vdb",
                    }],
                }],
            },
        }
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value = lib_k8s

        result = self.plugin.run(
            "run-id", self._scenario_file(), telemetry, MagicMock()
        )

        self.assertEqual(result, 1)

    @patch("krkn.scenario_plugins.vmi_pvc_fill.vmi_pvc_fill_scenario_plugin._run_virtctl")
    def test_block_fill_requires_guest_device_path(self, mock_virtctl):
        self.config["vmi_pvc_fill_scenario"]["device_path"] = ""
        lib_k8s = MagicMock()
        lib_k8s.get_vmi.return_value = {
            "status": {"phase": "Running", "nodeName": "worker-1"}
        }
        lib_k8s.list_pods.return_value = ["virt-launcher-vm1"]
        lib_k8s.cli.read_namespaced_pod.return_value = {
            "metadata": {"uid": "uid-vm1"},
            "status": {"phase": "Running"},
            "spec": {
                "nodeName": "worker-1",
                "volumes": [{
                    "name": "disk",
                    "persistentVolumeClaim": {"claimName": "vm-disk"},
                }],
                "containers": [{
                    "name": "compute",
                    "volumeDevices": [{
                        "name": "disk",
                        "devicePath": "/dev/vda",
                    }],
                }],
            },
        }
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value = lib_k8s

        result = self.plugin.run(
            "run-id", self._scenario_file(), telemetry, MagicMock()
        )

        self.assertEqual(result, 1)
        mock_virtctl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
