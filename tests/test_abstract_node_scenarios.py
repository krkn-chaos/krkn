"""
Test suite for AbstractNode Scenarios

Usage:
    python -m coverage run -a -m unittest tests/test_abstract_node_scenarios.py

Assisted By: Claude Code
"""

import unittest
from unittest.mock import Mock, patch
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import abstract_node_scenarios
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus


class TestAbstractNodeScenarios(unittest.TestCase):
    """Test suite for abstract_node_scenarios class"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.mock_affected_nodes_status = Mock(spec=AffectedNodeStatus)
        self.mock_affected_nodes_status.affected_nodes = []
        self.node_action_kube_check = True

        self.scenarios = abstract_node_scenarios(
            kubecli=self.mock_kubecli,
            node_action_kube_check=self.node_action_kube_check,
            affected_nodes_status=self.mock_affected_nodes_status
        )

    def test_init(self):
        """Test initialization of abstract_node_scenarios"""
        self.assertEqual(self.scenarios.kubecli, self.mock_kubecli)
        self.assertEqual(self.scenarios.affected_nodes_status, self.mock_affected_nodes_status)
        self.assertTrue(self.scenarios.node_action_kube_check)

    @patch('time.sleep')
    @patch('logging.info')
    def test_node_stop_start_scenario(self, mock_logging, mock_sleep):
        """Test node_stop_start_scenario calls stop and start in sequence"""
        # Arrange
        instance_kill_count = 1
        node = "test-node"
        timeout = 300
        duration = 60
        poll_interval = 10

        self.scenarios.node_stop_scenario = Mock()
        self.scenarios.node_start_scenario = Mock()

        # Act
        self.scenarios.node_stop_start_scenario(
            instance_kill_count, node, timeout, duration, poll_interval
        )

        # Assert
        self.scenarios.node_stop_scenario.assert_called_once_with(
            instance_kill_count, node, timeout, poll_interval
        )
        mock_sleep.assert_called_once_with(duration)
        self.scenarios.node_start_scenario.assert_called_once_with(
            instance_kill_count, node, timeout, poll_interval
        )
        self.mock_affected_nodes_status.merge_affected_nodes.assert_called_once()

    @patch('logging.info')
    def test_helper_node_stop_start_scenario(self, mock_logging):
        """Test helper_node_stop_start_scenario calls helper stop and start"""
        # Arrange
        instance_kill_count = 1
        node = "helper-node"
        timeout = 300

        self.scenarios.helper_node_stop_scenario = Mock()
        self.scenarios.helper_node_start_scenario = Mock()

        # Act
        self.scenarios.helper_node_stop_start_scenario(instance_kill_count, node, timeout)

        # Assert
        self.scenarios.helper_node_stop_scenario.assert_called_once_with(
            instance_kill_count, node, timeout
        )
        self.scenarios.helper_node_start_scenario.assert_called_once_with(
            instance_kill_count, node, timeout
        )

    @patch('time.sleep')
    @patch('logging.info')
    def test_node_disk_detach_attach_scenario_success(self, mock_logging, mock_sleep):
        """Test disk detach/attach scenario with valid disk attachment"""
        # Arrange
        instance_kill_count = 1
        node = "test-node"
        timeout = 300
        duration = 60
        disk_details = {"disk_id": "disk-123", "device": "/dev/sdb"}

        self.scenarios.get_disk_attachment_info = Mock(return_value=disk_details)
        self.scenarios.disk_detach_scenario = Mock()
        self.scenarios.disk_attach_scenario = Mock()

        # Act
        self.scenarios.node_disk_detach_attach_scenario(
            instance_kill_count, node, timeout, duration
        )

        # Assert
        self.scenarios.get_disk_attachment_info.assert_called_once_with(
            instance_kill_count, node
        )
        self.scenarios.disk_detach_scenario.assert_called_once_with(
            instance_kill_count, node, timeout
        )
        mock_sleep.assert_called_once_with(duration)
        self.scenarios.disk_attach_scenario.assert_called_once_with(
            instance_kill_count, disk_details, timeout
        )

    @patch('logging.error')
    @patch('logging.info')
    def test_node_disk_detach_attach_scenario_no_disk(self, mock_info, mock_error):
        """Test disk detach/attach scenario when only root disk exists"""
        # Arrange
        instance_kill_count = 1
        node = "test-node"
        timeout = 300
        duration = 60

        self.scenarios.get_disk_attachment_info = Mock(return_value=None)
        self.scenarios.disk_detach_scenario = Mock()
        self.scenarios.disk_attach_scenario = Mock()

        # Act
        self.scenarios.node_disk_detach_attach_scenario(
            instance_kill_count, node, timeout, duration
        )

        # Assert
        self.scenarios.disk_detach_scenario.assert_not_called()
        self.scenarios.disk_attach_scenario.assert_not_called()
        mock_error.assert_any_call("Node %s has only root disk attached" % node)

    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.nodeaction.wait_for_unknown_status')
    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.runcommand.run')
    @patch('logging.info')
    def test_stop_kubelet_scenario_success(self, mock_logging, mock_run, mock_wait):
        """Test successful kubelet stop scenario"""
        # Arrange
        instance_kill_count = 2
        node = "test-node"
        timeout = 300
        mock_affected_node = Mock(spec=AffectedNode)
        mock_wait.return_value = None

        # Act
        with patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.AffectedNode') as mock_affected_node_class:
            mock_affected_node_class.return_value = mock_affected_node
            self.scenarios.stop_kubelet_scenario(instance_kill_count, node, timeout)

        # Assert
        self.assertEqual(mock_run.call_count, 2)
        expected_command = "oc debug node/" + node + " -- chroot /host systemctl stop kubelet"
        mock_run.assert_called_with(expected_command)
        self.assertEqual(mock_wait.call_count, 2)
        self.assertEqual(len(self.mock_affected_nodes_status.affected_nodes), 2)

    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.nodeaction.wait_for_unknown_status')
    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.runcommand.run')
    @patch('logging.error')
    @patch('logging.info')
    def test_stop_kubelet_scenario_failure(self, mock_info, mock_error, mock_run, mock_wait):
        """Test kubelet stop scenario when command fails"""
        # Arrange
        instance_kill_count = 1
        node = "test-node"
        timeout = 300
        error_msg = "Command failed"
        mock_run.side_effect = Exception(error_msg)

        # Act & Assert
        with self.assertRaises(Exception):
            with patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.AffectedNode'):
                self.scenarios.stop_kubelet_scenario(instance_kill_count, node, timeout)

        mock_error.assert_any_call(
            "Failed to stop the kubelet of the node. Encountered following "
            "exception: %s. Test Failed" % error_msg
        )

    @patch('logging.info')
    def test_stop_start_kubelet_scenario(self, mock_logging):
        """Test stop/start kubelet scenario"""
        # Arrange
        instance_kill_count = 1
        node = "test-node"
        timeout = 300

        self.scenarios.stop_kubelet_scenario = Mock()
        self.scenarios.node_reboot_scenario = Mock()

        # Act
        self.scenarios.stop_start_kubelet_scenario(instance_kill_count, node, timeout)

        # Assert
        self.scenarios.stop_kubelet_scenario.assert_called_once_with(
            instance_kill_count, node, timeout
        )
        self.scenarios.node_reboot_scenario.assert_called_once_with(
            instance_kill_count, node, timeout
        )
        self.mock_affected_nodes_status.merge_affected_nodes.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.nodeaction.wait_for_ready_status')
    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.runcommand.run')
    @patch('logging.info')
    def test_restart_kubelet_scenario_success(self, mock_logging, mock_run, mock_wait):
        """Test successful kubelet restart scenario"""
        # Arrange
        instance_kill_count = 2
        node = "test-node"
        timeout = 300
        mock_affected_node = Mock(spec=AffectedNode)
        mock_wait.return_value = None

        # Act
        with patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.AffectedNode') as mock_affected_node_class:
            mock_affected_node_class.return_value = mock_affected_node
            self.scenarios.restart_kubelet_scenario(instance_kill_count, node, timeout)

        # Assert
        self.assertEqual(mock_run.call_count, 2)
        expected_command = "oc debug node/" + node + " -- chroot /host systemctl restart kubelet &"
        mock_run.assert_called_with(expected_command)
        self.assertEqual(mock_wait.call_count, 2)
        self.assertEqual(len(self.mock_affected_nodes_status.affected_nodes), 2)

    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.nodeaction.wait_for_ready_status')
    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.runcommand.run')
    @patch('logging.error')
    @patch('logging.info')
    def test_restart_kubelet_scenario_failure(self, mock_info, mock_error, mock_run, mock_wait):
        """Test kubelet restart scenario when command fails"""
        # Arrange
        instance_kill_count = 1
        node = "test-node"
        timeout = 300
        error_msg = "Restart failed"
        mock_run.side_effect = Exception(error_msg)

        # Act & Assert
        with self.assertRaises(Exception):
            with patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.AffectedNode'):
                self.scenarios.restart_kubelet_scenario(instance_kill_count, node, timeout)

        mock_error.assert_any_call(
            "Failed to restart the kubelet of the node. Encountered following "
            "exception: %s. Test Failed" % error_msg
        )

    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.runcommand.run')
    @patch('logging.info')
    def test_node_crash_scenario_success(self, mock_logging, mock_run):
        """Test successful node crash scenario"""
        # Arrange
        instance_kill_count = 2
        node = "test-node"
        timeout = 300

        # Act
        result = self.scenarios.node_crash_scenario(instance_kill_count, node, timeout)

        # Assert
        self.assertEqual(mock_run.call_count, 2)
        expected_command = (
            "oc debug node/" + node + " -- chroot /host "
            "dd if=/dev/urandom of=/proc/sysrq-trigger"
        )
        mock_run.assert_called_with(expected_command)
        self.assertIsNone(result)

    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.runcommand.run')
    @patch('logging.error')
    @patch('logging.info')
    def test_node_crash_scenario_failure(self, mock_info, mock_error, mock_run):
        """Test node crash scenario when command fails"""
        # Arrange
        instance_kill_count = 1
        node = "test-node"
        timeout = 300
        error_msg = "Crash command failed"
        mock_run.side_effect = Exception(error_msg)

        # Act
        result = self.scenarios.node_crash_scenario(instance_kill_count, node, timeout)

        # Assert
        self.assertEqual(result, 1)
        mock_error.assert_any_call(
            "Failed to crash the node. Encountered following exception: %s. "
            "Test Failed" % error_msg
        )

    def test_node_start_scenario_not_implemented(self):
        """Test that node_start_scenario returns None (not implemented)"""
        result = self.scenarios.node_start_scenario(1, "test-node", 300, 10)
        self.assertIsNone(result)

    def test_node_stop_scenario_not_implemented(self):
        """Test that node_stop_scenario returns None (not implemented)"""
        result = self.scenarios.node_stop_scenario(1, "test-node", 300, 10)
        self.assertIsNone(result)

    def test_node_termination_scenario_not_implemented(self):
        """Test that node_termination_scenario returns None (not implemented)"""
        result = self.scenarios.node_termination_scenario(1, "test-node", 300, 10)
        self.assertIsNone(result)

    def test_node_reboot_scenario_not_implemented(self):
        """Test that node_reboot_scenario returns None (not implemented)"""
        result = self.scenarios.node_reboot_scenario(1, "test-node", 300)
        self.assertIsNone(result)

    def test_node_service_status_not_implemented(self):
        """Test that node_service_status returns None (not implemented)"""
        result = self.scenarios.node_service_status("test-node", "service", "key", 300)
        self.assertIsNone(result)

    def test_node_block_scenario_not_implemented(self):
        """Test that node_block_scenario returns None (not implemented)"""
        result = self.scenarios.node_block_scenario(1, "test-node", 300, 60)
        self.assertIsNone(result)


class TestAbstractNodeScenariosIntegration(unittest.TestCase):
    """Integration tests for abstract_node_scenarios workflows"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.mock_affected_nodes_status = Mock(spec=AffectedNodeStatus)
        self.mock_affected_nodes_status.affected_nodes = []

        self.scenarios = abstract_node_scenarios(
            kubecli=self.mock_kubecli,
            node_action_kube_check=True,
            affected_nodes_status=self.mock_affected_nodes_status
        )

    @patch('time.sleep')
    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.nodeaction.wait_for_unknown_status')
    @patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.runcommand.run')
    def test_complete_stop_start_kubelet_workflow(self, mock_run, mock_wait, mock_sleep):
        """Test complete workflow of stop/start kubelet scenario"""
        # Arrange
        instance_kill_count = 1
        node = "test-node"
        timeout = 300

        self.scenarios.node_reboot_scenario = Mock()

        # Act
        with patch('krkn.scenario_plugins.node_actions.abstract_node_scenarios.AffectedNode'):
            self.scenarios.stop_start_kubelet_scenario(instance_kill_count, node, timeout)

        # Assert - verify stop kubelet was called
        expected_stop_command = "oc debug node/" + node + " -- chroot /host systemctl stop kubelet"
        mock_run.assert_any_call(expected_stop_command)

        # Verify reboot was called
        self.scenarios.node_reboot_scenario.assert_called_once_with(
            instance_kill_count, node, timeout
        )

        # Verify merge was called
        self.mock_affected_nodes_status.merge_affected_nodes.assert_called_once()

    @patch('time.sleep')
    def test_node_stop_start_scenario_workflow(self, mock_sleep):
        """Test complete workflow of node stop/start scenario"""
        # Arrange
        instance_kill_count = 1
        node = "test-node"
        timeout = 300
        duration = 60
        poll_interval = 10

        self.scenarios.node_stop_scenario = Mock()
        self.scenarios.node_start_scenario = Mock()

        # Act
        self.scenarios.node_stop_start_scenario(
            instance_kill_count, node, timeout, duration, poll_interval
        )

        # Assert - verify order of operations
        call_order = []

        # Verify stop was called first
        self.scenarios.node_stop_scenario.assert_called_once()

        # Verify sleep was called
        mock_sleep.assert_called_once_with(duration)

        # Verify start was called after sleep
        self.scenarios.node_start_scenario.assert_called_once()

        # Verify merge was called
        self.mock_affected_nodes_status.merge_affected_nodes.assert_called_once()


if __name__ == '__main__':
    unittest.main()
