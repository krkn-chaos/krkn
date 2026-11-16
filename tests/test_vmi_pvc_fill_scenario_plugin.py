#!/usr/bin/env python3

"""Tests for the guest-level VMI storage scenario."""

import io
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

    def test_parse_config_defaults_missing_or_blank_fill_percentage(self):
        for value in ("missing", None, "", "   "):
            with self.subTest(value=value):
                values = self.config["vmi_pvc_fill_scenario"]
                if value == "missing":
                    values.pop("fill_percentage", None)
                else:
                    values["fill_percentage"] = value
                params = self.plugin._parse_config(self._scenario_file())
                self.assertEqual(params.fill_percentage, 50)

    def test_parse_config_accepts_quoted_fill_percentage(self):
        self.config["vmi_pvc_fill_scenario"]["fill_percentage"] = "75"
        params = self.plugin._parse_config(self._scenario_file())
        self.assertEqual(params.fill_percentage, 75)

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

    @patch("krkn.scenario_plugins.vmi_pvc_fill.vmi_pvc_fill_scenario_plugin.subprocess.Popen")
    def test_virtctl_command_uses_vmi_and_namespace(self, mock_popen):
        params = self.plugin._parse_config(self._scenario_file())
        mock_popen.return_value = MagicMock(
            returncode=0,
            stdin=MagicMock(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        _run_virtctl(params, "true", timeout=30)

        args = mock_popen.call_args.args[0]
        self.assertIn("root@vmi/vm1", args)
        self.assertIn("--namespace", args)
        self.assertIn("default", args)
        self.assertIn("--local-ssh-opts=-o StrictHostKeyChecking=no", args)
        self.assertIn("--local-ssh-opts=-o UserKnownHostsFile=/dev/null", args)
        self.assertIn("--local-ssh-opts=-o BatchMode=yes", args)
        self.assertIn("--local-ssh-opts=-o PasswordAuthentication=no", args)
        self.assertIn("--command", args)
        self.assertIn("true", args)

    @patch("krkn.scenario_plugins.vmi_pvc_fill.vmi_pvc_fill_scenario_plugin.subprocess.Popen")
    def test_virtctl_error_omits_informational_ssh_warnings(self, mock_popen):
        params = self.plugin._parse_config(self._scenario_file())
        mock_popen.return_value = MagicMock(
            returncode=255,
            stdin=MagicMock(),
            stdout=io.StringIO(),
            stderr=io.StringIO(
                "Warning: Permanently added 'vmi' to known hosts.\n"
                "WARNING: connection is not using a post-quantum key exchange algorithm.\n"
                "Permission denied (publickey,password).\n"
                "exit status 255"
            ),
        )

        with self.assertRaises(RuntimeError) as context:
            _run_virtctl(params, "true", timeout=30)

        message = str(context.exception)
        self.assertIn("Permission denied", message)
        self.assertIn("exit status 255", message)
        self.assertNotIn("Permanently added", message)
        self.assertNotIn("post-quantum", message)

    @patch("krkn.scenario_plugins.vmi_pvc_fill.vmi_pvc_fill_scenario_plugin._run_virtctl")
    def test_run_returns_success(self, mock_virtctl):
        lib_k8s = MagicMock()
        lib_k8s.get_kubeconfig_path.return_value = "/tmp/test-kubeconfig"
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
        self.assertEqual(mock_virtctl.call_count, 2)

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
    def test_filesystem_fill_rollback_loads_and_removes_the_file(self, mock_fill):
        """The rollback registered for a filesystem fill must survive the
        version file round trip and remove the fill file (#1682)."""
        import os
        import shutil
        from krkn.rollback.handler import _parse_rollback_module
        from krkn.rollback.serialization import Serializer

        self.config["vmi_pvc_fill_scenario"].update({
            "pvc_name": "filesystem-pvc",
            "device_path": "",
        })
        fill_data = {
            "pod_name": "virt-launcher-vm1",
            "namespace": "default",
            "container_name": "app",
            "mount_path": "/data",
            "file_name": "kraken.tmp",
            "full_path": "/data/kraken.tmp",
        }

        def fill(*args, on_file_created=None, **kwargs):
            on_file_created(fill_data)
            return 1, None

        mock_fill.side_effect = fill
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
        self.plugin.rollback_handler = MagicMock()

        self.plugin.run("run-id", self._scenario_file(), telemetry, MagicMock())

        self.plugin.rollback_handler.set_rollback_callable.assert_called_once()
        callable_, content = (
            self.plugin.rollback_handler.set_rollback_callable.call_args.args
        )

        # Write and load the version file the way RollbackHandler does.
        serializer = Serializer("vmi_pvc_fill_scenarios")
        name, code = serializer._parse_rollback_callable_code(callable_)
        text = serializer.template.render(
            rollback_callable_name=name,
            rollback_callable_code=code,
            rollback_content=str(content),
        )
        version_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, version_dir, ignore_errors=True)
        version_file = os.path.join(version_dir, "version.py")
        with open(version_file, "w") as handle:
            handle.write(text)
        loaded_callable, loaded_content = _parse_rollback_module(version_file)

        rollback_k8s = MagicMock()
        rollback_k8s.exec_cmd_in_pod.return_value = ""
        rollback_telemetry = MagicMock()
        rollback_telemetry.get_lib_kubernetes.return_value = rollback_k8s
        loaded_callable(loaded_content, rollback_telemetry)

        rollback_k8s.exec_cmd_in_pod.assert_any_call(
            ["rm -f /data/kraken.tmp"], "virt-launcher-vm1", "default", "app"
        )

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
