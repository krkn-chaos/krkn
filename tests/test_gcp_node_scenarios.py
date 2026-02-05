#!/usr/bin/env python3

"""
Test suite for GCP node scenarios

This test suite covers both the GCP class and gcp_node_scenarios class
using mocks to avoid actual GCP API calls.

Usage:
    python -m coverage run -a -m unittest tests/test_gcp_node_scenarios.py -v

Assisted By: Claude Code
"""

import unittest
import sys
from unittest.mock import MagicMock, patch

# Mock external dependencies before any imports that use them
# Create proper nested mock structure for google modules
mock_google = MagicMock()
mock_google_auth = MagicMock()
mock_google_auth_transport = MagicMock()
mock_google_cloud = MagicMock()
mock_google_cloud_compute = MagicMock()

sys.modules['google'] = mock_google
sys.modules['google.auth'] = mock_google_auth
sys.modules['google.auth.transport'] = mock_google_auth_transport
sys.modules['google.auth.transport.requests'] = MagicMock()
sys.modules['google.cloud'] = mock_google_cloud
sys.modules['google.cloud.compute_v1'] = mock_google_cloud_compute
sys.modules['paramiko'] = MagicMock()

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus
from krkn.scenario_plugins.node_actions.gcp_node_scenarios import GCP, gcp_node_scenarios


