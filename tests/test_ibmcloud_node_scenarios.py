#!/usr/bin/env python3

"""
Test suite for IBM Cloud VPC node scenarios

This test suite covers both the IbmCloud class and ibm_node_scenarios class
using mocks to avoid actual IBM Cloud API calls.

IMPORTANT: These tests use comprehensive mocking and do NOT require any cloud provider
settings or credentials. No environment variables need to be set. All API clients and
external dependencies are mocked.

Test Coverage:
- TestIbmCloud: 30 tests for the IbmCloud VPC API client class
  - Initialization, SSL configuration, instance operations (start/stop/reboot/delete)
  - Status checking, wait operations, error handling
- TestIbmNodeScenarios: 14 tests for node scenario orchestration
  - Node start/stop/reboot/terminate scenarios
  - Exception handling, multiple kill counts

Usage:
    # Run all tests
    python -m unittest tests.test_ibmcloud_node_scenarios -v

    # Run with coverage
    python -m coverage run -a -m unittest tests/test_ibmcloud_node_scenarios.py -v

Assisted By: Claude Code
"""

import unittest
import sys
import json
from unittest.mock import MagicMock, patch, Mock

# Mock paramiko and IBM SDK before importing
sys.modules['paramiko'] = MagicMock()
sys.modules['ibm_vpc'] = MagicMock()
sys.modules['ibm_cloud_sdk_core'] = MagicMock()
sys.modules['ibm_cloud_sdk_core.authenticators'] = MagicMock()

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus
from krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios import (
    IbmCloud,
    ibm_node_scenarios
)


