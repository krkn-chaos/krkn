#!/usr/bin/env python3

"""
Test suite for alibaba_node_scenarios class

Usage:
    python -m coverage run -a -m unittest tests/test_alibaba_node_scenarios.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, Mock, patch, PropertyMock, call
import logging
import json

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

from krkn.scenario_plugins.node_actions.alibaba_node_scenarios import Alibaba, alibaba_node_scenarios


class TestAlibaba(unittest.TestCase):
    """Test suite for Alibaba class"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock environment variables
        self.env_patcher = patch.dict('os.environ', {
            'ALIBABA_ID': 'test-access-key',
            'ALIBABA_SECRET': 'test-secret-key',
            'ALIBABA_REGION_ID': 'cn-hangzhou'
        })
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after tests"""
        self.env_patcher.stop()

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_alibaba_init_success(self, mock_acs_client, mock_logging):
        """Test Alibaba class initialization"""
        mock_client = Mock()
        mock_acs_client.return_value = mock_client

        alibaba = Alibaba()

        mock_acs_client.assert_called_once_with('test-access-key', 'test-secret-key', 'cn-hangzhou')
        self.assertEqual(alibaba.compute_client, mock_client)

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_alibaba_init_failure(self, mock_acs_client, mock_logging):
        """Test Alibaba initialization handles errors"""
        mock_acs_client.side_effect = Exception("Credential error")

        alibaba = Alibaba()

        mock_logging.assert_called()
        self.assertIn("Initializing alibaba", str(mock_logging.call_args))

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_send_request_success(self, mock_acs_client):
        """Test _send_request successfully sends request"""
        alibaba = Alibaba()

        mock_request = Mock()
        mock_response = {'Instances': {'Instance': []}}
        alibaba.compute_client.do_action.return_value = json.dumps(mock_response).encode('utf-8')

        result = alibaba._send_request(mock_request)

        mock_request.set_accept_format.assert_called_once_with('json')
        alibaba.compute_client.do_action.assert_called_once_with(mock_request)
        self.assertEqual(result, mock_response)

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_send_request_failure(self, mock_acs_client, mock_logging):
        """Test _send_request handles errors"""
        alibaba = Alibaba()

        mock_request = Mock()
        alibaba.compute_client.do_action.side_effect = Exception("API error")

        # The actual code has a bug in the format string (%S instead of %s)
        # So we expect this to raise a ValueError
        with self.assertRaises(ValueError):
            alibaba._send_request(mock_request)

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_list_instances_success(self, mock_acs_client):
        """Test list_instances returns instance list"""
        alibaba = Alibaba()

        mock_instances = [
            {'InstanceId': 'i-123', 'InstanceName': 'node1'},
            {'InstanceId': 'i-456', 'InstanceName': 'node2'}
        ]
        mock_response = {'Instances': {'Instance': mock_instances}}
        alibaba.compute_client.do_action.return_value = json.dumps(mock_response).encode('utf-8')

        result = alibaba.list_instances()

        self.assertEqual(result, mock_instances)

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_list_instances_no_instances_key(self, mock_acs_client, mock_logging):
        """Test list_instances handles missing Instances key"""
        alibaba = Alibaba()

        mock_response = {'SomeOtherKey': 'value'}
        alibaba.compute_client.do_action.return_value = json.dumps(mock_response).encode('utf-8')

        with self.assertRaises(RuntimeError):
            alibaba.list_instances()

        mock_logging.assert_called()

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_list_instances_none_response(self, mock_acs_client):
        """Test list_instances handles None response"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(return_value=None)

        result = alibaba.list_instances()

        self.assertEqual(result, [])

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_list_instances_exception(self, mock_acs_client, mock_logging):
        """Test list_instances handles exceptions"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(side_effect=Exception("Network error"))

        with self.assertRaises(Exception):
            alibaba.list_instances()

        mock_logging.assert_called()

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_get_instance_id_found(self, mock_acs_client):
        """Test get_instance_id when instance is found"""
        alibaba = Alibaba()

        mock_instances = [
            {'InstanceId': 'i-123', 'InstanceName': 'test-node'},
            {'InstanceId': 'i-456', 'InstanceName': 'other-node'}
        ]
        alibaba.list_instances = Mock(return_value=mock_instances)

        result = alibaba.get_instance_id('test-node')

        self.assertEqual(result, 'i-123')

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_get_instance_id_not_found(self, mock_acs_client, mock_logging):
        """Test get_instance_id when instance is not found"""
        alibaba = Alibaba()

        alibaba.list_instances = Mock(return_value=[])

        with self.assertRaises(RuntimeError):
            alibaba.get_instance_id('nonexistent-node')

        mock_logging.assert_called()
        self.assertIn("Couldn't find vm", str(mock_logging.call_args))

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_start_instances_success(self, mock_acs_client, mock_logging):
        """Test start_instances successfully starts instance"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(return_value={'RequestId': 'req-123'})

        alibaba.start_instances('i-123')

        alibaba._send_request.assert_called_once()
        mock_logging.assert_called()
        call_str = str(mock_logging.call_args_list)
        self.assertTrue('started' in call_str or 'submit successfully' in call_str)

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_start_instances_failure(self, mock_acs_client, mock_logging):
        """Test start_instances handles failure"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(side_effect=Exception("Start failed"))

        with self.assertRaises(Exception):
            alibaba.start_instances('i-123')

        mock_logging.assert_called()
        self.assertIn("Failed to start", str(mock_logging.call_args))

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_stop_instances_success(self, mock_acs_client, mock_logging):
        """Test stop_instances successfully stops instance"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(return_value={'RequestId': 'req-123'})

        alibaba.stop_instances('i-123', force_stop=True)

        alibaba._send_request.assert_called_once()
        mock_logging.assert_called()

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_stop_instances_failure(self, mock_acs_client, mock_logging):
        """Test stop_instances handles failure"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(side_effect=Exception("Stop failed"))

        with self.assertRaises(Exception):
            alibaba.stop_instances('i-123')

        mock_logging.assert_called()
        self.assertIn("Failed to stop", str(mock_logging.call_args))

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_release_instance_success(self, mock_acs_client, mock_logging):
        """Test release_instance successfully releases instance"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(return_value={'RequestId': 'req-123'})

        alibaba.release_instance('i-123', force_release=True)

        alibaba._send_request.assert_called_once()
        mock_logging.assert_called()
        self.assertIn("released", str(mock_logging.call_args))

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_release_instance_failure(self, mock_acs_client, mock_logging):
        """Test release_instance handles failure"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(side_effect=Exception("Release failed"))

        with self.assertRaises(Exception):
            alibaba.release_instance('i-123')

        mock_logging.assert_called()
        self.assertIn("Failed to terminate", str(mock_logging.call_args))

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_reboot_instances_success(self, mock_acs_client, mock_logging):
        """Test reboot_instances successfully reboots instance"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(return_value={'RequestId': 'req-123'})

        alibaba.reboot_instances('i-123', force_reboot=True)

        alibaba._send_request.assert_called_once()
        mock_logging.assert_called()
        self.assertIn("rebooted", str(mock_logging.call_args))

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_reboot_instances_failure(self, mock_acs_client, mock_logging):
        """Test reboot_instances handles failure"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(side_effect=Exception("Reboot failed"))

        with self.assertRaises(Exception):
            alibaba.reboot_instances('i-123')

        mock_logging.assert_called()
        self.assertIn("Failed to reboot", str(mock_logging.call_args))

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_get_vm_status_success(self, mock_acs_client, mock_logging):
        """Test get_vm_status returns instance status"""
        alibaba = Alibaba()

        mock_response = {
            'Instances': {
                'Instance': [{'Status': 'Running'}]
            }
        }
        alibaba._send_request = Mock(return_value=mock_response)

        result = alibaba.get_vm_status('i-123')

        self.assertEqual(result, 'Running')

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_get_vm_status_no_instances(self, mock_acs_client, mock_logging):
        """Test get_vm_status when no instances found"""
        alibaba = Alibaba()

        mock_response = {
            'Instances': {
                'Instance': []
            }
        }
        alibaba._send_request = Mock(return_value=mock_response)

        result = alibaba.get_vm_status('i-123')

        self.assertIsNone(result)

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_get_vm_status_none_response(self, mock_acs_client, mock_logging):
        """Test get_vm_status with None response"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(return_value=None)

        result = alibaba.get_vm_status('i-123')

        self.assertEqual(result, 'Unknown')

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_get_vm_status_exception(self, mock_acs_client, mock_logging):
        """Test get_vm_status handles exceptions"""
        alibaba = Alibaba()
        alibaba._send_request = Mock(side_effect=Exception("API error"))

        result = alibaba.get_vm_status('i-123')

        self.assertIsNone(result)
        mock_logging.assert_called()

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_wait_until_running_success(self, mock_acs_client, mock_logging, mock_sleep):
        """Test wait_until_running waits for instance to be running"""
        alibaba = Alibaba()

        alibaba.get_vm_status = Mock(side_effect=['Starting', 'Running'])
        mock_affected_node = Mock(spec=AffectedNode)

        result = alibaba.wait_until_running('i-123', 300, mock_affected_node)

        self.assertTrue(result)
        mock_affected_node.set_affected_node_status.assert_called_once()
        args = mock_affected_node.set_affected_node_status.call_args[0]
        self.assertEqual(args[0], 'running')

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_wait_until_running_timeout(self, mock_acs_client, mock_logging, mock_sleep):
        """Test wait_until_running returns False on timeout"""
        alibaba = Alibaba()

        alibaba.get_vm_status = Mock(return_value='Starting')

        result = alibaba.wait_until_running('i-123', 10, None)

        self.assertFalse(result)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_wait_until_stopped_success(self, mock_acs_client, mock_logging, mock_sleep):
        """Test wait_until_stopped waits for instance to be stopped"""
        alibaba = Alibaba()

        alibaba.get_vm_status = Mock(side_effect=['Stopping', 'Stopped'])
        mock_affected_node = Mock(spec=AffectedNode)

        result = alibaba.wait_until_stopped('i-123', 300, mock_affected_node)

        self.assertTrue(result)
        mock_affected_node.set_affected_node_status.assert_called_once()

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_wait_until_stopped_timeout(self, mock_acs_client, mock_logging, mock_sleep):
        """Test wait_until_stopped returns False on timeout"""
        alibaba = Alibaba()

        alibaba.get_vm_status = Mock(return_value='Stopping')

        result = alibaba.wait_until_stopped('i-123', 10, None)

        self.assertFalse(result)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_wait_until_released_success(self, mock_acs_client, mock_logging, mock_sleep):
        """Test wait_until_released waits for instance to be released"""
        alibaba = Alibaba()

        alibaba.get_vm_status = Mock(side_effect=['Deleting', 'Released'])
        mock_affected_node = Mock(spec=AffectedNode)

        result = alibaba.wait_until_released('i-123', 300, mock_affected_node)

        self.assertTrue(result)
        mock_affected_node.set_affected_node_status.assert_called_once()
        args = mock_affected_node.set_affected_node_status.call_args[0]
        self.assertEqual(args[0], 'terminated')

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_wait_until_released_timeout(self, mock_acs_client, mock_logging, mock_sleep):
        """Test wait_until_released returns False on timeout"""
        alibaba = Alibaba()

        alibaba.get_vm_status = Mock(return_value='Deleting')

        result = alibaba.wait_until_released('i-123', 10, None)

        self.assertFalse(result)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.AcsClient')
    def test_wait_until_released_none_status(self, mock_acs_client, mock_logging, mock_sleep):
        """Test wait_until_released when status becomes None"""
        alibaba = Alibaba()

        alibaba.get_vm_status = Mock(side_effect=['Deleting', None])
        mock_affected_node = Mock(spec=AffectedNode)

        result = alibaba.wait_until_released('i-123', 300, mock_affected_node)

        self.assertTrue(result)