class TestGCP(unittest.TestCase):
    """Test cases for GCP class"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock google.auth before creating GCP instance
        self.auth_patcher = patch('krkn.scenario_plugins.node_actions.gcp_node_scenarios.google.auth.default')
        self.compute_patcher = patch('krkn.scenario_plugins.node_actions.gcp_node_scenarios.compute_v1.InstancesClient')

        self.mock_auth = self.auth_patcher.start()
        self.mock_compute_client = self.compute_patcher.start()

        # Configure auth mock to return credentials and project_id
        mock_credentials = MagicMock()
        self.mock_auth.return_value = (mock_credentials, 'test-project-123')

        # Create GCP instance with mocked dependencies
        self.gcp = GCP()

    def tearDown(self):
        """Clean up after tests"""
        self.auth_patcher.stop()
        self.compute_patcher.stop()

    def test_gcp_init_success(self):
        """Test GCP class initialization success"""
        self.assertEqual(self.gcp.project_id, 'test-project-123')
        self.assertIsNotNone(self.gcp.instance_client)

    def test_gcp_init_failure(self):
        """Test GCP class initialization failure"""
        with patch('krkn.scenario_plugins.node_actions.gcp_node_scenarios.google.auth.default', side_effect=Exception("Auth error")):
            with self.assertRaises(Exception):
                GCP()

    def test_get_node_instance_success(self):
        """Test getting node instance successfully"""
        # Create mock instance
        mock_instance = MagicMock()
        mock_instance.name = 'gke-cluster-node-1'

        # Create mock response
        mock_response = MagicMock()
        mock_response.instances = [mock_instance]

        # Mock aggregated_list to return our mock data
        self.gcp.instance_client.aggregated_list = MagicMock(
            return_value=[('zones/us-central1-a', mock_response)]
        )

        result = self.gcp.get_node_instance('gke-cluster-node-1')

        self.assertEqual(result, mock_instance)
        self.assertEqual(result.name, 'gke-cluster-node-1')

    def test_get_node_instance_partial_match(self):
        """Test getting node instance with partial name match"""
        mock_instance = MagicMock()
        mock_instance.name = 'node-1'

        mock_response = MagicMock()
        mock_response.instances = [mock_instance]

        self.gcp.instance_client.aggregated_list = MagicMock(
            return_value=[('zones/us-central1-a', mock_response)]
        )

        # instance.name ('node-1') in node ('gke-cluster-node-1-abc') == True
        result = self.gcp.get_node_instance('gke-cluster-node-1-abc')

        self.assertIsNotNone(result)
        self.assertEqual(result.name, 'node-1')

    def test_get_node_instance_not_found(self):
        """Test getting node instance when not found"""
        mock_response = MagicMock()
        mock_response.instances = None

        self.gcp.instance_client.aggregated_list = MagicMock(
            return_value=[('zones/us-central1-a', mock_response)]
        )

        result = self.gcp.get_node_instance('non-existent-node')

        self.assertIsNone(result)

    def test_get_node_instance_failure(self):
        """Test getting node instance with failure"""
        self.gcp.instance_client.aggregated_list = MagicMock(
            side_effect=Exception("GCP error")
        )

        with self.assertRaises(Exception):
            self.gcp.get_node_instance('node-1')

    def test_get_instance_name(self):
        """Test getting instance name"""
        mock_instance = MagicMock()
        mock_instance.name = 'gke-cluster-node-1'

        result = self.gcp.get_instance_name(mock_instance)

        self.assertEqual(result, 'gke-cluster-node-1')

    def test_get_instance_name_none(self):
        """Test getting instance name when name is None"""
        mock_instance = MagicMock()
        mock_instance.name = None

        result = self.gcp.get_instance_name(mock_instance)

        self.assertIsNone(result)

    def test_get_instance_zone(self):
        """Test getting instance zone"""
        mock_instance = MagicMock()
        mock_instance.zone = 'https://www.googleapis.com/compute/v1/projects/test-project/zones/us-central1-a'

        result = self.gcp.get_instance_zone(mock_instance)

        self.assertEqual(result, 'us-central1-a')

    def test_get_instance_zone_none(self):
        """Test getting instance zone when zone is None"""
        mock_instance = MagicMock()
        mock_instance.zone = None

        result = self.gcp.get_instance_zone(mock_instance)

        self.assertIsNone(result)

    def test_get_node_instance_zone(self):
        """Test getting node instance zone"""
        mock_instance = MagicMock()
        mock_instance.name = 'gke-cluster-node-1'
        mock_instance.zone = 'https://www.googleapis.com/compute/v1/projects/test-project/zones/us-west1-b'

        # Patch get_node_instance to return our mock directly
        with patch.object(self.gcp, 'get_node_instance', return_value=mock_instance):
            result = self.gcp.get_node_instance_zone('node-1')
            self.assertEqual(result, 'us-west1-b')

    def test_get_node_instance_name(self):
        """Test getting node instance name"""
        mock_instance = MagicMock()
        mock_instance.name = 'gke-cluster-node-1'

        # Patch get_node_instance to return our mock directly
        with patch.object(self.gcp, 'get_node_instance', return_value=mock_instance):
            result = self.gcp.get_node_instance_name('node-1')
            self.assertEqual(result, 'gke-cluster-node-1')

    def test_get_instance_id(self):
        """Test getting instance ID (alias for get_node_instance_name)"""
        # Patch get_node_instance_name since get_instance_id just calls it
        with patch.object(self.gcp, 'get_node_instance_name', return_value='gke-cluster-node-1'):
            result = self.gcp.get_instance_id('node-1')
            self.assertEqual(result, 'gke-cluster-node-1')

    def test_start_instances_success(self):
        """Test starting instances successfully"""
        instance_id = 'gke-cluster-node-1'

        # Mock get_node_instance_zone
        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.start = MagicMock()

            self.gcp.start_instances(instance_id)

            self.gcp.instance_client.start.assert_called_once()

    def test_start_instances_failure(self):
        """Test starting instances with failure"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.start = MagicMock(
                side_effect=Exception("GCP error")
            )

            with self.assertRaises(RuntimeError):
                self.gcp.start_instances(instance_id)

    def test_stop_instances_success(self):
        """Test stopping instances successfully"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.stop = MagicMock()

            self.gcp.stop_instances(instance_id)

            self.gcp.instance_client.stop.assert_called_once()

    def test_stop_instances_failure(self):
        """Test stopping instances with failure"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.stop = MagicMock(
                side_effect=Exception("GCP error")
            )

            with self.assertRaises(RuntimeError):
                self.gcp.stop_instances(instance_id)

    def test_suspend_instances_success(self):
        """Test suspending instances successfully"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.suspend = MagicMock()

            self.gcp.suspend_instances(instance_id)

            self.gcp.instance_client.suspend.assert_called_once()

    def test_suspend_instances_failure(self):
        """Test suspending instances with failure"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.suspend = MagicMock(
                side_effect=Exception("GCP error")
            )

            with self.assertRaises(RuntimeError):
                self.gcp.suspend_instances(instance_id)

    def test_terminate_instances_success(self):
        """Test terminating instances successfully"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.delete = MagicMock()

            self.gcp.terminate_instances(instance_id)

            self.gcp.instance_client.delete.assert_called_once()

    def test_terminate_instances_failure(self):
        """Test terminating instances with failure"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.delete = MagicMock(
                side_effect=Exception("GCP error")
            )

            with self.assertRaises(RuntimeError):
                self.gcp.terminate_instances(instance_id)

    def test_reboot_instances_success(self):
        """Test rebooting instances successfully"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.reset = MagicMock()

            self.gcp.reboot_instances(instance_id)

            self.gcp.instance_client.reset.assert_called_once()

    def test_reboot_instances_failure(self):
        """Test rebooting instances with failure"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.reset = MagicMock(
                side_effect=Exception("GCP error")
            )

            with self.assertRaises(RuntimeError):
                self.gcp.reboot_instances(instance_id)

    @patch('time.sleep')
    def test_get_instance_status_success(self, _mock_sleep):
        """Test getting instance status successfully"""
        instance_id = 'gke-cluster-node-1'

        mock_instance = MagicMock()
        mock_instance.status = 'RUNNING'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.get = MagicMock(return_value=mock_instance)

            result = self.gcp.get_instance_status(instance_id, 'RUNNING', 60)

            self.assertTrue(result)

    @patch('time.sleep')
    def test_get_instance_status_timeout(self, _mock_sleep):
        """Test getting instance status with timeout"""
        instance_id = 'gke-cluster-node-1'

        mock_instance = MagicMock()
        mock_instance.status = 'PROVISIONING'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.get = MagicMock(return_value=mock_instance)

            result = self.gcp.get_instance_status(instance_id, 'RUNNING', 5)

            self.assertFalse(result)

    @patch('time.sleep')
    def test_get_instance_status_failure(self, _mock_sleep):
        """Test getting instance status with failure"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_node_instance_zone', return_value='us-central1-a'):
            self.gcp.instance_client.get = MagicMock(
                side_effect=Exception("GCP error")
            )

            with self.assertRaises(RuntimeError):
                self.gcp.get_instance_status(instance_id, 'RUNNING', 60)

    def test_wait_until_suspended_success(self):
        """Test waiting until instance is suspended"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_instance_status', return_value=True) as mock_get_status:
            result = self.gcp.wait_until_suspended(instance_id, 60)

            self.assertTrue(result)
            mock_get_status.assert_called_once_with(instance_id, 'SUSPENDED', 60)

    def test_wait_until_suspended_failure(self):
        """Test waiting until instance is suspended with failure"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_instance_status', return_value=False):
            result = self.gcp.wait_until_suspended(instance_id, 60)

            self.assertFalse(result)

    def test_wait_until_running_success(self):
        """Test waiting until instance is running successfully"""
        instance_id = 'gke-cluster-node-1'
        affected_node = MagicMock(spec=AffectedNode)

        with patch('time.time', side_effect=[100, 110]):
            with patch.object(self.gcp, 'get_instance_status', return_value=True):
                result = self.gcp.wait_until_running(instance_id, 60, affected_node)

                self.assertTrue(result)
                affected_node.set_affected_node_status.assert_called_once_with('running', 10)

    def test_wait_until_running_without_affected_node(self):
        """Test waiting until running without affected node tracking"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_instance_status', return_value=True):
            result = self.gcp.wait_until_running(instance_id, 60, None)

            self.assertTrue(result)

    def test_wait_until_stopped_success(self):
        """Test waiting until instance is stopped successfully"""
        instance_id = 'gke-cluster-node-1'
        affected_node = MagicMock(spec=AffectedNode)

        with patch('time.time', side_effect=[100, 115]):
            with patch.object(self.gcp, 'get_instance_status', return_value=True):
                result = self.gcp.wait_until_stopped(instance_id, 60, affected_node)

                self.assertTrue(result)
                affected_node.set_affected_node_status.assert_called_once_with('stopped', 15)

    def test_wait_until_stopped_without_affected_node(self):
        """Test waiting until stopped without affected node tracking"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_instance_status', return_value=True):
            result = self.gcp.wait_until_stopped(instance_id, 60, None)

            self.assertTrue(result)

    def test_wait_until_terminated_success(self):
        """Test waiting until instance is terminated successfully"""
        instance_id = 'gke-cluster-node-1'
        affected_node = MagicMock(spec=AffectedNode)

        with patch('time.time', side_effect=[100, 120]):
            with patch.object(self.gcp, 'get_instance_status', return_value=True):
                result = self.gcp.wait_until_terminated(instance_id, 60, affected_node)

                self.assertTrue(result)
                affected_node.set_affected_node_status.assert_called_once_with('terminated', 20)

    def test_wait_until_terminated_without_affected_node(self):
        """Test waiting until terminated without affected node tracking"""
        instance_id = 'gke-cluster-node-1'

        with patch.object(self.gcp, 'get_instance_status', return_value=True):
            result = self.gcp.wait_until_terminated(instance_id, 60, None)

            self.assertTrue(result)


class TestGCPNodeScenarios(unittest.TestCase):
    """Test cases for gcp_node_scenarios class"""

    def setUp(self):
        """Set up test fixtures"""
        self.kubecli = MagicMock(spec=KrknKubernetes)
        self.affected_nodes_status = AffectedNodeStatus()

        # Mock the GCP class
        with patch('krkn.scenario_plugins.node_actions.gcp_node_scenarios.GCP') as mock_gcp_class:
            self.mock_gcp = MagicMock()
            mock_gcp_class.return_value = self.mock_gcp
            self.scenario = gcp_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=True,
                affected_nodes_status=self.affected_nodes_status
            )

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_start_scenario_success(self, mock_wait_ready):
        """Test node start scenario successfully"""
        node = 'gke-cluster-node-1'
        instance_id = 'gke-cluster-node-1'

        mock_instance = MagicMock()
        mock_instance.name = instance_id

        self.mock_gcp.get_node_instance.return_value = mock_instance
        self.mock_gcp.get_instance_name.return_value = instance_id
        self.mock_gcp.start_instances.return_value = None
        self.mock_gcp.wait_until_running.return_value = True

        self.scenario.node_start_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600,
            poll_interval=15
        )

        self.mock_gcp.get_node_instance.assert_called_once_with(node)
        self.mock_gcp.get_instance_name.assert_called_once_with(mock_instance)
        self.mock_gcp.start_instances.assert_called_once_with(instance_id)
        self.mock_gcp.wait_until_running.assert_called_once()
        mock_wait_ready.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)
        self.assertEqual(self.affected_nodes_status.affected_nodes[0].node_name, node)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_start_scenario_no_kube_check(self, mock_wait_ready):
        """Test node start scenario without kube check"""
        node = 'gke-cluster-node-1'
        instance_id = 'gke-cluster-node-1'

        # Create scenario with node_action_kube_check=False
        with patch('krkn.scenario_plugins.node_actions.gcp_node_scenarios.GCP') as mock_gcp_class:
            mock_gcp = MagicMock()
            mock_gcp_class.return_value = mock_gcp
            scenario = gcp_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            mock_instance = MagicMock()
            mock_instance.name = instance_id

            mock_gcp.get_node_instance.return_value = mock_instance
            mock_gcp.get_instance_name.return_value = instance_id
            mock_gcp.start_instances.return_value = None
            mock_gcp.wait_until_running.return_value = True

            scenario.node_start_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600,
                poll_interval=15
            )

            # Should not call wait_for_ready_status
            mock_wait_ready.assert_not_called()

    def test_node_start_scenario_failure(self):
        """Test node start scenario with failure"""
        node = 'gke-cluster-node-1'

        self.mock_gcp.get_node_instance.side_effect = Exception("GCP error")

        with self.assertRaises(RuntimeError):
            self.scenario.node_start_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600,
                poll_interval=15
            )

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    def test_node_stop_scenario_success(self, mock_wait_unknown):
        """Test node stop scenario successfully"""
        node = 'gke-cluster-node-1'
        instance_id = 'gke-cluster-node-1'

        mock_instance = MagicMock()
        mock_instance.name = instance_id

        self.mock_gcp.get_node_instance.return_value = mock_instance
        self.mock_gcp.get_instance_name.return_value = instance_id
        self.mock_gcp.stop_instances.return_value = None
        self.mock_gcp.wait_until_stopped.return_value = True

        self.scenario.node_stop_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600,
            poll_interval=15
        )

        self.mock_gcp.get_node_instance.assert_called_once_with(node)
        self.mock_gcp.get_instance_name.assert_called_once_with(mock_instance)
        self.mock_gcp.stop_instances.assert_called_once_with(instance_id)
        self.mock_gcp.wait_until_stopped.assert_called_once()
        mock_wait_unknown.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    def test_node_stop_scenario_no_kube_check(self, mock_wait_unknown):
        """Test node stop scenario without kube check"""
        node = 'gke-cluster-node-1'
        instance_id = 'gke-cluster-node-1'

        # Create scenario with node_action_kube_check=False
        with patch('krkn.scenario_plugins.node_actions.gcp_node_scenarios.GCP') as mock_gcp_class:
            mock_gcp = MagicMock()
            mock_gcp_class.return_value = mock_gcp
            scenario = gcp_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            mock_instance = MagicMock()
            mock_instance.name = instance_id

            mock_gcp.get_node_instance.return_value = mock_instance
            mock_gcp.get_instance_name.return_value = instance_id
            mock_gcp.stop_instances.return_value = None
            mock_gcp.wait_until_stopped.return_value = True

            scenario.node_stop_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600,
                poll_interval=15
            )

            # Should not call wait_for_unknown_status
            mock_wait_unknown.assert_not_called()

    def test_node_stop_scenario_failure(self):
        """Test node stop scenario with failure"""
        node = 'gke-cluster-node-1'

        self.mock_gcp.get_node_instance.side_effect = Exception("GCP error")

        with self.assertRaises(RuntimeError):
            self.scenario.node_stop_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600,
                poll_interval=15
            )

    @patch('time.sleep')
    def test_node_termination_scenario_success(self, _mock_sleep):
        """Test node termination scenario successfully"""
        node = 'gke-cluster-node-1'
        instance_id = 'gke-cluster-node-1'

        mock_instance = MagicMock()
        mock_instance.name = instance_id

        self.mock_gcp.get_node_instance.return_value = mock_instance
        self.mock_gcp.get_instance_name.return_value = instance_id
        self.mock_gcp.terminate_instances.return_value = None
        self.mock_gcp.wait_until_terminated.return_value = True
        self.kubecli.list_nodes.return_value = []

        self.scenario.node_termination_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600,
            poll_interval=15
        )

        self.mock_gcp.get_node_instance.assert_called_once_with(node)
        self.mock_gcp.get_instance_name.assert_called_once_with(mock_instance)
        self.mock_gcp.terminate_instances.assert_called_once_with(instance_id)
        self.mock_gcp.wait_until_terminated.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('time.sleep')
    def test_node_termination_scenario_node_still_exists(self, _mock_sleep):
        """Test node termination scenario when node still exists"""
        node = 'gke-cluster-node-1'
        instance_id = 'gke-cluster-node-1'

        mock_instance = MagicMock()
        mock_instance.name = instance_id

        self.mock_gcp.get_node_instance.return_value = mock_instance
        self.mock_gcp.get_instance_name.return_value = instance_id
        self.mock_gcp.terminate_instances.return_value = None
        self.mock_gcp.wait_until_terminated.return_value = True
        # Node still in list after timeout
        self.kubecli.list_nodes.return_value = [node]

        with self.assertRaises(RuntimeError):
            self.scenario.node_termination_scenario(
                instance_kill_count=1,
                node=node,
                timeout=2,
                poll_interval=15
            )

    def test_node_termination_scenario_failure(self):
        """Test node termination scenario with failure"""
        node = 'gke-cluster-node-1'

        self.mock_gcp.get_node_instance.side_effect = Exception("GCP error")

        with self.assertRaises(RuntimeError):
            self.scenario.node_termination_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600,
                poll_interval=15
            )

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_reboot_scenario_success(self, mock_wait_ready, mock_wait_unknown):
        """Test node reboot scenario successfully"""
        node = 'gke-cluster-node-1'
        instance_id = 'gke-cluster-node-1'

        mock_instance = MagicMock()
        mock_instance.name = instance_id

        self.mock_gcp.get_node_instance.return_value = mock_instance
        self.mock_gcp.get_instance_name.return_value = instance_id
        self.mock_gcp.reboot_instances.return_value = None
        self.mock_gcp.wait_until_running.return_value = True

        self.scenario.node_reboot_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600
        )

        self.mock_gcp.get_node_instance.assert_called_once_with(node)
        self.mock_gcp.get_instance_name.assert_called_once_with(mock_instance)
        self.mock_gcp.reboot_instances.assert_called_once_with(instance_id)
        self.mock_gcp.wait_until_running.assert_called_once()
        # Should be called twice in GCP implementation
        self.assertEqual(mock_wait_unknown.call_count, 1)
        self.assertEqual(mock_wait_ready.call_count, 1)
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_reboot_scenario_no_kube_check(self, mock_wait_ready, mock_wait_unknown):
        """Test node reboot scenario without kube check"""
        node = 'gke-cluster-node-1'
        instance_id = 'gke-cluster-node-1'

        # Create scenario with node_action_kube_check=False
        with patch('krkn.scenario_plugins.node_actions.gcp_node_scenarios.GCP') as mock_gcp_class:
            mock_gcp = MagicMock()
            mock_gcp_class.return_value = mock_gcp
            scenario = gcp_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            mock_instance = MagicMock()
            mock_instance.name = instance_id

            mock_gcp.get_node_instance.return_value = mock_instance
            mock_gcp.get_instance_name.return_value = instance_id
            mock_gcp.reboot_instances.return_value = None
            mock_gcp.wait_until_running.return_value = True

            scenario.node_reboot_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600
            )

            # Should not call wait functions
            mock_wait_unknown.assert_not_called()
            mock_wait_ready.assert_not_called()

    def test_node_reboot_scenario_failure(self):
        """Test node reboot scenario with failure"""
        node = 'gke-cluster-node-1'

        self.mock_gcp.get_node_instance.side_effect = Exception("GCP error")

        with self.assertRaises(RuntimeError):
            self.scenario.node_reboot_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600
            )

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_start_scenario_multiple_kills(self, mock_wait_ready):
        """Test node start scenario with multiple kill counts"""
        node = 'gke-cluster-node-1'
        instance_id = 'gke-cluster-node-1'

        mock_instance = MagicMock()
        mock_instance.name = instance_id

        self.mock_gcp.get_node_instance.return_value = mock_instance
        self.mock_gcp.get_instance_name.return_value = instance_id
        self.mock_gcp.start_instances.return_value = None
        self.mock_gcp.wait_until_running.return_value = True

        self.scenario.node_start_scenario(
            instance_kill_count=3,
            node=node,
            timeout=600,
            poll_interval=15
        )

        self.assertEqual(self.mock_gcp.start_instances.call_count, 3)
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 3)


if __name__ == "__main__":
    unittest.main()
