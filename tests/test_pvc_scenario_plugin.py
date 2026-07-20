#!/usr/bin/env python3

"""
Test suite for PvcScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_pvc_scenario_plugin.py -v

Assisted By: Claude Code
"""

import base64
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch
import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.pvc.pvc_scenario_plugin import (
    PvcScenarioPlugin,
    _parse_fill_percentage,
)
from krkn.rollback.config import RollbackContent
from krkn.utils.filesystem_pvc import encode_rollback_data


class TestPvcScenarioPlugin(unittest.TestCase):
    """Unit tests for PvcScenarioPlugin class"""

    def setUp(self):
        """
        Set up test fixtures for PvcScenarioPlugin
        """
        self.plugin = PvcScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pvc_scenarios"])
        self.assertEqual(len(result), 1)

    def test_parse_fill_percentage_defaults_missing_or_blank_values(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertEqual(_parse_fill_percentage(value), 50.0)

    def test_parse_fill_percentage_accepts_quoted_numeric_value(self):
        self.assertEqual(_parse_fill_percentage("50"), 50.0)

class TestRollbackTempFile(unittest.TestCase):
    """Tests for the rollback_temp_file static method"""

    def test_rollback_temp_file_success(self):
        """Test successful rollback removes temp file"""
        # Create mock telemetry
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_kubecli = MagicMock()
        mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli
        
        # Simulate successful file removal
        mock_kubecli.exec_cmd_in_pod.side_effect = [
            "",  # rm -f command output
            "total 0\ndrwxr-xr-x 2 root root 40 Jan 1 00:00 .",  # ls -lh output without file
        ]

        # Create rollback data
        rollback_data = {
            "pod_name": "test-pod",
            "namespace": "test-ns",
            "container_name": "test-container",
            "full_path": "/mnt/data/kraken.tmp",
            "file_name": "kraken.tmp",
            "mount_path": "/mnt/data",
        }
        encoded_data = encode_rollback_data(rollback_data)

        rollback_content = RollbackContent(
            namespace="test-ns",
            resource_identifier=encoded_data,
        )

        # Should not raise any exception
        PvcScenarioPlugin.rollback_temp_file(rollback_content, mock_telemetry)

        # Verify exec_cmd_in_pod was called
        self.assertEqual(mock_kubecli.exec_cmd_in_pod.call_count, 2)  

    @patch("krkn.utils.filesystem_pvc.logging")
    def test_rollback_temp_file_invalid_data(self, mock_logging):
        """Test rollback handles invalid encoded data gracefully and logs error"""
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)

        rollback_content = RollbackContent(
            namespace="test-ns",
            resource_identifier="invalid-base64-data!!!",
        )

        # Should not raise exception, just log the error
        PvcScenarioPlugin.rollback_temp_file(rollback_content, mock_telemetry)

        # Verify error was logged to inform users of rollback failure
        mock_logging.error.assert_called_once()
        error_message = mock_logging.error.call_args[0][0]
        self.assertIn("Failed to rollback filesystem PVC fill", error_message)


