# Copyright 2026 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Tests for shared filesystem PVC fill operations."""

import unittest
from unittest.mock import MagicMock, patch
from krkn.utils.filesystem_pvc import (fill_filesystem_pvc, remove_filesystem_fill, encode_rollback_data, rollback_filesystem_fill)
from krkn.utils.pod_volumes import PodVolumeTarget
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift


class TestFillFilesystemPvc(unittest.TestCase):
    def test_remove_filesystem_fill_success(self):
        kubecli = MagicMock()
        kubecli.exec_cmd_in_pod.side_effect = [
            "",
            "total 0\ndrwxr-xr-x 2 root root 40 Jan 1 00:00 .",
        ]

        remove_filesystem_fill(
            kubecli=kubecli,
            pod_name="test-pod",
            namespace="test-ns",
            container_name="test-container",
            mount_path="/mnt/data",
            file_name="kraken.tmp",
        )

        self.assertEqual(kubecli.exec_cmd_in_pod.call_count, 2)

    def test_remove_filesystem_fill_failure(self):
        kubecli = MagicMock()
        kubecli.exec_cmd_in_pod.side_effect = [
            "",
            "total 1024\n-rw-r--r-- 1 root root 1M Jan 1 00:00 kraken.tmp",
        ]

        with self.assertRaises(RuntimeError):
            remove_filesystem_fill(
                kubecli=kubecli,
                pod_name="test-pod",
                namespace="test-ns",
                container_name="test-container",
                mount_path="/mnt/data",
                file_name="kraken.tmp",
            )

        self.assertEqual(kubecli.exec_cmd_in_pod.call_count, 2)
        
    def test_logs_usage_file_size_and_cleanup(self):
        kubecli = MagicMock()
        kubecli.get_pod_shell.return_value = "shell"
        df_outputs = iter([
            "filesystem 1000 100 900 10% /data",
            "filesystem 1000 500 500 50% /data",
            "filesystem 1000 100 900 10% /data",
        ])
        listing_outputs = iter([
            "-rw-r--r-- 1 user group 400K kraken.tmp",
            "total 0",
        ])

        def exec_cmd(command, pod_name, namespace, container_name):
            command = command[0]
            if command.startswith("df "):
                return next(df_outputs)
            if command == "command -v fallocate":
                return "/usr/bin/fallocate"
            if command == "command -v dd":
                return "/usr/bin/dd"
            if command.startswith("ls -lh "):
                return next(listing_outputs)
            if command.startswith("wc -c < "):
                return "409600"
            return ""

        kubecli.exec_cmd_in_pod.side_effect = exec_cmd
        target = PodVolumeTarget(
            pvc_name="test-pvc",
            volume_name="data",
            container_name="app",
            path="/data",
            mode="filesystem",
        )
        rollback_callback = MagicMock()

        with patch("krkn.utils.filesystem_pvc.time.sleep") as sleep, self.assertLogs(
            "root", level="INFO"
        ) as captured:
            status, rollback_data = fill_filesystem_pvc(
                kubecli,
                pod_name="app-pod",
                namespace="default",
                pvc_name="test-pvc",
                target_fill_percentage="50",
                duration=20,
                volume_target=target,
                on_file_created=rollback_callback,
                pod=object(),
            )

        self.assertEqual(status, 0)
        self.assertEqual(rollback_data["file_name"], "kraken.tmp")
        rollback_callback.assert_called_once_with(rollback_data)
        sleep.assert_called_once_with(20)
        self.assertTrue(any("Filesystem PVC before fill" in line for line in captured.output))
        self.assertTrue(any("actual=409600B" in line for line in captured.output))
        self.assertTrue(any("utilization=50.00%" in line for line in captured.output))
        self.assertTrue(any("Filesystem PVC after cleanup" in line for line in captured.output))
        self.assertTrue(any("fill file removed" in line for line in captured.output))

class TestRollbackFilesystemFill(unittest.TestCase):

    def test_rollback_filesystem_fill_success(self):
        """Test successful rollback removes the temporary file."""
        # Create mock telemetry
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
        mock_kubecli = MagicMock()
        mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

        # Simulate successful file removal
        mock_kubecli.exec_cmd_in_pod.side_effect = [
            "",
            "total 0\ndrwxr-xr-x 2 root root 40 Jan 1 00:00 .",
        ]

        # Create rollback data
        rollback_data = {
            "pod_name": "test-pod",
            "namespace": "test-ns",
            "container_name": "test-container",
            "file_name": "kraken.tmp",
            "mount_path": "/mnt/data",
        }

        encoded_data = encode_rollback_data(rollback_data)

        rollback_filesystem_fill(encoded_data, mock_telemetry)
        # Verify exec_cmd_in_pod was called
        self.assertEqual(mock_kubecli.exec_cmd_in_pod.call_count, 2)

    @patch("krkn.utils.filesystem_pvc.logging")
    def test_rollback_filesystem_fill_invalid_data(self, mock_logging):
        """Test rollback handles invalid encoded data gracefully."""
        mock_telemetry = MagicMock(spec=KrknTelemetryOpenshift)

        rollback_filesystem_fill("invalid-base64-data!!!", mock_telemetry)
        # Verify error was logged to inform users of rollback failure
        mock_logging.error.assert_called_once()
        error_message = mock_logging.error.call_args[0][0]
        self.assertIn("Failed to rollback filesystem PVC fill", error_message)


if __name__ == "__main__":
    unittest.main()
