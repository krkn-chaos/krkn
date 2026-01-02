#!/usr/bin/env python3

"""
Test suite for IBM Cloud Power node scenarios

This test suite covers both the IbmCloudPower class and ibmcloud_power_node_scenarios class
using mocks to avoid actual IBM Cloud API calls.

IMPORTANT: These tests use comprehensive mocking and do NOT require any cloud provider
settings or credentials. No environment variables need to be set. All API clients and
external dependencies are mocked.

Test Coverage:
- TestIbmCloudPower: 31 tests for the IbmCloudPower API client class
  - Authentication, instance operations (start/stop/reboot/delete)
  - Status checking, wait operations, error handling
- TestIbmCloudPowerNodeScenarios: 10 tests for node scenario orchestration
  - Node start/stop/reboot/terminate scenarios
  - Exception handling, multiple kill counts

Usage:
    # Run all tests
    python -m unittest tests.test_ibmcloud_power_node_scenarios -v

    # Run with coverage
    python -m coverage run -a -m unittest tests/test_ibmcloud_power_node_scenarios.py -v

Assisted By: Claude Code
"""

import unittest
import sys
import json
from unittest.mock import MagicMock, patch, Mock

# Mock paramiko before importing
sys.modules['paramiko'] = MagicMock()

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus
from krkn.scenario_plugins.node_actions.ibmcloud_power_node_scenarios import (
    IbmCloudPower,
    ibmcloud_power_node_scenarios
)


