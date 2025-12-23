#!/usr/bin/env python3

"""
Test suite for common_node_functions module

Usage:
    python -m coverage run -a -m unittest tests/test_common_node_functions.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, Mock, patch, call
import logging

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode

from krkn.scenario_plugins.node_actions import common_node_functions


class TestCommonNodeFunctions(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures before each test
        """
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.mock_affected_node = Mock(spec=AffectedNode)

    def test_get_node_by_name_all_nodes_exist(self):
        """
        Test get_node_by_name returns list when all nodes exist
        """
        node_name_list = ["node1", "node2", "node3"]
        self.mock_kubecli.list_killable_nodes.return_value = ["node1", "node2", "node3", "node4"]

        result = common_node_functions.get_node_by_name(node_name_list, self.mock_kubecli)

        self.assertEqual(result, node_name_list)
        self.mock_kubecli.list_killable_nodes.assert_called_once()

    def test_get_node_by_name_single_node(self):
        """
        Test get_node_by_name with single node
        """
        node_name_list = ["worker-1"]
        self.mock_kubecli.list_killable_nodes.return_value = ["worker-1", "worker-2"]

        result = common_node_functions.get_node_by_name(node_name_list, self.mock_kubecli)

        self.assertEqual(result, node_name_list)

    @patch('logging.info')
    def test_get_node_by_name_node_not_exist(self, mock_logging):
        """
        Test get_node_by_name returns None when node doesn't exist
        """
        node_name_list = ["node1", "nonexistent-node"]
        self.mock_kubecli.list_killable_nodes.return_value = ["node1", "node2", "node3"]

        result = common_node_functions.get_node_by_name(node_name_list, self.mock_kubecli)

        self.assertIsNone(result)
        mock_logging.assert_called()
        self.assertIn("does not exist", str(mock_logging.call_args))

    @patch('logging.info')
    def test_get_node_by_name_empty_killable_list(self, mock_logging):
        """
        Test get_node_by_name when no killable nodes exist
        """
        node_name_list = ["node1"]
        self.mock_kubecli.list_killable_nodes.return_value = []

        result = common_node_functions.get_node_by_name(node_name_list, self.mock_kubecli)

        self.assertIsNone(result)
        mock_logging.assert_called()

    @patch('logging.info')
    def test_get_node_single_label_selector(self, mock_logging):
        """
        Test get_node with single label selector
        """
        label_selector = "node-role.kubernetes.io/worker"
        instance_kill_count = 2
        self.mock_kubecli.list_killable_nodes.return_value = ["worker-1", "worker-2", "worker-3"]

        result = common_node_functions.get_node(label_selector, instance_kill_count, self.mock_kubecli)

        self.assertEqual(len(result), 2)
        self.assertTrue(all(node in ["worker-1", "worker-2", "worker-3"] for node in result))
        self.mock_kubecli.list_killable_nodes.assert_called_once_with(label_selector)
        mock_logging.assert_called()

    @patch('logging.info')
    def test_get_node_multiple_label_selectors(self, mock_logging):
        """
        Test get_node with multiple comma-separated label selectors
        """
        label_selector = "node-role.kubernetes.io/worker,topology.kubernetes.io/zone=us-east-1a"
        instance_kill_count = 3
        self.mock_kubecli.list_killable_nodes.side_effect = [
            ["worker-1", "worker-2"],
            ["worker-3", "worker-4"]
        ]

        result = common_node_functions.get_node(label_selector, instance_kill_count, self.mock_kubecli)

        self.assertEqual(len(result), 3)
        self.assertTrue(all(node in ["worker-1", "worker-2", "worker-3", "worker-4"] for node in result))
        self.assertEqual(self.mock_kubecli.list_killable_nodes.call_count, 2)

    @patch('logging.info')
    def test_get_node_return_all_when_count_equals_total(self, mock_logging):
        """
        Test get_node returns all nodes when instance_kill_count equals number of nodes
        """
        label_selector = "node-role.kubernetes.io/worker"
        nodes = ["worker-1", "worker-2", "worker-3"]
        instance_kill_count = 3
        self.mock_kubecli.list_killable_nodes.return_value = nodes

        result = common_node_functions.get_node(label_selector, instance_kill_count, self.mock_kubecli)

        self.assertEqual(result, nodes)

    @patch('logging.info')
    def test_get_node_return_all_when_count_is_zero(self, mock_logging):
        """
        Test get_node returns all nodes when instance_kill_count is 0
        """
        label_selector = "node-role.kubernetes.io/worker"
        nodes = ["worker-1", "worker-2", "worker-3"]
        instance_kill_count = 0
        self.mock_kubecli.list_killable_nodes.return_value = nodes

        result = common_node_functions.get_node(label_selector, instance_kill_count, self.mock_kubecli)

        self.assertEqual(result, nodes)

    @patch('logging.info')
    @patch('random.randint')
    def test_get_node_random_selection(self, mock_randint, mock_logging):
        """
        Test get_node randomly selects nodes when count is less than total
        """
        label_selector = "node-role.kubernetes.io/worker"
        instance_kill_count = 2
        self.mock_kubecli.list_killable_nodes.return_value = ["worker-1", "worker-2", "worker-3", "worker-4"]
        # Mock random selection to return predictable values
        mock_randint.side_effect = [1, 0]  # Select index 1, then index 0

        result = common_node_functions.get_node(label_selector, instance_kill_count, self.mock_kubecli)

        self.assertEqual(len(result), 2)
        # Verify nodes were removed after selection to avoid duplicates
        self.assertEqual(len(set(result)), 2)

    def test_get_node_no_nodes_with_label(self):
        """
        Test get_node raises exception when no nodes match label selector
        """
        label_selector = "nonexistent-label"
        instance_kill_count = 1
        self.mock_kubecli.list_killable_nodes.return_value = []

        with self.assertRaises(Exception) as context:
            common_node_functions.get_node(label_selector, instance_kill_count, self.mock_kubecli)

        self.assertIn("Ready nodes with the provided label selector do not exist", str(context.exception))

    def test_get_node_single_node_available(self):
        """
        Test get_node when only one node is available
        """
        label_selector = "node-role.kubernetes.io/master"
        instance_kill_count = 1
        self.mock_kubecli.list_killable_nodes.return_value = ["master-1"]

        result = common_node_functions.get_node(label_selector, instance_kill_count, self.mock_kubecli)

        self.assertEqual(result, ["master-1"])

    def test_wait_for_ready_status_without_affected_node(self):
        """
        Test wait_for_ready_status without providing affected_node
        """
        node = "test-node"
        timeout = 300
        expected_affected_node = Mock(spec=AffectedNode)
        self.mock_kubecli.watch_node_status.return_value = expected_affected_node

        result = common_node_functions.wait_for_ready_status(node, timeout, self.mock_kubecli)

        self.assertEqual(result, expected_affected_node)
        self.mock_kubecli.watch_node_status.assert_called_once_with(node, "True", timeout, None)

    def test_wait_for_ready_status_with_affected_node(self):
        """
        Test wait_for_ready_status with provided affected_node
        """
        node = "test-node"
        timeout = 300
        self.mock_kubecli.watch_node_status.return_value = self.mock_affected_node

        result = common_node_functions.wait_for_ready_status(
            node, timeout, self.mock_kubecli, self.mock_affected_node
        )

        self.assertEqual(result, self.mock_affected_node)
        self.mock_kubecli.watch_node_status.assert_called_once_with(
            node, "True", timeout, self.mock_affected_node
        )

    def test_wait_for_not_ready_status_without_affected_node(self):
        """
        Test wait_for_not_ready_status without providing affected_node
        """
        node = "test-node"
        timeout = 300
        expected_affected_node = Mock(spec=AffectedNode)
        self.mock_kubecli.watch_node_status.return_value = expected_affected_node

        result = common_node_functions.wait_for_not_ready_status(node, timeout, self.mock_kubecli)

        self.assertEqual(result, expected_affected_node)
        self.mock_kubecli.watch_node_status.assert_called_once_with(node, "False", timeout, None)

    def test_wait_for_not_ready_status_with_affected_node(self):
        """
        Test wait_for_not_ready_status with provided affected_node
        """
        node = "test-node"
        timeout = 300
        self.mock_kubecli.watch_node_status.return_value = self.mock_affected_node

        result = common_node_functions.wait_for_not_ready_status(
            node, timeout, self.mock_kubecli, self.mock_affected_node
        )

        self.assertEqual(result, self.mock_affected_node)
        self.mock_kubecli.watch_node_status.assert_called_once_with(
            node, "False", timeout, self.mock_affected_node
        )

    def test_wait_for_unknown_status_without_affected_node(self):
        """
        Test wait_for_unknown_status without providing affected_node
        """
        node = "test-node"
        timeout = 300
        expected_affected_node = Mock(spec=AffectedNode)
        self.mock_kubecli.watch_node_status.return_value = expected_affected_node

        result = common_node_functions.wait_for_unknown_status(node, timeout, self.mock_kubecli)

        self.assertEqual(result, expected_affected_node)
        self.mock_kubecli.watch_node_status.assert_called_once_with(node, "Unknown", timeout, None)

    def test_wait_for_unknown_status_with_affected_node(self):
        """
        Test wait_for_unknown_status with provided affected_node
        """
        node = "test-node"
        timeout = 300
        self.mock_kubecli.watch_node_status.return_value = self.mock_affected_node

        result = common_node_functions.wait_for_unknown_status(
            node, timeout, self.mock_kubecli, self.mock_affected_node
        )

        self.assertEqual(result, self.mock_affected_node)
        self.mock_kubecli.watch_node_status.assert_called_once_with(
            node, "Unknown", timeout, self.mock_affected_node
        )

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.paramiko.SSHClient')
    def test_check_service_status_success(self, mock_ssh_client, mock_logging, mock_sleep):
        """
        Test check_service_status successfully checks service status
        """
        node = "192.168.1.100"
        service = ["neutron-server", "nova-compute"]
        ssh_private_key = "~/.ssh/id_rsa"
        timeout = 60

        # Mock SSH client
        mock_ssh = Mock()
        mock_ssh_client.return_value = mock_ssh
        mock_ssh.connect.return_value = None

        # Mock exec_command to return active status
        mock_stdout = Mock()
        mock_stdout.readlines.return_value = ["active\n"]
        mock_ssh.exec_command.return_value = (Mock(), mock_stdout, Mock())

        common_node_functions.check_service_status(node, service, ssh_private_key, timeout)

        # Verify SSH connection was attempted
        mock_ssh.connect.assert_called()
        # Verify service status was checked for each service
        self.assertEqual(mock_ssh.exec_command.call_count, 2)
        # Verify SSH connection was closed
        mock_ssh.close.assert_called_once()

    @patch('time.sleep')
    @patch('logging.error')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.paramiko.SSHClient')
    def test_check_service_status_service_inactive(self, mock_ssh_client, mock_logging_info, mock_logging_error, mock_sleep):
        """
        Test check_service_status logs error when service is inactive
        """
        node = "192.168.1.100"
        service = ["neutron-server"]
        ssh_private_key = "~/.ssh/id_rsa"
        timeout = 60

        # Mock SSH client
        mock_ssh = Mock()
        mock_ssh_client.return_value = mock_ssh
        mock_ssh.connect.return_value = None

        # Mock exec_command to return inactive status
        mock_stdout = Mock()
        mock_stdout.readlines.return_value = ["inactive\n"]
        mock_ssh.exec_command.return_value = (Mock(), mock_stdout, Mock())

        common_node_functions.check_service_status(node, service, ssh_private_key, timeout)

        # Verify error was logged for inactive service
        mock_logging_error.assert_called()
        error_call_str = str(mock_logging_error.call_args)
        self.assertIn("inactive", error_call_str)
        mock_ssh.close.assert_called_once()

    @patch('time.sleep')
    @patch('logging.error')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.paramiko.SSHClient')
    def test_check_service_status_ssh_connection_fails(self, mock_ssh_client, mock_logging_info, mock_logging_error, mock_sleep):
        """
        Test check_service_status handles SSH connection failures
        """
        node = "192.168.1.100"
        service = ["neutron-server"]
        ssh_private_key = "~/.ssh/id_rsa"
        timeout = 5

        # Mock SSH client to raise exception
        mock_ssh = Mock()
        mock_ssh_client.return_value = mock_ssh
        mock_ssh.connect.side_effect = Exception("Connection timeout")

        # Mock exec_command for when connection eventually works (or doesn't)
        mock_stdout = Mock()
        mock_stdout.readlines.return_value = ["active\n"]
        mock_ssh.exec_command.return_value = (Mock(), mock_stdout, Mock())

        common_node_functions.check_service_status(node, service, ssh_private_key, timeout)

        # Verify error was logged for SSH connection failure
        mock_logging_error.assert_called()
        error_call_str = str(mock_logging_error.call_args)
        self.assertIn("Failed to ssh", error_call_str)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.paramiko.SSHClient')
    def test_check_service_status_multiple_services(self, mock_ssh_client, mock_logging, mock_sleep):
        """
        Test check_service_status with multiple services
        """
        node = "192.168.1.100"
        service = ["service1", "service2", "service3"]
        ssh_private_key = "~/.ssh/id_rsa"
        timeout = 60

        # Mock SSH client
        mock_ssh = Mock()
        mock_ssh_client.return_value = mock_ssh
        mock_ssh.connect.return_value = None

        # Mock exec_command to return active status
        mock_stdout = Mock()
        mock_stdout.readlines.return_value = ["active\n"]
        mock_ssh.exec_command.return_value = (Mock(), mock_stdout, Mock())

        common_node_functions.check_service_status(node, service, ssh_private_key, timeout)

        # Verify service status was checked for all services
        self.assertEqual(mock_ssh.exec_command.call_count, 3)
        mock_ssh.close.assert_called_once()

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.paramiko.SSHClient')
    def test_check_service_status_retry_logic(self, mock_ssh_client, mock_logging, mock_sleep):
        """
        Test check_service_status retry logic on connection failure then success
        """
        node = "192.168.1.100"
        service = ["neutron-server"]
        ssh_private_key = "~/.ssh/id_rsa"
        timeout = 10

        # Mock SSH client
        mock_ssh = Mock()
        mock_ssh_client.return_value = mock_ssh
        # First two attempts fail, third succeeds
        mock_ssh.connect.side_effect = [
            Exception("Timeout"),
            Exception("Timeout"),
            None  # Success
        ]

        # Mock exec_command
        mock_stdout = Mock()
        mock_stdout.readlines.return_value = ["active\n"]
        mock_ssh.exec_command.return_value = (Mock(), mock_stdout, Mock())

        common_node_functions.check_service_status(node, service, ssh_private_key, timeout)

        # Verify multiple connection attempts were made
        self.assertGreater(mock_ssh.connect.call_count, 1)
        # Verify service was eventually checked
        mock_ssh.exec_command.assert_called()
        mock_ssh.close.assert_called_once()