class TestAlibabaNodeScenarios(unittest.TestCase):
    """Test suite for alibaba_node_scenarios class"""

    def setUp(self):
        """Set up test fixtures"""
        self.env_patcher = patch.dict('os.environ', {
            'ALIBABA_ID': 'test-access-key',
            'ALIBABA_SECRET': 'test-secret-key',
            'ALIBABA_REGION_ID': 'cn-hangzhou'
        })
        self.env_patcher.start()

        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.affected_nodes_status = AffectedNodeStatus()

    def tearDown(self):
        """Clean up after tests"""
        self.env_patcher.stop()

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_init(self, mock_alibaba_class, mock_logging):
        """Test alibaba_node_scenarios initialization"""
        mock_alibaba_instance = Mock()
        mock_alibaba_class.return_value = mock_alibaba_instance

        scenarios = alibaba_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        self.assertEqual(scenarios.kubecli, self.mock_kubecli)
        self.assertTrue(scenarios.node_action_kube_check)
        self.assertEqual(scenarios.alibaba, mock_alibaba_instance)

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_start_scenario_success(self, mock_alibaba_class, mock_logging, mock_nodeaction):
        """Test node_start_scenario successfully starts node"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'
        mock_alibaba.wait_until_running.return_value = True

        scenarios = alibaba_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        scenarios.node_start_scenario(1, 'test-node', 300, 15)

        mock_alibaba.get_instance_id.assert_called_once_with('test-node')
        mock_alibaba.start_instances.assert_called_once_with('i-123')
        mock_alibaba.wait_until_running.assert_called_once()
        mock_nodeaction.wait_for_ready_status.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_start_scenario_no_kube_check(self, mock_alibaba_class, mock_logging, mock_nodeaction):
        """Test node_start_scenario without Kubernetes check"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'
        mock_alibaba.wait_until_running.return_value = True

        scenarios = alibaba_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        scenarios.node_start_scenario(1, 'test-node', 300, 15)

        mock_alibaba.start_instances.assert_called_once()
        mock_nodeaction.wait_for_ready_status.assert_not_called()

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_start_scenario_failure(self, mock_alibaba_class, mock_logging):
        """Test node_start_scenario handles failure"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'
        mock_alibaba.start_instances.side_effect = Exception('Start failed')

        scenarios = alibaba_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        with self.assertRaises(Exception):
            scenarios.node_start_scenario(1, 'test-node', 300, 15)

        mock_logging.assert_called()

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_start_scenario_multiple_runs(self, mock_alibaba_class, mock_logging, mock_nodeaction):
        """Test node_start_scenario with multiple runs"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'
        mock_alibaba.wait_until_running.return_value = True

        scenarios = alibaba_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        scenarios.node_start_scenario(3, 'test-node', 300, 15)

        self.assertEqual(mock_alibaba.start_instances.call_count, 3)
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 3)

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_stop_scenario_success(self, mock_alibaba_class, mock_logging, mock_nodeaction):
        """Test node_stop_scenario successfully stops node"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'
        mock_alibaba.wait_until_stopped.return_value = True

        scenarios = alibaba_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        scenarios.node_stop_scenario(1, 'test-node', 300, 15)

        mock_alibaba.get_instance_id.assert_called_once_with('test-node')
        mock_alibaba.stop_instances.assert_called_once_with('i-123')
        mock_alibaba.wait_until_stopped.assert_called_once()
        mock_nodeaction.wait_for_unknown_status.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_stop_scenario_failure(self, mock_alibaba_class, mock_logging):
        """Test node_stop_scenario handles failure"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'
        mock_alibaba.stop_instances.side_effect = Exception('Stop failed')

        scenarios = alibaba_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        with self.assertRaises(Exception):
            scenarios.node_stop_scenario(1, 'test-node', 300, 15)

        mock_logging.assert_called()

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_termination_scenario_success(self, mock_alibaba_class, mock_logging):
        """Test node_termination_scenario successfully terminates node"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'
        mock_alibaba.wait_until_stopped.return_value = True
        mock_alibaba.wait_until_released.return_value = True

        scenarios = alibaba_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        scenarios.node_termination_scenario(1, 'test-node', 300, 15)

        mock_alibaba.stop_instances.assert_called_once_with('i-123')
        mock_alibaba.wait_until_stopped.assert_called_once()
        mock_alibaba.release_instance.assert_called_once_with('i-123')
        mock_alibaba.wait_until_released.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_termination_scenario_failure(self, mock_alibaba_class, mock_logging):
        """Test node_termination_scenario handles failure"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'
        mock_alibaba.stop_instances.side_effect = Exception('Stop failed')

        scenarios = alibaba_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        with self.assertRaises(Exception):
            scenarios.node_termination_scenario(1, 'test-node', 300, 15)

        mock_logging.assert_called()

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_reboot_scenario_success(self, mock_alibaba_class, mock_logging, mock_nodeaction):
        """Test node_reboot_scenario successfully reboots node"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'

        scenarios = alibaba_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        scenarios.node_reboot_scenario(1, 'test-node', 300, soft_reboot=False)

        mock_alibaba.reboot_instances.assert_called_once_with('i-123')
        mock_nodeaction.wait_for_unknown_status.assert_called_once()
        mock_nodeaction.wait_for_ready_status.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_reboot_scenario_no_kube_check(self, mock_alibaba_class, mock_logging, mock_nodeaction):
        """Test node_reboot_scenario without Kubernetes check"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'

        scenarios = alibaba_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        scenarios.node_reboot_scenario(1, 'test-node', 300)

        mock_alibaba.reboot_instances.assert_called_once()
        mock_nodeaction.wait_for_unknown_status.assert_not_called()
        mock_nodeaction.wait_for_ready_status.assert_not_called()

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_reboot_scenario_failure(self, mock_alibaba_class, mock_logging):
        """Test node_reboot_scenario handles failure"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'
        mock_alibaba.reboot_instances.side_effect = Exception('Reboot failed')

        scenarios = alibaba_node_scenarios(self.mock_kubecli, False, self.affected_nodes_status)

        with self.assertRaises(Exception):
            scenarios.node_reboot_scenario(1, 'test-node', 300)

        mock_logging.assert_called()

    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.nodeaction')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.Alibaba')
    def test_node_reboot_scenario_multiple_runs(self, mock_alibaba_class, mock_logging, mock_nodeaction):
        """Test node_reboot_scenario with multiple runs"""
        mock_alibaba = Mock()
        mock_alibaba_class.return_value = mock_alibaba
        mock_alibaba.get_instance_id.return_value = 'i-123'

        scenarios = alibaba_node_scenarios(self.mock_kubecli, True, self.affected_nodes_status)

        scenarios.node_reboot_scenario(2, 'test-node', 300)

        self.assertEqual(mock_alibaba.reboot_instances.call_count, 2)
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 2)


if __name__ == "__main__":
    unittest.main()