class TestPvcScenarioPluginRun(unittest.TestCase):
    """Tests for the run method of PvcScenarioPlugin"""

    def setUp(self):
        """Set up test fixtures"""
        self.plugin = PvcScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def create_scenario_file(self, config: dict, temp_dir: str) -> str:
        """Helper to create a temporary scenario YAML file in the given directory"""
        path = os.path.join(temp_dir, "scenario.yaml")
        with open(path, "w") as f:
            yaml.dump(config, f)
        return path

    def test_run_missing_namespace(self):
        """Test run returns 1 when namespace is missing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "pvc_name": "test-pvc",
                    # namespace is missing
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            assert result == 1

    def test_run_missing_pvc_and_pod_name(self):
        """Test run returns 1 when both pvc_name and pod_name are missing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    # pvc_name and pod_name are missing
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 1)

    def test_run_pod_not_found(self):
        """Test run returns 1 when pod doesn't exist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pod_name": "non-existent-pod",
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli
            mock_kubecli.get_pod_info.return_value = None
            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 1)

    def test_run_pvc_not_found_for_pod(self):
        """Test run returns 1 when pod has no PVC"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pod_name": "test-pod",
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            # Create mock pod with no PVC volumes
            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = None  # No PVC attached
            mock_pod.volumes = [mock_volume]
            mock_kubecli.get_pod_info.return_value = mock_pod

            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 1)

    def test_run_invalid_fill_percentage(self):
        """Test run returns 1 when target fill percentage is invalid"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pod_name": "test-pod",
                    "fill_percentage": 10,  # Lower than current usage
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            # Create mock pod with PVC volume
            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "test-pvc"
            mock_volume.name = "test-volume"
            mock_pod.volumes = [mock_volume]

            # Create mock container with volume mount
            mock_container = MagicMock()
            mock_container.name = "test-container"
            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "test-volume"
            mock_vol_mount.mountPath = "/mnt/data"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_kubecli.get_pod_info.return_value = mock_pod

            # Mock PVC info
            mock_pvc = MagicMock()
            mock_kubecli.get_pvc_info.return_value = mock_pvc

            # Mock df command output: 50% used (50000 used, 50000 available, 100000 total)
            mock_kubecli.exec_cmd_in_pod.return_value = (
                "/dev/sda1 100000 50000 50000 50% /mnt/data"
            )

            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            # Should return 1 because target fill (10%) < current fill (50%)
            self.assertEqual(result, 1)

    def test_run_rollback_registration_failure(self):
        """Test run returns 1 and does not create a file when rollback registration fails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pod_name": "test-pod",
                    "fill_percentage": 80,
                    "duration": 1,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli
            # Create mock pod with PVC volume
            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "test-pvc"
            mock_volume.name = "test-volume"
            mock_pod.volumes = [mock_volume]

            # Create mock container with volume mount
            mock_container = MagicMock()
            mock_container.name = "test-container"
            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "test-volume"
            mock_vol_mount.mountPath = "/mnt/data"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_kubecli.get_pod_info.return_value = mock_pod
            mock_kubecli.get_pvc_info.return_value = MagicMock()
            mock_kubecli.get_pod_shell.return_value = "bash"

            mock_kubecli.exec_cmd_in_pod.side_effect = [
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df
                "/usr/bin/fallocate",  # fallocate available
                "/usr/bin/dd",  # dd available
            ]

            with patch.object(
              self.plugin.rollback_handler,
              "set_rollback_callable",
              return_value=False,
           ) as mock_rollback:
              result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=MagicMock(),
              )
            # Scenario must abort when rollback registration fails
            self.assertEqual(result, 1)
            mock_rollback.assert_called_once()
            # Only df and the two binary checks should run.
            calls = mock_kubecli.exec_cmd_in_pod.call_args_list
            self.assertEqual(len(calls), 3)
            self.assertIn("df", calls[0].args[0][0])
            self.assertIn("command -v fallocate", calls[1].args[0][0])
            self.assertIn("command -v dd", calls[2].args[0][0])

    @patch("krkn.utils.filesystem_pvc.time.sleep")
    def test_run_success_with_fallocate(self, mock_sleep):
        """Test successful run using fallocate"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pod_name": "test-pod",
                    "fill_percentage": 80,
                    "duration": 1,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            # Create mock pod with PVC volume
            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "test-pvc"
            mock_volume.name = "test-volume"
            mock_pod.volumes = [mock_volume]

            # Create mock container with volume mount
            mock_container = MagicMock()
            mock_container.name = "test-container"
            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "test-volume"
            mock_vol_mount.mountPath = "/mnt/data"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_kubecli.get_pod_info.return_value = mock_pod

            # Mock PVC info
            mock_pvc = MagicMock()
            mock_kubecli.get_pvc_info.return_value = mock_pvc

            # Set up exec_cmd_in_pod responses
            mock_kubecli.exec_cmd_in_pod.side_effect = [
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df command (10% used)
                "/usr/bin/fallocate",  # command -v fallocate
                "/usr/bin/dd",  # command -v dd
                "",  # fallocate command
                "-rw-r--r-- 1 root root 70M Jan 1 00:00 kraken.tmp",  # ls -lh (file created)
                "71680000",  # wc -c
                "/dev/sda1 100000 80000 20000 80% /mnt/data",  # df after fill
                "",  # rm -f (cleanup)
                "total 0",  # ls -lh (file removed)
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df after cleanup
            ]

            mock_scenario_telemetry = MagicMock()
            
            with patch.object(
              self.plugin.rollback_handler,
              "set_rollback_callable",
              return_value=True,
            ):
              result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
              )

            self.assertEqual(result, 0)
            mock_sleep.assert_called_once_with(1)

    @patch("krkn.utils.filesystem_pvc.time.sleep")
    def test_run_success_with_dd(self, mock_sleep):
        """Test successful run using dd when fallocate is not available"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pod_name": "test-pod",
                    "fill_percentage": 80,
                    "duration": 1,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            # Create mock pod with PVC volume
            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "test-pvc"
            mock_volume.name = "test-volume"
            mock_pod.volumes = [mock_volume]

            # Create mock container with volume mount
            mock_container = MagicMock()
            mock_container.name = "test-container"
            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "test-volume"
            mock_vol_mount.mountPath = "/mnt/data"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_kubecli.get_pod_info.return_value = mock_pod

            # Mock PVC info
            mock_pvc = MagicMock()
            mock_kubecli.get_pvc_info.return_value = mock_pvc

            # Set up exec_cmd_in_pod responses (fallocate not available)
            mock_kubecli.exec_cmd_in_pod.side_effect = [
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df command
                "",  # command -v fallocate (not found)
                "/usr/bin/dd",  # command -v dd
                "",  # dd command
                "-rw-r--r-- 1 root root 70M Jan 1 00:00 kraken.tmp",  # ls -lh
                "71680000",  # wc -c
                "/dev/sda1 100000 80000 20000 80% /mnt/data",  # df after fill
                "",  # rm -f
                "total 0",  # ls -lh (file removed)
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df after cleanup
            ]

            mock_scenario_telemetry = MagicMock()
            
            with patch.object(
              self.plugin.rollback_handler,
              "set_rollback_callable",
              return_value=True,
            ):
              result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
              )

            self.assertEqual(result, 0)
            mock_sleep.assert_called_once_with(1)

    def test_run_no_file_creation_command_does_not_register_rollback(self):
        """Test rollback is not registered when neither fallocate nor dd is available."""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pod_name": "test-pod",
                    "fill_percentage": 80,
                    "duration": 1,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli
            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "test-pvc"
            mock_volume.name = "test-volume"
            mock_pod.volumes = [mock_volume]

            mock_container = MagicMock()
            mock_container.name = "test-container"
            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "test-volume"
            mock_vol_mount.mountPath = "/mnt/data"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_kubecli.get_pod_info.return_value = mock_pod
            mock_kubecli.get_pvc_info.return_value = MagicMock()
            mock_kubecli.get_pod_shell.return_value = "sh"
            mock_kubecli.exec_cmd_in_pod.side_effect = [
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df
                "",  # fallocate unavailable
                None,  # dd unavailable
            ]

            with patch.object(
                self.plugin.rollback_handler,
                "set_rollback_callable",
            ) as mock_rollback:
                result = self.plugin.run(
                    run_uuid="test-uuid",
                    scenario=scenario_path,
                    lib_telemetry=mock_telemetry,
                    scenario_telemetry=MagicMock(),
                )

            self.assertEqual(result, 1)
            mock_rollback.assert_not_called()
            self.assertEqual(mock_kubecli.exec_cmd_in_pod.call_count, 3)

    def test_run_no_binary_available(self):
        """Test run returns 1 when neither fallocate nor dd is available"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pod_name": "test-pod",
                    "fill_percentage": 80,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            # Create mock pod with PVC volume
            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "test-pvc"
            mock_volume.name = "test-volume"
            mock_pod.volumes = [mock_volume]

            # Create mock container with volume mount
            mock_container = MagicMock()
            mock_container.name = "test-container"
            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "test-volume"
            mock_vol_mount.mountPath = "/mnt/data"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_kubecli.get_pod_info.return_value = mock_pod

            # Mock PVC info
            mock_pvc = MagicMock()
            mock_kubecli.get_pvc_info.return_value = mock_pvc

            # Neither fallocate nor dd available
            mock_kubecli.exec_cmd_in_pod.side_effect = [
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df command
                "",  # command -v fallocate (not found)
                "",  # command -v dd (not found)
            ]

            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 1)

    def test_run_file_not_found(self):
        """Test run returns 1 when scenario file doesn't exist"""
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_scenario_telemetry = MagicMock()

        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario="/non/existent/path.yaml",
            lib_telemetry=mock_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        self.assertEqual(result, 1)

    def test_run_both_pvc_and_pod_name_provided(self):
        """Test run when both pvc_name and pod_name are provided (pod_name is overridden)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pvc_name": "test-pvc",
                    "pod_name": "ignored-pod",  # This will be overridden
                    "fill_percentage": 80,
                    "duration": 1,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            # Mock PVC info with pod names
            mock_pvc = MagicMock()
            mock_pvc.podNames = ["actual-pod-from-pvc"]
            mock_kubecli.get_pvc_info.return_value = mock_pvc

            # Create mock pod with PVC volume
            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "test-pvc"
            mock_volume.name = "test-volume"
            mock_pod.volumes = [mock_volume]

            # Create mock container with volume mount
            mock_container = MagicMock()
            mock_container.name = "test-container"
            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "test-volume"
            mock_vol_mount.mountPath = "/mnt/data"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_kubecli.get_pod_info.return_value = mock_pod

            # Mock df command output: 10% used
            mock_kubecli.exec_cmd_in_pod.side_effect = [
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df command
                "/usr/bin/fallocate",  # command -v fallocate
                "/usr/bin/dd",  # command -v dd
                "",  # fallocate command
                "-rw-r--r-- 1 root root 70M Jan 1 00:00 kraken.tmp",  # ls -lh (file created)
                "71680000",  # wc -c
                "/dev/sda1 100000 80000 20000 80% /mnt/data",  # df after fill
                "",  # rm -f (cleanup)
                "total 0",  # ls -lh (file removed)
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df after cleanup
            ]

            mock_scenario_telemetry = MagicMock()
            
            with patch.object(
                self.plugin.rollback_handler,
                "set_rollback_callable",
                return_value=True,
            ):
              with patch("krkn.utils.filesystem_pvc.time.sleep"):
                result = self.plugin.run(
                    run_uuid="test-uuid",
                    scenario=scenario_path,
                    lib_telemetry=mock_telemetry,
                    scenario_telemetry=mock_scenario_telemetry,
                )

            self.assertEqual(result, 0)  
            # get_pod_info should be called with "actual-pod-from-pvc", not "ignored-pod"
            mock_kubecli.get_pod_info.assert_called_with(
                name="actual-pod-from-pvc", 
                namespace="test-ns"
            )
            
            # Verify exec_cmd_in_pod uses the overridden pod name
            for call in mock_kubecli.exec_cmd_in_pod.call_args_list:
                kwargs = call[1]
                if 'pod_name' in kwargs:
                    self.assertEqual(kwargs['pod_name'], "actual-pod-from-pvc")

    def test_run_pvc_name_only_no_pods_associated(self):
        """Test run returns 1 when pvc_name is provided but no pods are associated"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pvc_name": "test-pvc",
                    "fill_percentage": 80,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            # Mock PVC info with empty pod names (no pods using this PVC)
            mock_pvc = MagicMock()
            mock_pvc.podNames = []  # No pods associated
            mock_kubecli.get_pvc_info.return_value = mock_pvc

            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            # Should return 1 because random.choice on empty list raises IndexError
            self.assertEqual(result, 1)

    @patch("krkn.utils.filesystem_pvc.time.sleep")
    def test_run_retries_pods_and_succeeds(self, mock_sleep):
        """Test that the engine loops through multiple pods if the first one lacks a shell"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pvc_name": "test-pvc",
                    "fill_percentage": 80,
                    "duration": 1,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            # Mock a PVC cluster layout providing 2 pods
            mock_pvc = MagicMock()
            mock_pvc.podNames = ["broken-pod", "working-pod"]
            mock_kubecli.get_pvc_info.return_value = mock_pvc

            # Pod Mock Definitions
            def get_pod_info_side_effect(name, namespace):
                pod = MagicMock()
                mock_volume = MagicMock()
                mock_volume.pvcName = "test-pvc"
                mock_volume.name = "test-volume"
                pod.volumes = [mock_volume]

                mock_container = MagicMock()
                mock_container.name = "test-container"
                mock_vol_mount = MagicMock()
                mock_vol_mount.name = "test-volume"
                mock_vol_mount.mountPath = "/mnt/data"
                mock_container.volumeMounts = [mock_vol_mount]
                pod.containers = [mock_container]
                return pod

            mock_kubecli.get_pod_info.side_effect = get_pod_info_side_effect

            # Simulate "broken-pod" has no shell, but "working-pod" successfully returns "bash"
            def get_pod_shell_side_effect(pod_name, ns, container):
                if pod_name == "broken-pod":
                    return None
                return "bash"

            mock_kubecli.get_pod_shell.side_effect = get_pod_shell_side_effect

            # Exec configurations for the successful execution track
            mock_kubecli.exec_cmd_in_pod.side_effect = [
                "/dev/sda1 100000 10000 90000 10%",  # Initial df
                "/usr/bin/fallocate",                # fallocate check
                "/usr/bin/dd",                       # dd check
                "",                                  # File creation
                "-rw-r--r-- 1 root root 70M kraken.tmp",  # ls
                "71680000",                          # wc -c
                "/dev/sda1 100000 80000 20000 80%",  # df after fill
                "",                                  # rm -f
                "total 0",                           # ls after cleanup
                "/dev/sda1 100000 10000 90000 10%",  # df after cleanup
            ]

            # Patch random.shuffle to keep order predictable for testing execution paths
            with (patch("random.shuffle", lambda x: None),
                  patch.object(
                    self.plugin.rollback_handler,
                    "set_rollback_callable",
                    return_value=True,
                ),
            ):
                result = self.plugin.run(
                    run_uuid="test-uuid",
                    scenario=scenario_path,
                    lib_telemetry=mock_telemetry,
                    scenario_telemetry=MagicMock(),
                )

            # Assure the engine bypasses the error state and completes successfully (0)
            self.assertEqual(result, 0)
            # Verify it evaluated the active shell profile on the working candidate explicitly
            mock_kubecli.get_pod_info.assert_any_call(name="broken-pod", namespace="test-ns")
            mock_kubecli.get_pod_info.assert_any_call(name="working-pod", namespace="test-ns")

            self.assertEqual(mock_kubecli.get_pod_shell.call_count, 3)
            mock_kubecli.get_pod_shell.assert_any_call("broken-pod", "test-ns", "test-container")
            mock_kubecli.get_pod_shell.assert_any_call("working-pod", "test-ns", "test-container")

    def test_run_fails_when_all_pods_lack_shell(self):
        """Test that the plugin fails safely out if all cluster pods lack a shell"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pvc_name": "test-pvc",
                    "fill_percentage": 80,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            mock_pvc = MagicMock()
            mock_pvc.podNames = ["pod-a", "pod-b"]
            mock_kubecli.get_pvc_info.return_value = mock_pvc

            # Provide common valid structural shapes for pods
            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "test-pvc"
            mock_volume.name = "test-volume"
            mock_pod.volumes = [mock_volume]
            mock_container = MagicMock()
            mock_container.name = "test-container"
            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "test-volume"
            mock_vol_mount.mountPath = "/mnt/data"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_kubecli.get_pod_info.return_value = mock_pod
            # Both pods return None for active shell capabilities
            mock_kubecli.get_pod_shell.return_value = None

            with patch.object(self.plugin.rollback_handler,"set_rollback_callable") as mock_rollback:
                result = self.plugin.run(
                    run_uuid="test-uuid",
                    scenario=scenario_path,
                    lib_telemetry=mock_telemetry,
                    scenario_telemetry=MagicMock(),
                )
            self.assertEqual(result, 1)
            self.assertEqual(mock_kubecli.get_pod_shell.call_count, 2)
            self.assertEqual(mock_kubecli.exec_cmd_in_pod.call_count, 0)
            mock_rollback.assert_not_called()

    def test_run_skips_pod_without_pvc_and_continues(self):
        """Test that the loop ignores intermediate candidate pods missing a valid PVC mapping"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pvc_name": "test-pvc",
                    "fill_percentage": 80,
                    "duration": 1,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            mock_pvc = MagicMock()
            mock_pvc.podNames = ["no-pvc-pod", "good-pod"]
            mock_kubecli.get_pvc_info.return_value = mock_pvc

            def get_pod_info_side_effect(name, namespace):
                pod = MagicMock()
                mock_volume = MagicMock()
                mock_container = MagicMock()
                mock_container.name = "test-container"
                mock_vol_mount = MagicMock()
                mock_vol_mount.name = "test-volume"
                mock_vol_mount.mountPath = "/mnt/data"
                mock_container.volumeMounts = [mock_vol_mount]
                pod.containers = [mock_container]

                if name == "no-pvc-pod":
                    mock_volume.pvcName = None  # Broken volume mapping configuration
                else:
                    mock_volume.pvcName = "test-pvc"

                mock_volume.name = "test-volume"
                pod.volumes = [mock_volume]
                return pod

            mock_kubecli.get_pod_info.side_effect = get_pod_info_side_effect
            mock_kubecli.get_pod_shell.return_value = "bash"

            mock_kubecli.exec_cmd_in_pod.side_effect = [
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # Initial df
                "/usr/bin/fallocate",                          # fallocate check
                "/usr/bin/dd",                                 # dd check
                "",                                            # File creation
                "-rw-r--r-- 1 root root 70M Jan 1 00:00 kraken.tmp",  # ls
                "71680000",                                    # wc -c
                "/dev/sda1 100000 80000 20000 80% /mnt/data",  # df after fill
                "",                                            # rm -f
                "total 0",                                     # ls after cleanup
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df after cleanup
            ]

            with (patch("random.shuffle", lambda x: None), 
                patch("krkn.utils.filesystem_pvc.time.sleep"),
                patch("krkn.utils.pod_volumes.read_raw_pod", return_value=None),
                patch.object(
                    self.plugin.rollback_handler,
                    "set_rollback_callable",
                    return_value=True,
                ),
            ):
                result = self.plugin.run(
                    run_uuid="test-uuid",
                    scenario=scenario_path,
                    lib_telemetry=mock_telemetry,
                    scenario_telemetry=MagicMock(),
                )

            self.assertEqual(result, 0)
            mock_kubecli.get_pod_info.assert_any_call(name="no-pvc-pod", namespace="test-ns")
            mock_kubecli.get_pod_info.assert_any_call(name="good-pod", namespace="test-ns")

            # The first pod is skipped before shell access.
            self.assertEqual(mock_kubecli.get_pod_shell.call_count, 2)
            mock_kubecli.get_pod_shell.assert_has_calls([
                call("good-pod", "test-ns", "test-container"),
                call("good-pod", "test-ns", "test-container")
            ])

    def test_run_shell_check_before_exec(self):
        """Test that get_pod_shell is called before any exec_cmd_in_pod when shell exists"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pod_name": "test-pod",
                    "fill_percentage": 80,
                    "duration": 1,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "test-pvc"
            mock_volume.name = "test-volume"
            mock_pod.volumes = [mock_volume]

            mock_container = MagicMock()
            mock_container.name = "test-container"
            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "test-volume"
            mock_vol_mount.mountPath = "/mnt/data"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_kubecli.get_pod_info.return_value = mock_pod
            mock_kubecli.get_pvc_info.return_value = MagicMock()
            mock_kubecli.get_pod_shell.return_value = "bash"
            mock_kubecli.exec_cmd_in_pod.side_effect = [
                "/dev/sda1 100000 10000 90000 10% /mnt/data",
                "/usr/bin/fallocate",
                "/usr/bin/dd",
                "",
                "-rw-r--r-- 1 root root 70M Jan 1 00:00 kraken.tmp",
                "71680000",
                "/dev/sda1 100000 80000 20000 80% /mnt/data",
                "",
                "total 0",
                "/dev/sda1 100000 10000 90000 10% /mnt/data",
            ]

            mock_scenario_telemetry = MagicMock()

            call_order = []
            exec_responses = iter([
                "/dev/sda1 100000 10000 90000 10% /mnt/data",
                "/usr/bin/fallocate",
                "/usr/bin/dd",
                "",
                "-rw-r--r-- 1 root root 70M Jan 1 00:00 kraken.tmp",
                "71680000",
                "/dev/sda1 100000 80000 20000 80% /mnt/data",
                "",
                "total 0",
                "/dev/sda1 100000 10000 90000 10% /mnt/data",
            ])

            def track_shell(*a, **kw):
                call_order.append("get_pod_shell")
                return "bash"

            def track_exec(*a, **kw):
                call_order.append("exec_cmd_in_pod")
                return next(exec_responses)

            mock_kubecli.get_pod_shell.side_effect = track_shell
            mock_kubecli.exec_cmd_in_pod.side_effect = track_exec
            
            with patch.object(
              self.plugin.rollback_handler,
              "set_rollback_callable",
              return_value=True,
            ):
              with patch("krkn.utils.filesystem_pvc.time.sleep"):
                result = self.plugin.run(
                    run_uuid="test-uuid",
                    scenario=scenario_path,
                    lib_telemetry=mock_telemetry,
                    scenario_telemetry=mock_scenario_telemetry,
                )

            self.assertEqual(result, 0)
            self.assertEqual(call_order[:2], ["get_pod_shell", "get_pod_shell"])
            self.assertTrue(all(c == "exec_cmd_in_pod" for c in call_order[2:]))

    def test_run_file_creation_failed(self):
        """Test run returns 1 when file creation fails and verifies cleanup is attempted"""
        with tempfile.TemporaryDirectory() as temp_dir:
            scenario_config = {
                "pvc_scenario": {
                    "namespace": "test-ns",
                    "pod_name": "test-pod",
                    "fill_percentage": 80,
                    "duration": 1,
                }
            }
            scenario_path = self.create_scenario_file(scenario_config, temp_dir)

            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

            # Create mock pod with PVC volume
            mock_pod = MagicMock()
            mock_volume = MagicMock()
            mock_volume.pvcName = "test-pvc"
            mock_volume.name = "test-volume"
            mock_pod.volumes = [mock_volume]

            # Create mock container with volume mount
            mock_container = MagicMock()
            mock_container.name = "test-container"
            mock_vol_mount = MagicMock()
            mock_vol_mount.name = "test-volume"
            mock_vol_mount.mountPath = "/mnt/data"
            mock_container.volumeMounts = [mock_vol_mount]
            mock_pod.containers = [mock_container]

            mock_kubecli.get_pod_info.return_value = mock_pod

            # Mock PVC info
            mock_pvc = MagicMock()
            mock_kubecli.get_pvc_info.return_value = mock_pvc

            # Set up exec_cmd_in_pod responses - file creation fails
            mock_kubecli.exec_cmd_in_pod.side_effect = [
                "/dev/sda1 100000 10000 90000 10% /mnt/data",  # df command
                "/usr/bin/fallocate",  # command -v fallocate
                "/usr/bin/dd",  # command -v dd
                "",  # fallocate command
                "total 0",  # ls -lh shows NO kraken.tmp (file creation failed)
                "",  # rm -f (cleanup attempt)
                "total 0",  # ls -lh (cleanup verification)
            ]

            mock_scenario_telemetry = MagicMock()
            
            with patch.object(
               self.plugin.rollback_handler,
               "set_rollback_callable",
               return_value=True,
            ):
              result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
              )

            # Should return 1 because file creation failed
            self.assertEqual(result, 1)
            
            # Verify cleanup was attempted (7 calls total: df, 2x command -v, fallocate, ls, rm, ls)
            self.assertEqual(mock_kubecli.exec_cmd_in_pod.call_count, 7)

