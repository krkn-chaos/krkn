#!/usr/bin/env python3

"""
Test suite for ContainerScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_container_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.container.container_scenario_plugin import ContainerScenarioPlugin


class TestContainerScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ContainerScenarioPlugin
        """
        self.plugin = ContainerScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["container_scenarios"])
        self.assertEqual(len(result), 1)

    def test_distroless_container_bug(self):
        """
        Reproduce the distroless container bug and verify the fallback.
        """
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_kubecli.exec_cmd_in_pod.side_effect = Exception("impossible to determine the shell to run command")

        # Mock the fallback _kill_container_via_node directly on the plugin
        self.plugin._kill_container_via_node = MagicMock()

        self.plugin.retry_container_killing(
            kill_action="kill 15",
            podname="noobaa-db-pg-cluster-2",
            namespace="openshift-storage",
            container_name="postgres",
            kubecli=mock_kubecli
        )
        self.plugin._kill_container_via_node.assert_called_once_with(
            "noobaa-db-pg-cluster-2", "openshift-storage", "postgres", mock_kubecli
        )

    @patch("time.sleep")
    def test_crictl_execution_path_success(self, mock_sleep):
        """
        Test the successful crictl execution path and container status validation.
        """
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        
        # Mock initial pod_info
        mock_pod_info_1 = MagicMock()
        mock_pod_info_1.spec.node_name = "node-1"
        
        mock_status_1 = MagicMock()
        mock_status_1.name = "postgres"
        mock_status_1.container_id = "containerd://1234567890abcdef"
        mock_status_1.restart_count = 0
        mock_pod_info_1.status.container_statuses = [mock_status_1]
        
        # Mock updated pod_info (validation success)
        mock_pod_info_2 = MagicMock()
        mock_status_2 = MagicMock()
        mock_status_2.name = "postgres"
        mock_status_2.restart_count = 1  # increased
        mock_pod_info_2.status.container_statuses = [mock_status_2]
        
        mock_kubecli.cli.read_namespaced_pod.side_effect = [mock_pod_info_1, mock_pod_info_2]
        mock_kubecli.exec_command_on_node.return_value = "crictl stop 1234567890abcdef"
        
        self.plugin._kill_container_via_node("mypod", "mynamespace", "postgres", mock_kubecli)
        
        mock_kubecli.exec_command_on_node.assert_called_once_with(
            "node-1", ["chroot /host /bin/sh -c 'crictl stop 1234567890abcdef'"], "krkn-crictl-12345678", "mynamespace"
        )
        mock_kubecli.delete_pod.assert_called_once_with("krkn-crictl-12345678", "mynamespace")

    @patch("time.sleep")
    def test_crictl_execution_path_failure(self, mock_sleep):
        """
        Test that exec pod is cleaned up even when crictl execution fails.
        """
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        
        mock_pod_info_1 = MagicMock()
        mock_pod_info_1.spec.node_name = "node-1"
        mock_status_1 = MagicMock()
        mock_status_1.name = "postgres"
        mock_status_1.container_id = "docker://1234567890abcdef"
        mock_status_1.restart_count = 0
        mock_pod_info_1.status.container_statuses = [mock_status_1]
        
        mock_kubecli.cli.read_namespaced_pod.return_value = mock_pod_info_1
        mock_kubecli.exec_command_on_node.side_effect = Exception("Node offline")
        
        with self.assertRaises(Exception) as context:
            self.plugin._kill_container_via_node("mypod", "mynamespace", "postgres", mock_kubecli)
            
        self.assertIn("Node offline", str(context.exception))
        
        # Ensure cleanup is still called
        mock_kubecli.delete_pod.assert_called_once_with("krkn-crictl-12345678", "mynamespace")

    @patch("time.sleep")
    def test_crictl_execution_validation_failure(self, mock_sleep):
        """
        Test that exec pod is cleaned up even when validation fails.
        """
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        
        mock_pod_info_1 = MagicMock()
        mock_pod_info_1.spec.node_name = "node-1"
        mock_status_1 = MagicMock()
        mock_status_1.name = "postgres"
        mock_status_1.container_id = "cri-o://1234567890abcdef"
        mock_status_1.restart_count = 0
        mock_status_1.state.terminated = None
        mock_status_1.state.waiting = None
        mock_pod_info_1.status.container_statuses = [mock_status_1]
        
        # Always return the same pod info (restart_count=0) so validation fails after retries
        mock_kubecli.cli.read_namespaced_pod.return_value = mock_pod_info_1
        mock_kubecli.exec_command_on_node.return_value = "crictl stopped"
        
        with self.assertRaises(RuntimeError) as context:
            self.plugin._kill_container_via_node("mypod", "mynamespace", "postgres", mock_kubecli)
            
        self.assertIn("Failed to validate that container postgres was stopped", str(context.exception))
        
        # Ensure cleanup is still called
        mock_kubecli.delete_pod.assert_called_once_with("krkn-crictl-12345678", "mynamespace")

if __name__ == "__main__":
    unittest.main()