class TestIbmCloudPower(unittest.TestCase):
    """Test cases for IbmCloudPower class"""

    def setUp(self):
        """Set up test fixtures"""
        # Set up environment variables
        self.env_patcher = patch.dict('os.environ', {
            'IBMC_APIKEY': 'test-api-key',
            'IBMC_POWER_URL': 'https://test.cloud.ibm.com',
            'IBMC_POWER_CRN': 'crn:v1:bluemix:public:power-iaas:us-south:a/abc123:instance-id::'
        })
        self.env_patcher.start()

        # Mock requests
        self.requests_patcher = patch('krkn.scenario_plugins.node_actions.ibmcloud_power_node_scenarios.requests')
        self.mock_requests = self.requests_patcher.start()

        # Mock authentication response
        mock_auth_response = Mock()
        mock_auth_response.status_code = 200
        mock_auth_response.json.return_value = {
            'access_token': 'test-token',
            'token_type': 'Bearer',
            'expires_in': 3600
        }

        self.mock_requests.request.return_value = mock_auth_response

        # Create IbmCloudPower instance
        self.ibm = IbmCloudPower()

    def tearDown(self):
        """Clean up after tests"""
        self.env_patcher.stop()
        self.requests_patcher.stop()

    def test_init_success(self):
        """Test IbmCloudPower class initialization"""
        self.assertIsNotNone(self.ibm.api_key)
        self.assertEqual(self.ibm.api_key, 'test-api-key')
        self.assertIsNotNone(self.ibm.service_url)
        self.assertEqual(self.ibm.service_url, 'https://test.cloud.ibm.com')
        self.assertIsNotNone(self.ibm.CRN)
        self.assertEqual(self.ibm.cloud_instance_id, 'instance-id')
        self.assertIsNotNone(self.ibm.token)
        self.assertIsNotNone(self.ibm.headers)

    def test_init_missing_api_key(self):
        """Test initialization fails when IBMC_APIKEY is missing"""
        with patch.dict('os.environ', {
            'IBMC_POWER_URL': 'https://test.cloud.ibm.com',
            'IBMC_POWER_CRN': 'crn:v1:bluemix:public:power-iaas:us-south:a/abc123:instance-id::'
        }, clear=True):
            with self.assertRaises(Exception) as context:
                IbmCloudPower()
            self.assertIn("IBMC_APIKEY", str(context.exception))

    def test_init_missing_power_url(self):
        """Test initialization fails when IBMC_POWER_URL is missing"""
        with patch.dict('os.environ', {
            'IBMC_APIKEY': 'test-api-key',
            'IBMC_POWER_CRN': 'crn:v1:bluemix:public:power-iaas:us-south:a/abc123:instance-id::'
        }, clear=True):
            with self.assertRaises(Exception) as context:
                IbmCloudPower()
            self.assertIn("IBMC_POWER_URL", str(context.exception))

    def test_init_missing_crn(self):
        """Test initialization fails when IBMC_POWER_CRN is missing"""
        with patch.dict('os.environ', {
            'IBMC_APIKEY': 'test-api-key',
            'IBMC_POWER_URL': 'https://test.cloud.ibm.com'
        }, clear=True):
            # The code will fail on split() before the IBMC_POWER_CRN check
            # so we check for either AttributeError or the exception message
            with self.assertRaises((Exception, AttributeError)):
                IbmCloudPower()

    def test_authenticate_success(self):
        """Test successful authentication"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'new-test-token',
            'token_type': 'Bearer',
            'expires_in': 3600
        }
        self.mock_requests.request.return_value = mock_response

        self.ibm.authenticate()

        self.assertEqual(self.ibm.token['access_token'], 'new-test-token')
        self.assertIn('Authorization', self.ibm.headers)
        self.assertEqual(self.ibm.headers['Authorization'], 'Bearer new-test-token')

    def test_authenticate_failure(self):
        """Test authentication failure"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("Unauthorized")
        self.mock_requests.request.return_value = mock_response

        with self.assertRaises(Exception):
            self.ibm.authenticate()

    def test_get_instance_id_success(self):
        """Test getting instance ID by node name"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'pvmInstances': [
                {'serverName': 'test-node-1', 'pvmInstanceID': 'pvm-1'},
                {'serverName': 'test-node-2', 'pvmInstanceID': 'pvm-2'}
            ]
        }
        self.mock_requests.request.return_value = mock_response

        instance_id = self.ibm.get_instance_id('test-node-1')

        self.assertEqual(instance_id, 'pvm-1')

    def test_get_instance_id_not_found(self):
        """Test getting instance ID when node not found"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'pvmInstances': [
                {'serverName': 'test-node-1', 'pvmInstanceID': 'pvm-1'}
            ]
        }
        self.mock_requests.request.return_value = mock_response

        with self.assertRaises(SystemExit):
            self.ibm.get_instance_id('non-existent-node')

    def test_delete_instance_success(self):
        """Test deleting instance successfully"""
        mock_response = Mock()
        mock_response.status_code = 200
        self.mock_requests.request.return_value = mock_response

        result = self.ibm.delete_instance('pvm-123')

        self.mock_requests.request.assert_called()
        call_args = self.mock_requests.request.call_args
        self.assertIn('immediate-shutdown', call_args[1]['data'])

    def test_delete_instance_failure(self):
        """Test deleting instance with failure"""
        self.mock_requests.request.side_effect = Exception("API Error")

        result = self.ibm.delete_instance('pvm-123')

        self.assertEqual(result, False)

    def test_reboot_instances_hard_reboot(self):
        """Test hard reboot of instance"""
        mock_response = Mock()
        mock_response.status_code = 200
        self.mock_requests.request.return_value = mock_response

        result = self.ibm.reboot_instances('pvm-123', soft=False)

        self.assertTrue(result)
        call_args = self.mock_requests.request.call_args
        self.assertIn('hard-reboot', call_args[1]['data'])

    def test_reboot_instances_soft_reboot(self):
        """Test soft reboot of instance"""
        mock_response = Mock()
        mock_response.status_code = 200
        self.mock_requests.request.return_value = mock_response

        result = self.ibm.reboot_instances('pvm-123', soft=True)

        self.assertTrue(result)
        call_args = self.mock_requests.request.call_args
        self.assertIn('soft-reboot', call_args[1]['data'])

    def test_reboot_instances_failure(self):
        """Test reboot instance with failure"""
        self.mock_requests.request.side_effect = Exception("API Error")

        result = self.ibm.reboot_instances('pvm-123')

        self.assertEqual(result, False)

    def test_stop_instances_success(self):
        """Test stopping instance successfully"""
        mock_response = Mock()
        mock_response.status_code = 200
        self.mock_requests.request.return_value = mock_response

        result = self.ibm.stop_instances('pvm-123')

        self.assertTrue(result)
        call_args = self.mock_requests.request.call_args
        self.assertIn('stop', call_args[1]['data'])

    def test_stop_instances_failure(self):
        """Test stopping instance with failure"""
        self.mock_requests.request.side_effect = Exception("API Error")

        result = self.ibm.stop_instances('pvm-123')

        self.assertEqual(result, False)

    def test_start_instances_success(self):
        """Test starting instance successfully"""
        mock_response = Mock()
        mock_response.status_code = 200
        self.mock_requests.request.return_value = mock_response

        result = self.ibm.start_instances('pvm-123')

        self.assertTrue(result)
        call_args = self.mock_requests.request.call_args
        self.assertIn('start', call_args[1]['data'])

    def test_start_instances_failure(self):
        """Test starting instance with failure"""
        self.mock_requests.request.side_effect = Exception("API Error")

        result = self.ibm.start_instances('pvm-123')

        self.assertEqual(result, False)

    def test_list_instances_success(self):
        """Test listing instances successfully"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'pvmInstances': [
                type('obj', (object,), {'serverName': 'node-1', 'pvmInstanceID': 'pvm-1'}),
                type('obj', (object,), {'serverName': 'node-2', 'pvmInstanceID': 'pvm-2'})
            ]
        }
        self.mock_requests.request.return_value = mock_response

        instances = self.ibm.list_instances()

        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[0]['serverName'], 'node-1')
        self.assertEqual(instances[1]['serverName'], 'node-2')

    def test_list_instances_failure(self):
        """Test listing instances with failure"""
        self.mock_requests.request.side_effect = Exception("API Error")

        with self.assertRaises(SystemExit):
            self.ibm.list_instances()

    def test_get_instance_status_success(self):
        """Test getting instance status successfully"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'ACTIVE'}
        self.mock_requests.request.return_value = mock_response

        status = self.ibm.get_instance_status('pvm-123')

        self.assertEqual(status, 'ACTIVE')

    def test_get_instance_status_failure(self):
        """Test getting instance status with failure"""
        self.mock_requests.request.side_effect = Exception("API Error")

        status = self.ibm.get_instance_status('pvm-123')

        self.assertIsNone(status)

    def test_wait_until_deleted_success(self):
        """Test waiting until instance is deleted"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': None}
        self.mock_requests.request.side_effect = [
            mock_response,
            Exception("Not found")
        ]

        affected_node = MagicMock(spec=AffectedNode)

        with patch('time.time', side_effect=[100, 105]), \
             patch('time.sleep'):
            result = self.ibm.wait_until_deleted('pvm-123', timeout=60, affected_node=affected_node)

        self.assertTrue(result)
        affected_node.set_affected_node_status.assert_called_once()

    def test_wait_until_deleted_timeout(self):
        """Test waiting until deleted with timeout"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'DELETING'}
        self.mock_requests.request.return_value = mock_response

        with patch('time.sleep'):
            result = self.ibm.wait_until_deleted('pvm-123', timeout=5)

        self.assertFalse(result)

    def test_wait_until_running_success(self):
        """Test waiting until instance is running"""
        mock_responses = [
            Mock(status_code=200, json=lambda: {'status': 'BUILD'}),
            Mock(status_code=200, json=lambda: {'status': 'ACTIVE'})
        ]
        self.mock_requests.request.side_effect = mock_responses

        affected_node = MagicMock(spec=AffectedNode)

        with patch('time.time', side_effect=[100, 105]), \
             patch('time.sleep'):
            result = self.ibm.wait_until_running('pvm-123', timeout=60, affected_node=affected_node)

        self.assertTrue(result)
        affected_node.set_affected_node_status.assert_called_once_with("running", 5)

    def test_wait_until_running_timeout(self):
        """Test waiting until running with timeout"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'BUILD'}
        self.mock_requests.request.return_value = mock_response

        with patch('time.sleep'):
            result = self.ibm.wait_until_running('pvm-123', timeout=5)

        self.assertFalse(result)

    def test_wait_until_stopped_success(self):
        """Test waiting until instance is stopped"""
        mock_responses = [
            Mock(status_code=200, json=lambda: {'status': 'STOPPING'}),
            Mock(status_code=200, json=lambda: {'status': 'STOPPED'})
        ]
        self.mock_requests.request.side_effect = mock_responses

        affected_node = MagicMock(spec=AffectedNode)

        with patch('time.time', side_effect=[100, 105]), \
             patch('time.sleep'):
            result = self.ibm.wait_until_stopped('pvm-123', timeout=60, affected_node=affected_node)

        self.assertTrue(result)
        affected_node.set_affected_node_status.assert_called_once_with("stopped", 5)

    def test_wait_until_stopped_timeout(self):
        """Test waiting until stopped with timeout"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'STOPPING'}
        self.mock_requests.request.return_value = mock_response

        with patch('time.sleep'):
            result = self.ibm.wait_until_stopped('pvm-123', timeout=5, affected_node=None)

        self.assertFalse(result)

    def test_wait_until_rebooted_success(self):
        """Test waiting until instance is rebooted"""
        # wait_until_rebooted calls get_instance_status until NOT in reboot state,
        # then calls wait_until_running which also calls get_instance_status
        mock_responses = [
            Mock(status_code=200, json=lambda: {'status': 'HARD_REBOOT'}),  # First check - still rebooting
            Mock(status_code=200, json=lambda: {'status': 'ACTIVE'}),       # Second check - done rebooting
            Mock(status_code=200, json=lambda: {'status': 'ACTIVE'})        # wait_until_running check
        ]
        self.mock_requests.request.side_effect = mock_responses

        affected_node = MagicMock(spec=AffectedNode)

        # Mock all time() calls - need many values because logging uses time.time() extensively
        time_values = [100] * 20  # Just provide enough time values
        with patch('time.time', side_effect=time_values), \
             patch('time.sleep'):
            result = self.ibm.wait_until_rebooted('pvm-123', timeout=60, affected_node=affected_node)

        self.assertTrue(result)

    def test_wait_until_rebooted_timeout(self):
        """Test waiting until rebooted with timeout"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'HARD_REBOOT'}
        self.mock_requests.request.return_value = mock_response

        with patch('time.sleep'):
            result = self.ibm.wait_until_rebooted('pvm-123', timeout=5, affected_node=None)

        self.assertFalse(result)

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


class TestIbmCloudPowerNodeScenarios(unittest.TestCase):
    """Test cases for ibmcloud_power_node_scenarios class"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock KrknKubernetes
        self.mock_kubecli = MagicMock(spec=KrknKubernetes)
        self.affected_nodes_status = AffectedNodeStatus()

        # Mock the IbmCloudPower class entirely to avoid any real API calls
        self.ibm_cloud_patcher = patch('krkn.scenario_plugins.node_actions.ibmcloud_power_node_scenarios.IbmCloudPower')
        self.mock_ibm_cloud_class = self.ibm_cloud_patcher.start()

        # Create a mock instance that will be returned when IbmCloudPower() is called
        self.mock_ibm_cloud_instance = MagicMock()
        self.mock_ibm_cloud_class.return_value = self.mock_ibm_cloud_instance

        # Create ibmcloud_power_node_scenarios instance
        self.scenario = ibmcloud_power_node_scenarios(
            kubecli=self.mock_kubecli,
            node_action_kube_check=True,
            affected_nodes_status=self.affected_nodes_status,
            disable_ssl_verification=False
        )

    def tearDown(self):
        """Clean up after tests"""
        self.ibm_cloud_patcher.stop()

    def test_init(self):
        """Test ibmcloud_power_node_scenarios initialization"""
        self.assertIsNotNone(self.scenario.ibmcloud_power)
        self.assertTrue(self.scenario.node_action_kube_check)
        self.assertEqual(self.scenario.kubecli, self.mock_kubecli)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_start_scenario_success(self, mock_wait_ready):
        """Test node start scenario successfully"""
        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'pvm-123'
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
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'pvm-123'
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
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'pvm-123'
        self.mock_ibm_cloud_instance.stop_instances.return_value = True
        self.mock_ibm_cloud_instance.wait_until_stopped.return_value = True

        self.scenario.node_stop_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            poll_interval=5
        )

        # Verify methods were called
        self.mock_ibm_cloud_instance.get_instance_id.assert_called_once_with('test-node')
        self.mock_ibm_cloud_instance.stop_instances.assert_called_once_with('pvm-123')

        # Note: affected_nodes are not appended in stop scenario based on the code

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_reboot_scenario_hard_reboot(self, mock_wait_ready, mock_wait_unknown):
        """Test node hard reboot scenario"""
        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'pvm-123'
        self.mock_ibm_cloud_instance.reboot_instances.return_value = True
        self.mock_ibm_cloud_instance.wait_until_rebooted.return_value = True

        self.scenario.node_reboot_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            soft_reboot=False
        )

        # Verify methods were called
        self.mock_ibm_cloud_instance.reboot_instances.assert_called_once_with('pvm-123', False)
        mock_wait_unknown.assert_called_once()
        mock_wait_ready.assert_called_once()

        # Note: affected_nodes are not appended in reboot scenario based on the code

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_reboot_scenario_soft_reboot(self, mock_wait_ready, mock_wait_unknown):
        """Test node soft reboot scenario"""
        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'pvm-123'
        self.mock_ibm_cloud_instance.reboot_instances.return_value = True
        self.mock_ibm_cloud_instance.wait_until_rebooted.return_value = True

        self.scenario.node_reboot_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            soft_reboot=True
        )

        # Verify methods were called
        self.mock_ibm_cloud_instance.reboot_instances.assert_called_once_with('pvm-123', True)
        mock_wait_unknown.assert_called_once()
        mock_wait_ready.assert_called_once()

        # Note: affected_nodes are not appended in reboot scenario based on the code

    def test_node_terminate_scenario_success(self):
        """Test node terminate scenario successfully"""
        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'pvm-123'
        self.mock_ibm_cloud_instance.delete_instance.return_value = None
        self.mock_ibm_cloud_instance.wait_until_deleted.return_value = True

        self.scenario.node_terminate_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            poll_interval=5
        )

        # Verify methods were called
        self.mock_ibm_cloud_instance.delete_instance.assert_called_once_with('pvm-123')
        self.mock_ibm_cloud_instance.wait_until_deleted.assert_called_once()

        # Note: affected_nodes are not appended in terminate scenario based on the code

    def test_node_scenario_multiple_kill_count(self):
        """Test node scenario with multiple kill count"""
        # Configure mock methods
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'pvm-123'
        self.mock_ibm_cloud_instance.stop_instances.return_value = True
        self.mock_ibm_cloud_instance.wait_until_stopped.return_value = True

        self.scenario.node_stop_scenario(
            instance_kill_count=2,
            node='test-node',
            timeout=60,
            poll_interval=5
        )

        # Verify stop was called twice (kill_count=2)
        self.assertEqual(self.mock_ibm_cloud_instance.stop_instances.call_count, 2)

        # Note: affected_nodes are not appended in stop scenario based on the code

    def test_node_start_scenario_exception(self):
        """Test node start scenario with exception during operation"""
        # Configure mock - get_instance_id succeeds but start_instances fails
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'pvm-123'
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

    def test_node_reboot_scenario_exception(self):
        """Test node reboot scenario with exception during operation"""
        # Configure mock - get_instance_id succeeds but reboot_instances fails
        self.mock_ibm_cloud_instance.get_instance_id.return_value = 'pvm-123'
        self.mock_ibm_cloud_instance.reboot_instances.side_effect = Exception("API Error")

        # Should handle exception gracefully
        self.scenario.node_reboot_scenario(
            instance_kill_count=1,
            node='test-node',
            timeout=60,
            soft_reboot=False
        )


if __name__ == '__main__':
    unittest.main()