class TestRollbackTempFileEdgeCases(unittest.TestCase):
    """Additional tests for rollback_temp_file edge cases"""

    @patch("krkn.utils.filesystem_pvc.logging")
    def test_rollback_temp_file_still_exists(self, mock_logging):
        """Test rollback when file still exists after removal attempt and logs warning"""
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_kubecli = MagicMock()
        mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

        # Simulate file still exists after rm command
        mock_kubecli.exec_cmd_in_pod.side_effect = [
            "",  # rm -f command output
            "-rw-r--r-- 1 root root 70M Jan 1 00:00 kraken.tmp",  # ls -lh shows file still exists
        ]

        # Create rollback data
        rollback_data = {
            "pod_name": "test-pod",
            "namespace": "test-ns",
            "container_name": "test-container",
            "full_path": "/mnt/data/kraken.tmp",
            "file_name": "kraken.tmp",
            "mount_path": "/mnt/data",
        }
        encoded_data = encode_rollback_data(rollback_data)

        rollback_content = RollbackContent(
            namespace="test-ns",
            resource_identifier=encoded_data,
        )

        # Should not raise exception, just log warning
        PvcScenarioPlugin.rollback_temp_file(rollback_content, mock_telemetry)

        # Verify exec_cmd_in_pod was called twice
        assert mock_kubecli.exec_cmd_in_pod.call_count == 2
        
        # Verify error was logged to inform operators of incomplete rollback
        mock_logging.error.assert_called_once()
        error_message = mock_logging.error.call_args[0][0]
        self.assertIn("Failed to rollback filesystem PVC fill", error_message)


if __name__ == "__main__":
    unittest.main()
