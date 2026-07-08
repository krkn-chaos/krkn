#!/usr/bin/env python3

"""
Test suite for VM migration chaos scenario plugin

Usage:
    python -m coverage run -a -m unittest tests/test_vm_migration_chaos_scenario_plugin.py -v
"""

import unittest
import sys
from unittest.mock import MagicMock, patch, mock_open

sys.modules['boto3'] = MagicMock()

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn.scenario_plugins.vm_migration_chaos.vm_migration_chaos_scenario_plugin import (
    VmMigrationChaosScenarioPlugin,
)


class TestVmMigrationChaosScenarioPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = VmMigrationChaosScenarioPlugin()

    def test_get_scenario_types(self):
        self.assertEqual(
            self.plugin.get_scenario_types(),
            ["vm_migration_chaos_scenarios"],
        )

    def test_requires_kubernetes(self):
        mock_telemetry = MagicMock()
        mock_telemetry.get_lib_kubernetes.return_value = None

        yaml_data = (
            "vm_migration_chaos:\n"
            "  vm_name: test-vm\n"
            "  migration_action: trigger_and_disrupt\n"
        )
        with patch("builtins.open", mock_open(read_data=yaml_data)):
            result = self.plugin.run(
                "uuid", "test.yml", mock_telemetry, MagicMock()
            )
        self.assertEqual(result, 1)

    def test_requires_vm_name(self):
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_telemetry = MagicMock()
        mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

        yaml_data = (
            "vm_migration_chaos:\n"
            "  migration_action: trigger_and_disrupt\n"
        )
        with patch("builtins.open", mock_open(read_data=yaml_data)):
            result = self.plugin.run(
                "uuid", "test.yml", mock_telemetry, MagicMock()
            )
        self.assertEqual(result, 1)

    def test_invalid_action(self):
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_telemetry = MagicMock()
        mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

        yaml_data = (
            "vm_migration_chaos:\n"
            "  vm_name: test-vm\n"
            "  migration_action: invalid\n"
        )
        with patch("builtins.open", mock_open(read_data=yaml_data)):
            result = self.plugin.run(
                "uuid", "test.yml", mock_telemetry, MagicMock()
            )
        self.assertEqual(result, 1)

    def test_vmi_not_found(self):
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_kubecli.get_vmi.return_value = None
        mock_telemetry = MagicMock()
        mock_telemetry.get_lib_kubernetes.return_value = mock_kubecli

        yaml_data = (
            "vm_migration_chaos:\n"
            "  vm_name: nonexistent-vm\n"
            "  vm_namespace: default\n"
            "  migration_action: trigger_and_disrupt\n"
        )
        with patch("builtins.open", mock_open(read_data=yaml_data)):
            result = self.plugin.run(
                "uuid", "test.yml", mock_telemetry, MagicMock()
            )
        self.assertEqual(result, 1)

    def test_check_dual_pods_none_detected(self):
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_kubecli.list_pods.return_value = ["virt-launcher-test-vm-abc"]

        result = self.plugin._check_dual_pods(
            mock_kubecli, "test-vm", "default"
        )
        self.assertFalse(result)

    def test_check_dual_pods_detected(self):
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_kubecli.list_pods.return_value = [
            "virt-launcher-test-vm-abc",
            "virt-launcher-test-vm-def",
        ]

        result = self.plugin._check_dual_pods(
            mock_kubecli, "test-vm", "default"
        )
        self.assertTrue(result)

    @patch("krkn.scenario_plugins.vm_migration_chaos.vm_migration_chaos_scenario_plugin.time")
    def test_wait_for_migration_completed(self, mock_time):
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_kubecli.get_vmi.return_value = {
            "status": {
                "phase": "Running",
                "nodeName": "node2",
                "migrationState": {"completed": True},
            }
        }
        mock_time.time.side_effect = [0, 5]
        mock_time.sleep = MagicMock()

        result = self.plugin._wait_for_migration(
            mock_kubecli, "test-vm", "default", 600
        )
        self.assertTrue(result)

    @patch("krkn.scenario_plugins.vm_migration_chaos.vm_migration_chaos_scenario_plugin.time")
    def test_wait_for_migration_failed(self, mock_time):
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_kubecli.get_vmi.return_value = {
            "status": {
                "phase": "Running",
                "migrationState": {"failed": True},
            }
        }
        mock_time.time.side_effect = [0, 5]
        mock_time.sleep = MagicMock()

        result = self.plugin._wait_for_migration(
            mock_kubecli, "test-vm", "default", 600
        )
        self.assertFalse(result)

    def test_cleanup_vmim(self):
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_custom = MagicMock()
        mock_kubecli.custom_object_client.return_value = mock_custom

        self.plugin._cleanup_vmim(mock_kubecli, "test-vm", "default")

        mock_custom.delete_namespaced_custom_object.assert_called_once()


if __name__ == "__main__":
    unittest.main()