class TestIbmCloud(unittest.TestCase):
    """Test cases for IbmCloud class"""

    def setUp(self):
        """Set up test fixtures"""
        # Set up environment variables
        self.env_patcher = patch.dict('os.environ', {
            'IBMC_APIKEY': 'test-api-key',
            'IBMC_URL': 'https://test.cloud.ibm.com'
        })
        self.env_patcher.start()

        # Mock IBM VPC client
        self.mock_vpc = MagicMock()
        self.vpc_patcher = patch('krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios.VpcV1')
        self.mock_vpc_class = self.vpc_patcher.start()
        self.mock_vpc_class.return_value = self.mock_vpc

        # Mock IAMAuthenticator
        self.auth_patcher = patch('krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios.IAMAuthenticator')
        self.mock_auth = self.auth_patcher.start()

        # Create IbmCloud instance
        self.ibm = IbmCloud()

    def tearDown(self):
        """Clean up after tests"""
        self.env_patcher.stop()
        self.vpc_patcher.stop()
        self.auth_patcher.stop()

    def test_init_success(self):
        """Test IbmCloud class initialization"""
        self.assertIsNotNone(self.ibm.service)
        self.mock_vpc.set_service_url.assert_called_once_with('https://test.cloud.ibm.com')

    def test_init_missing_api_key(self):
        """Test initialization fails when IBMC_APIKEY is missing"""
        with patch.dict('os.environ', {
            'IBMC_URL': 'https://test.cloud.ibm.com'
        }, clear=True):
            with self.assertRaises(Exception) as context:
                IbmCloud()
            self.assertIn("IBMC_APIKEY", str(context.exception))

    def test_init_missing_url(self):
        """Test initialization fails when IBMC_URL is missing"""
        with patch.dict('os.environ', {
            'IBMC_APIKEY': 'test-api-key'
        }, clear=True):
            with self.assertRaises(Exception) as context:
                IbmCloud()
            self.assertIn("IBMC_URL", str(context.exception))

    def test_configure_ssl_verification_disabled(self):
        """Test disabling SSL verification"""
        self.ibm.configure_ssl_verification(True)
        self.mock_vpc.set_disable_ssl_verification.assert_called_with(True)

    def test_configure_ssl_verification_enabled(self):
        """Test enabling SSL verification"""
        self.ibm.configure_ssl_verification(False)
        self.mock_vpc.set_disable_ssl_verification.assert_called_with(False)

    def test_get_instance_id_success(self):
        """Test getting instance ID by node name"""
        mock_list = [
            {'vpc_name': 'test-node-1', 'vpc_id': 'vpc-1'},
            {'vpc_name': 'test-node-2', 'vpc_id': 'vpc-2'}
        ]

        with patch.object(self.ibm, 'list_instances', return_value=mock_list):
            instance_id = self.ibm.get_instance_id('test-node-1')
            self.assertEqual(instance_id, 'vpc-1')

    def test_get_instance_id_not_found(self):
        """Test getting instance ID when node not found"""
        mock_list = [
            {'vpc_name': 'test-node-1', 'vpc_id': 'vpc-1'}
        ]

        with patch.object(self.ibm, 'list_instances', return_value=mock_list):
            with self.assertRaises(SystemExit):
                self.ibm.get_instance_id('non-existent-node')

    def test_delete_instance_success(self):
        """Test deleting instance successfully"""
        self.mock_vpc.delete_instance.return_value = None

        result = self.ibm.delete_instance('vpc-123')

        self.mock_vpc.delete_instance.assert_called_once_with('vpc-123')
        # Method doesn't explicitly return True, so we just verify no exception

    def test_delete_instance_failure(self):
        """Test deleting instance with failure"""
        self.mock_vpc.delete_instance.side_effect = Exception("API Error")

        result = self.ibm.delete_instance('vpc-123')

        self.assertEqual(result, False)

    def test_reboot_instances_success(self):
        """Test rebooting instance successfully"""
        self.mock_vpc.create_instance_action.return_value = None

        result = self.ibm.reboot_instances('vpc-123')

        self.assertTrue(result)
        self.mock_vpc.create_instance_action.assert_called_once_with(
            'vpc-123',
            type='reboot'
        )

    def test_reboot_instances_failure(self):
        """Test rebooting instance with failure"""
        self.mock_vpc.create_instance_action.side_effect = Exception("API Error")

        result = self.ibm.reboot_instances('vpc-123')

        self.assertEqual(result, False)

    def test_stop_instances_success(self):
        """Test stopping instance successfully"""
        self.mock_vpc.create_instance_action.return_value = None

        result = self.ibm.stop_instances('vpc-123')

        self.assertTrue(result)
        self.mock_vpc.create_instance_action.assert_called_once_with(
            'vpc-123',
            type='stop'
        )

    def test_stop_instances_failure(self):
        """Test stopping instance with failure"""
        self.mock_vpc.create_instance_action.side_effect = Exception("API Error")

        result = self.ibm.stop_instances('vpc-123')

        self.assertEqual(result, False)

    def test_start_instances_success(self):
        """Test starting instance successfully"""
        self.mock_vpc.create_instance_action.return_value = None

        result = self.ibm.start_instances('vpc-123')

        self.assertTrue(result)
        self.mock_vpc.create_instance_action.assert_called_once_with(
            'vpc-123',
            type='start'
        )

    def test_start_instances_failure(self):
        """Test starting instance with failure"""
        self.mock_vpc.create_instance_action.side_effect = Exception("API Error")

        result = self.ibm.start_instances('vpc-123')

        self.assertEqual(result, False)

    def test_list_instances_success(self):
        """Test listing instances successfully"""
        mock_result = Mock()
        mock_result.get_result.return_value = {
            'instances': [
                {'name': 'node-1', 'id': 'vpc-1'},
                {'name': 'node-2', 'id': 'vpc-2'}
            ],
            'total_count': 2,
            'limit': 50
        }
        self.mock_vpc.list_instances.return_value = mock_result

        instances = self.ibm.list_instances()

        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[0]['vpc_name'], 'node-1')
        self.assertEqual(instances[1]['vpc_name'], 'node-2')

    def test_list_instances_with_pagination(self):
        """Test listing instances with pagination"""
        # First call returns limit reached
        mock_result_1 = Mock()
        mock_result_1.get_result.return_value = {
            'instances': [
                {'name': 'node-1', 'id': 'vpc-1'}
            ],
            'total_count': 1,
            'limit': 1
        }

        # Second call returns remaining
        mock_result_2 = Mock()
        mock_vpc_2 = type('obj', (object,), {'name': 'node-2', 'id': 'vpc-2'})
        mock_result_2.get_result.return_value = {
            'instances': [mock_vpc_2],
            'total_count': 1,
            'limit': 50
        }

        self.mock_vpc.list_instances.side_effect = [mock_result_1, mock_result_2]

        instances = self.ibm.list_instances()

        self.assertEqual(len(instances), 2)
        self.assertEqual(self.mock_vpc.list_instances.call_count, 2)

    def test_list_instances_failure(self):
        """Test listing instances with failure"""
        self.mock_vpc.list_instances.side_effect = Exception("API Error")

        with self.assertRaises(SystemExit):
            self.ibm.list_instances()

    def test_find_id_in_list(self):
        """Test finding ID in VPC list"""
        vpc_list = [
            {'vpc_name': 'vpc-1', 'vpc_id': 'id-1'},
            {'vpc_name': 'vpc-2', 'vpc_id': 'id-2'}
        ]

        vpc_id = self.ibm.find_id_in_list('vpc-2', vpc_list)

        self.assertEqual(vpc_id, 'id-2')

    def test_find_id_in_list_not_found(self):
        """Test finding ID in VPC list when not found"""
        vpc_list = [
            {'vpc_name': 'vpc-1', 'vpc_id': 'id-1'}
        ]

        vpc_id = self.ibm.find_id_in_list('vpc-3', vpc_list)

        self.assertIsNone(vpc_id)

    def test_get_instance_status_success(self):
        """Test getting instance status successfully"""
        mock_result = Mock()
        mock_result.get_result.return_value = {'status': 'running'}
        self.mock_vpc.get_instance.return_value = mock_result

        status = self.ibm.get_instance_status('vpc-123')

        self.assertEqual(status, 'running')

    def test_get_instance_status_failure(self):
        """Test getting instance status with failure"""
        self.mock_vpc.get_instance.side_effect = Exception("API Error")

        status = self.ibm.get_instance_status('vpc-123')

        self.assertIsNone(status)

    def test_wait_until_deleted_success(self):
        """Test waiting until instance is deleted"""
        # First call returns status, second returns None (deleted)
        with patch.object(self.ibm, 'get_instance_status', side_effect=['deleting', None]):
            affected_node = MagicMock(spec=AffectedNode)

            with patch('time.time', side_effect=[100, 105]), \
                 patch('time.sleep'):
                result = self.ibm.wait_until_deleted('vpc-123', timeout=60, affected_node=affected_node)

            self.assertTrue(result)
            affected_node.set_affected_node_status.assert_called_once_with("terminated", 5)

    def test_wait_until_deleted_timeout(self):
        """Test waiting until deleted with timeout"""
        with patch.object(self.ibm, 'get_instance_status', return_value='deleting'):
            with patch('time.sleep'):
                result = self.ibm.wait_until_deleted('vpc-123', timeout=5)

            self.assertFalse(result)

    def test_wait_until_running_success(self):
        """Test waiting until instance is running"""
        with patch.object(self.ibm, 'get_instance_status', side_effect=['starting', 'running']):
            affected_node = MagicMock(spec=AffectedNode)

            with patch('time.time', side_effect=[100, 105]), \
                 patch('time.sleep'):
                result = self.ibm.wait_until_running('vpc-123', timeout=60, affected_node=affected_node)

            self.assertTrue(result)
            affected_node.set_affected_node_status.assert_called_once_with("running", 5)

    def test_wait_until_running_timeout(self):
        """Test waiting until running with timeout"""
        with patch.object(self.ibm, 'get_instance_status', return_value='starting'):
            with patch('time.sleep'):
                result = self.ibm.wait_until_running('vpc-123', timeout=5)

            self.assertFalse(result)

    def test_wait_until_stopped_success(self):
        """Test waiting until instance is stopped"""
        with patch.object(self.ibm, 'get_instance_status', side_effect=['stopping', 'stopped']):
            affected_node = MagicMock(spec=AffectedNode)

            with patch('time.time', side_effect=[100, 105]), \
                 patch('time.sleep'):
                result = self.ibm.wait_until_stopped('vpc-123', timeout=60, affected_node=affected_node)

            self.assertTrue(result)
            affected_node.set_affected_node_status.assert_called_once_with("stopped", 5)

    def test_wait_until_stopped_timeout(self):
        """Test waiting until stopped with timeout"""
        with patch.object(self.ibm, 'get_instance_status', return_value='stopping'):
            with patch('time.sleep'):
                result = self.ibm.wait_until_stopped('vpc-123', timeout=5, affected_node=None)

            self.assertFalse(result)

    def test_wait_until_rebooted_success(self):
        """Test waiting until instance is rebooted"""
        # First call checks reboot status (not 'starting'), second call in wait_until_running checks status
        with patch.object(self.ibm, 'get_instance_status', side_effect=['running', 'running']):
            affected_node = MagicMock(spec=AffectedNode)

            time_values = [100, 105, 110]
            with patch('time.time', side_effect=time_values), \
                 patch('time.sleep'):
                result = self.ibm.wait_until_rebooted('vpc-123', timeout=60, affected_node=affected_node)

            self.assertTrue(result)

    def test_wait_until_rebooted_timeout(self):
        """Test waiting until rebooted with timeout"""
        with patch.object(self.ibm, 'get_instance_status', return_value='starting'):
            with patch('time.sleep'):
                result = self.ibm.wait_until_rebooted('vpc-123', timeout=5, affected_node=None)

            self.assertFalse(result)


