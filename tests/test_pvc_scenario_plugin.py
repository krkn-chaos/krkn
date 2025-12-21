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
from unittest.mock import MagicMock, patch

import pytest

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.pvc.pvc_scenario_plugin import PvcScenarioPlugin
from krkn.rollback.config import RollbackContent


class TestPvcScenarioPlugin(unittest.TestCase):
    """Unit tests for PvcScenarioPlugin class"""

    def setUp(self):
        """
        Set up test fixtures for PvcScenarioPlugin
        """
        self.plugin = PvcScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pvc_scenarios"])
        self.assertEqual(len(result), 1)


class TestToKbytes:
    """Tests for the to_kbytes method"""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = PvcScenarioPlugin()

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("1Ki", 1),  # 1 KB
            ("2Ki", 2),  # 2 KB
            ("1Mi", 1024),  # 1024 KB
            ("2Mi", 2 * 1024),  # 2048 KB
            ("1Gi", 1024 * 1024),  # 1 GB in KB
            ("5Gi", 5 * 1024 * 1024),  # 5 GB in KB
            ("1Ti", 1024 * 1024 * 1024),  # 1 TB in KB
        ],
    )
    def test_to_kbytes_valid_values(self, value, expected):
        """Test to_kbytes with valid Kubernetes storage values"""
        result = self.plugin.to_kbytes(value)
        assert result == expected

    @pytest.mark.parametrize(
        "invalid_value",
        [
            "1K",  # Missing 'i'
            "1MB",  # Invalid format
            "1Gib",  # Extra character
            "abc",  # Non-numeric
            "1024",  # Missing unit
            "",  # Empty string
            "1Pi",  # Unsupported unit (Peta)
        ],
    )
    def test_to_kbytes_invalid_values(self, invalid_value):
        """Test to_kbytes raises RuntimeError for invalid values"""
        with pytest.raises(RuntimeError):
            self.plugin.to_kbytes(invalid_value)


class TestRemoveTempFile:
    """Tests for the remove_temp_file method"""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = PvcScenarioPlugin()

    def test_remove_temp_file_success(self):
        """Test successful removal of temp file"""
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        # Simulate file not present in ls output after removal
        mock_kubecli.exec_cmd_in_pod.side_effect = [
            "",  # rm -f command output
            "total 0\ndrwxr-xr-x 2 root root 40 Jan 1 00:00 .",  # ls -lh output without kraken.tmp
        ]

        # Should not raise any exception
        self.plugin.remove_temp_file(
            file_name="kraken.tmp",
            full_path="/mnt/data/kraken.tmp",
            pod_name="test-pod",
            namespace="test-ns",
            container_name="test-container",
            mount_path="/mnt/data",
            file_size_kb=1024,
            kubecli=mock_kubecli,
        )

        # Verify exec_cmd_in_pod was called twice (rm and ls)
        assert mock_kubecli.exec_cmd_in_pod.call_count == 2

    def test_remove_temp_file_failure(self):
        """Test removal failure when file still exists"""
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        # Simulate file still present in ls output after removal attempt
        mock_kubecli.exec_cmd_in_pod.side_effect = [
            "",  # rm -f command output
            "total 1024\n-rw-r--r-- 1 root root 1M Jan 1 00:00 kraken.tmp",  # ls -lh output with kraken.tmp
        ]

        with pytest.raises(RuntimeError):
            self.plugin.remove_temp_file(
                file_name="kraken.tmp",
                full_path="/mnt/data/kraken.tmp",
                pod_name="test-pod",
                namespace="test-ns",
                container_name="test-container",
                mount_path="/mnt/data",
                file_size_kb=1024,
                kubecli=mock_kubecli,
            )