class TestCommonNodeFunctionsIntegration(unittest.TestCase):
    """Integration-style tests for common_node_functions"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_kubecli = Mock(spec=KrknKubernetes)

    @patch('logging.info')
    def test_get_node_workflow_with_label_filtering(self, mock_logging):
        """
        Test complete workflow of getting nodes with label selector and filtering
        """
        label_selector = "node-role.kubernetes.io/worker"
        instance_kill_count = 2
        available_nodes = ["worker-1", "worker-2", "worker-3", "worker-4", "worker-5"]
        self.mock_kubecli.list_killable_nodes.return_value = available_nodes

        result = common_node_functions.get_node(label_selector, instance_kill_count, self.mock_kubecli)

        self.assertEqual(len(result), 2)
        # Verify no duplicates
        self.assertEqual(len(result), len(set(result)))
        # Verify all nodes are from the available list
        self.assertTrue(all(node in available_nodes for node in result))

    @patch('logging.info')
    def test_get_node_by_name_validation_workflow(self, mock_logging):
        """
        Test complete workflow of validating node names
        """
        requested_nodes = ["node-a", "node-b"]
        killable_nodes = ["node-a", "node-b", "node-c", "node-d"]
        self.mock_kubecli.list_killable_nodes.return_value = killable_nodes

        result = common_node_functions.get_node_by_name(requested_nodes, self.mock_kubecli)

        self.assertEqual(result, requested_nodes)
        self.mock_kubecli.list_killable_nodes.assert_called_once()


if __name__ == "__main__":
    unittest.main()