class TestIbmNodeScenarios(unittest.TestCase):
    """Test cases for ibm_node_scenarios class"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock KrknKubernetes
        self.mock_kubecli = MagicMock(spec=KrknKubernetes)
        self.affected_nodes_status = AffectedNodeStatus()

        # Mock the IbmCloud class entirely to avoid any real API calls
        self.ibm_cloud_patcher = patch('krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios.IbmCloud')
        self.mock_ibm_cloud_class = self.ibm_cloud_patcher.start()

        # Create a mock instance that will be returned when IbmCloud() is called
        self.mock_ibm_cloud_instance = MagicMock()
        self.mock_ibm_cloud_class.return_value = self.mock_ibm_cloud_instance

        # Create ibm_node_scenarios instance
        self.scenario = ibm_node_scenarios(
            kubecli=self.mock_kubecli,
            node_action_kube_check=True,
            affected_nodes_status=self.affected_nodes_status,
            disable_ssl_verification=False
        )

    def tearDown(self):
        """Clean up after tests"""
        self.ibm_cloud_patcher.stop()

    def test_init(self):
        """Test ibm_node_scenarios initialization"""
        self.assertIsNotNone(self.scenario.ibmcloud)
        self.assertTrue(self.scenario.node_action_kube_check)
        self.assertEqual(self.scenario.kubecli, self.mock_kubecli)

    def test_init_with_ssl_disabled(self):
        """Test initialization with SSL verification disabled"""
        scenario = ibm_node_scenarios(
            kubecli=self.mock_kubecli,
            node_action_kube_check=True,
            affected_nodes_status=self.affected_nodes_status,
            disable_ssl_verification=True
        )

        # Verify configure_ssl_verification was called
        self.mock_ibm_cloud_instance.configure_ssl_verification.assert_called_with(True)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_start_scenario_success(self, mock_wait_ready):
        """Test node start scenario successfully"""
        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.start_instances.return_value = True
        self.mock_ibm_cloud_instance.wait_until_running.return_value = True

        self.scenario.node_start_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            poll_interval=5
        )

        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)
        self.assertEqual(self.affected_nodes_status.affected_nodes[0].node_name, 'test-node')
        mock_wait_ready.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_start_scenario_no_kube_check(self, mock_wait_ready):
        """Test node start scenario without Kubernetes check"""
        self.scenario.node_action_kube_check = False

        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.start_instances.return_value = True
        self.mock_ibm_cloud_instance.wait_until_running.return_value = True

        self.scenario.node_start_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            poll_interval=5
        )

        mock_wait_ready.assert_not_called()

    def test_node_stop_scenario_success(self):
        """Test node stop scenario successfully"""
        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.stop_instances.return_value = True
        self.mock_ibm_cloud_instance.wait_until_stopped.return_value = True

        self.scenario.node_stop_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            poll_interval=5
        )

        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    def test_node_stop_scenario_failure(self):
        """Test node stop scenario with stop command failure"""
        # Configure mock - get_instance_id succeeds but stop_instances fails
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.stop_instances.return_value = False

        # Code raises exception inside try/except, so it should be caught and logged
        self.scenario.node_stop_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            poll_interval=5
        )

        # Verify that affected nodes were not appended since exception was caught
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 0)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_reboot_scenario_success(self, mock_wait_ready, mock_wait_unknown):
        """Test node reboot scenario successfully"""
        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.reboot_instances.return_value = True
        self.mock_ibm_cloud_instance.wait_until_rebooted.return_value = True

        self.scenario.node_reboot_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            soft_reboot=False
        )

        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)
        mock_wait_unknown.assert_called_once()
        mock_wait_ready.assert_called_once()

    def test_node_reboot_scenario_failure(self):
        """Test node reboot scenario with reboot command failure"""
        # Configure mock - get_instance_id succeeds but reboot_instances fails
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.reboot_instances.return_value = False

        # Code raises exception inside try/except, so it should be caught and logged
        self.scenario.node_reboot_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            soft_reboot=False
        )

        # Verify that affected nodes were not appended since exception was caught
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 0)

    def test_node_terminate_scenario_success(self):
        """Test node terminate scenario successfully"""
        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.delete_instance.return_value = None
        self.mock_ibm_cloud_instance.wait_until_deleted.return_value = True

        self.scenario.node_terminate_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            poll_interval=5
        )

        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    def test_node_scenario_multiple_kill_count(self):
        """Test node scenario with multiple kill count"""
        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.stop_instances.return_value = True
        self.mock_ibm_cloud_instance.wait_until_stopped.return_value = True

        self.scenario.node_stop_scenario(
            instance_kill_count=2,
            node='test-node',
            timeout=60,
            poll_interval=5
        )

        # Should have 2 affected nodes for 2 iterations
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 2)

    def test_node_start_scenario_exception(self):
        """Test node start scenario with exception during operation"""
        # Configure mock - get_instance_id succeeds but start_instances fails
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.start_instances.side_effect = Exception("API Error")

        # Should handle exception gracefully
        self.scenario.node_start_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            poll_interval=5
        )

        # Verify affected node still added even on failure
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    def test_node_stop_scenario_exception(self):
        """Test node stop scenario with exception"""
        # Configure mock to raise SystemExit
        self.mock_ibm_cloud_instance.get_instance_id.side_effect = SystemExit(1)

        # Should handle system exit gracefully
        with self.assertRaises(SystemExit):
            self.scenario.node_stop_scenario(
                instance_kill_count=1,
                node='test-node',
                timeout=60,
                poll_interval=5
            )

    def test_node_reboot_scenario_exception(self):
        """Test node reboot scenario with exception during operation"""
        # Configure mock - get_instance_id succeeds but reboot_instances fails
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.reboot_instances.side_effect = Exception("API Error")

        # Should handle exception gracefully
        self.scenario.node_reboot_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            soft_reboot=False
        )

    def test_node_terminate_scenario_exception(self):
        """Test node terminate scenario with exception"""
        # Configure mock - get_instance_id succeeds but delete_instance fails
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'vpc-123'
        self.mock_ibm_cloud_instance.delete_instance.side_effect = Exception("API Error")

        # Should handle exception gracefully
        self.scenario.node_terminate_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            poll_interval=5
        )


if __name__ == '__main__':
    unittest.main()