class TestRollbackTempFile:
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
            "container_name": "test-container",
            "full_path": "/mnt/data/kraken.tmp",
            "file_name": "kraken.tmp",
            "mount_path": "/mnt/data",
        }
        encoded_data = base64.b64encode(
            json.dumps(rollback_data).encode("utf-8")
        ).decode("utf-8")

        rollback_content = RollbackContent(
            namespace="test-ns",
            resource_identifier=encoded_data,
        )

        # Should not raise any exception
        PvcScenarioPlugin.rollback_temp_file(rollback_content, mock_telemetry)

        # Verify exec_cmd_in_pod was called
        assert mock_kubecli.exec_cmd_in_pod.call_count == 2

    def test_rollback_temp_file_invalid_data(self):
        """Test rollback handles invalid encoded data gracefully"""
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)

        rollback_content = RollbackContent(
            namespace="test-ns",
            resource_identifier="invalid-base64-data!!!",
        )

        # Should not raise exception, just log the error
        PvcScenarioPlugin.rollback_temp_file(rollback_content, mock_telemetry)


class TestPvcScenarioPluginRun:
    """Tests for the run method of PvcScenarioPlugin"""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = PvcScenarioPlugin()

    def create_scenario_file(self, config: dict) -> str:
        """Helper to create a temporary scenario YAML file"""
        import yaml

        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            yaml.dump(config, f)
        return path

    def test_run_missing_namespace(self):
        """Test run returns 1 when namespace is missing"""
        scenario_config = {
            "pvc_scenario": {
                "pvc_name": "test-pvc",
                # namespace is missing
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                krkn_config={},
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            assert result == 1
        finally:
            os.unlink(scenario_path)

    def test_run_missing_pvc_and_pod_name(self):
        """Test run returns 1 when both pvc_name and pod_name are missing"""
        scenario_config = {
            "pvc_scenario": {
                "namespace": "test-ns",
                # pvc_name and pod_name are missing
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                krkn_config={},
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            assert result == 1
        finally:
            os.unlink(scenario_path)

    def test_run_pod_not_found(self):
        """Test run returns 1 when pod doesn't exist"""
        scenario_config = {
            "pvc_scenario": {
                "namespace": "test-ns",
                "pod_name": "non-existent-pod",
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
            mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            mock_kubecli = MagicMock()
            mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli
            mock_kubecli.get_pod_info.return_value = None
            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                krkn_config={},
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            assert result == 1
        finally:
            os.unlink(scenario_path)

    def test_run_pvc_not_found_for_pod(self):
        """Test run returns 1 when pod has no PVC"""
        scenario_config = {
            "pvc_scenario": {
                "namespace": "test-ns",
                "pod_name": "test-pod",
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
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
                krkn_config={},
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            assert result == 1
        finally:
            os.unlink(scenario_path)

    def test_run_invalid_fill_percentage(self):
        """Test run returns 1 when target fill percentage is invalid"""
        scenario_config = {
            "pvc_scenario": {
                "namespace": "test-ns",
                "pod_name": "test-pod",
                "fill_percentage": 10,  # Lower than current usage
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
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
                krkn_config={},
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            # Should return 1 because target fill (10%) < current fill (50%)
            assert result == 1
        finally:
            os.unlink(scenario_path)

    @patch("krkn.scenario_plugins.pvc.pvc_scenario_plugin.time.sleep")
    @patch("krkn.scenario_plugins.pvc.pvc_scenario_plugin.cerberus.publish_kraken_status")
    def test_run_success_with_fallocate(self, mock_publish, mock_sleep):
        """Test successful run using fallocate"""
        scenario_config = {
            "pvc_scenario": {
                "namespace": "test-ns",
                "pod_name": "test-pod",
                "fill_percentage": 80,
                "duration": 1,
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
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
                "",  # rm -f (cleanup)
                "total 0",  # ls -lh (file removed)
            ]

            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                krkn_config={},
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            assert result == 0
            mock_sleep.assert_called_once_with(1)
        finally:
            os.unlink(scenario_path)

    @patch("krkn.scenario_plugins.pvc.pvc_scenario_plugin.time.sleep")
    @patch("krkn.scenario_plugins.pvc.pvc_scenario_plugin.cerberus.publish_kraken_status")
    def test_run_success_with_dd(self, mock_publish, mock_sleep):
        """Test successful run using dd when fallocate is not available"""
        scenario_config = {
            "pvc_scenario": {
                "namespace": "test-ns",
                "pod_name": "test-pod",
                "fill_percentage": 80,
                "duration": 1,
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
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
                "",  # rm -f
                "total 0",  # ls -lh (file removed)
            ]

            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                krkn_config={},
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            assert result == 0
        finally:
            os.unlink(scenario_path)

    def test_run_no_binary_available(self):
        """Test run returns 1 when neither fallocate nor dd is available"""
        scenario_config = {
            "pvc_scenario": {
                "namespace": "test-ns",
                "pod_name": "test-pod",
                "fill_percentage": 80,
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
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
                None,  # command -v dd (not found)
            ]

            mock_scenario_telemetry = MagicMock()

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                krkn_config={},
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            assert result == 1
        finally:
            os.unlink(scenario_path)

    def test_run_file_not_found(self):
        """Test run returns 1 when scenario file doesn't exist"""
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_scenario_telemetry = MagicMock()

        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario="/non/existent/path.yaml",
            krkn_config={},
            lib_telemetry=mock_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        assert result == 1

    def test_run_both_pvc_and_pod_name_provided(self):
        """Test run when both pvc_name and pod_name are provided (pod_name is ignored)"""
        scenario_config = {
            "pvc_scenario": {
                "namespace": "test-ns",
                "pvc_name": "test-pvc",
                "pod_name": "ignored-pod",  # This should be ignored
                "fill_percentage": 80,
                "duration": 1,
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
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
                "",  # rm -f (cleanup)
                "total 0",  # ls -lh (file removed)
            ]

            mock_scenario_telemetry = MagicMock()

            with patch("krkn.scenario_plugins.pvc.pvc_scenario_plugin.time.sleep"):
                with patch("krkn.scenario_plugins.pvc.pvc_scenario_plugin.cerberus.publish_kraken_status"):
                    result = self.plugin.run(
                        run_uuid="test-uuid",
                        scenario=scenario_path,
                        krkn_config={},
                        lib_telemetry=mock_telemetry,
                        scenario_telemetry=mock_scenario_telemetry,
                    )

            assert result == 0
        finally:
            os.unlink(scenario_path)

    def test_run_pvc_name_only_no_pods_associated(self):
        """Test run returns 1 when pvc_name is provided but no pods are associated"""
        scenario_config = {
            "pvc_scenario": {
                "namespace": "test-ns",
                "pvc_name": "test-pvc",
                "fill_percentage": 80,
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
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
                krkn_config={},
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            # Should return 1 because random.choice on empty list raises IndexError
            assert result == 1
        finally:
            os.unlink(scenario_path)

    def test_run_file_creation_failed(self):
        """Test run returns 1 when file creation fails and cleanup is attempted"""
        scenario_config = {
            "pvc_scenario": {
                "namespace": "test-ns",
                "pod_name": "test-pod",
                "fill_percentage": 80,
                "duration": 1,
            }
        }
        scenario_path = self.create_scenario_file(scenario_config)

        try:
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

            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario=scenario_path,
                krkn_config={},
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            # Should return 1 because file creation failed
            assert result == 1
        finally:
            os.unlink(scenario_path)


class TestRollbackTempFileEdgeCases:
    """Additional tests for rollback_temp_file edge cases"""

    def test_rollback_temp_file_still_exists(self):
        """Test rollback when file still exists after removal attempt"""
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
            "container_name": "test-container",
            "full_path": "/mnt/data/kraken.tmp",
            "file_name": "kraken.tmp",
            "mount_path": "/mnt/data",
        }
        encoded_data = base64.b64encode(
            json.dumps(rollback_data).encode("utf-8")
        ).decode("utf-8")

        rollback_content = RollbackContent(
            namespace="test-ns",
            resource_identifier=encoded_data,
        )

        # Should not raise exception, just log warning
        PvcScenarioPlugin.rollback_temp_file(rollback_content, mock_telemetry)

        # Verify exec_cmd_in_pod was called twice
        assert mock_kubecli.exec_cmd_in_pod.call_count == 2


if __name__ == "__main__":
    unittest.main()
