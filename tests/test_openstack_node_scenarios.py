#!/usr/bin/env python3

"""
Test suite for OpenStack node scenarios

This test suite covers both the OPENSTACKCLOUD class and openstack_node_scenarios class
using mocks to avoid actual OpenStack CLI calls.

Usage:
    python -m coverage run -a -m unittest tests/test_openstack_node_scenarios.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch, Mock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus
from krkn.scenario_plugins.node_actions.openstack_node_scenarios import (
    OPENSTACKCLOUD,
    openstack_node_scenarios
)


class TestOPENSTACKCLOUD(unittest.TestCase):
    """Test cases for OPENSTACKCLOUD class"""

    def setUp(self):
        """Set up test fixtures"""
        self.openstack = OPENSTACKCLOUD()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.openstack = None

    def test_openstackcloud_init(self):
        """Test OPENSTACKCLOUD class initialization"""
        self.assertEqual(self.openstack.Wait, 30)

    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD.get_openstack_nodename')
    def test_get_instance_id(self, mock_get_nodename):
        """Test getting instance ID by node IP"""
        node_ip = '10.0.1.100'
        node_name = 'test-openstack-node'

        mock_get_nodename.return_value = node_name

        result = self.openstack.get_instance_id(node_ip)

        self.assertEqual(result, node_name)
        mock_get_nodename.assert_called_once_with(node_ip)

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_start_instances_success(self, mock_invoke, mock_logging):
        """Test starting instance successfully"""
        node_name = 'test-node'

        self.openstack.start_instances(node_name)

        mock_invoke.assert_called_once_with('openstack server start %s' % node_name)
        mock_logging.assert_called()
        self.assertIn("started", str(mock_logging.call_args))

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_start_instances_failure(self, mock_invoke, mock_logging):
        """Test starting instance with failure"""
        node_name = 'test-node'
        mock_invoke.side_effect = Exception("OpenStack error")

        with self.assertRaises(RuntimeError):
            self.openstack.start_instances(node_name)

        mock_logging.assert_called()
        self.assertIn("Failed to start", str(mock_logging.call_args))

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_stop_instances_success(self, mock_invoke, mock_logging):
        """Test stopping instance successfully"""
        node_name = 'test-node'

        self.openstack.stop_instances(node_name)

        mock_invoke.assert_called_once_with('openstack server stop %s' % node_name)
        mock_logging.assert_called()
        self.assertIn("stopped", str(mock_logging.call_args))

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_stop_instances_failure(self, mock_invoke, mock_logging):
        """Test stopping instance with failure"""
        node_name = 'test-node'
        mock_invoke.side_effect = Exception("OpenStack error")

        with self.assertRaises(RuntimeError):
            self.openstack.stop_instances(node_name)

        mock_logging.assert_called()
        self.assertIn("Failed to stop", str(mock_logging.call_args))

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_reboot_instances_success(self, mock_invoke, mock_logging):
        """Test rebooting instance successfully"""
        node_name = 'test-node'

        self.openstack.reboot_instances(node_name)

        mock_invoke.assert_called_once_with('openstack server reboot --soft %s' % node_name)
        mock_logging.assert_called()
        self.assertIn("rebooted", str(mock_logging.call_args))

    @patch('logging.error')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_reboot_instances_failure(self, mock_invoke, mock_logging):
        """Test rebooting instance with failure"""
        node_name = 'test-node'
        mock_invoke.side_effect = Exception("OpenStack error")

        with self.assertRaises(RuntimeError):
            self.openstack.reboot_instances(node_name)

        mock_logging.assert_called()
        self.assertIn("Failed to reboot", str(mock_logging.call_args))

    @patch('time.time')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD.get_instance_status')
    def test_wait_until_running_success(self, mock_get_status, mock_time):
        """Test waiting until instance is running successfully"""
        node_name = 'test-node'
        timeout = 300

        mock_time.side_effect = [100, 110]
        mock_get_status.return_value = True

        affected_node = Mock(spec=AffectedNode)
        result = self.openstack.wait_until_running(node_name, timeout, affected_node)

        self.assertTrue(result)
        mock_get_status.assert_called_once_with(node_name, "ACTIVE", timeout)
        affected_node.set_affected_node_status.assert_called_once_with("running", 10)

    @patch('time.time')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD.get_instance_status')
    def test_wait_until_running_without_affected_node(self, mock_get_status, mock_time):
        """Test waiting until running without affected node tracking"""
        node_name = 'test-node'
        timeout = 300

        mock_get_status.return_value = True

        result = self.openstack.wait_until_running(node_name, timeout, None)

        self.assertTrue(result)

    @patch('time.time')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD.get_instance_status')
    def test_wait_until_stopped_success(self, mock_get_status, mock_time):
        """Test waiting until instance is stopped successfully"""
        node_name = 'test-node'
        timeout = 300

        mock_time.side_effect = [100, 115]
        mock_get_status.return_value = True

        affected_node = Mock(spec=AffectedNode)
        result = self.openstack.wait_until_stopped(node_name, timeout, affected_node)

        self.assertTrue(result)
        mock_get_status.assert_called_once_with(node_name, "SHUTOFF", timeout)
        affected_node.set_affected_node_status.assert_called_once_with("stopped", 15)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_get_instance_status_success(self, mock_invoke, mock_logging, mock_sleep):
        """Test getting instance status when it matches expected status"""
        node_name = 'test-node'
        expected_status = 'ACTIVE'
        timeout = 60

        mock_invoke.return_value = 'ACTIVE'

        result = self.openstack.get_instance_status(node_name, expected_status, timeout)

        self.assertTrue(result)
        mock_invoke.assert_called()

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_get_instance_status_timeout(self, mock_invoke, mock_logging, mock_sleep):
        """Test getting instance status with timeout"""
        node_name = 'test-node'
        expected_status = 'ACTIVE'
        timeout = 2

        mock_invoke.return_value = 'SHUTOFF'

        result = self.openstack.get_instance_status(node_name, expected_status, timeout)

        self.assertFalse(result)

    @patch('time.sleep')
    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_get_instance_status_with_whitespace(self, mock_invoke, mock_logging, mock_sleep):
        """Test getting instance status with whitespace in response"""
        node_name = 'test-node'
        expected_status = 'ACTIVE'
        timeout = 60

        mock_invoke.return_value = '  ACTIVE  '

        result = self.openstack.get_instance_status(node_name, expected_status, timeout)

        self.assertTrue(result)

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_get_openstack_nodename_success(self, mock_invoke, mock_logging):
        """Test getting OpenStack node name by IP"""
        node_ip = '10.0.1.100'

        # Mock OpenStack server list output
        mock_output = """| 12345 | test-node | ACTIVE | network1=10.0.1.100 |"""
        mock_invoke.return_value = mock_output

        result = self.openstack.get_openstack_nodename(node_ip)

        self.assertEqual(result, 'test-node')
        mock_invoke.assert_called_once()

    @patch('logging.info')
    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_get_openstack_nodename_multiple_servers(self, mock_invoke, mock_logging):
        """Test getting OpenStack node name with multiple servers"""
        node_ip = '10.0.1.101'

        # Mock OpenStack server list output with multiple servers
        mock_output = """| 12345 | test-node-1 | ACTIVE | network1=10.0.1.100 |
| 67890 | test-node-2 | ACTIVE | network1=10.0.1.101 |"""
        mock_invoke.return_value = mock_output

        result = self.openstack.get_openstack_nodename(node_ip)

        self.assertEqual(result, 'test-node-2')

    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.runcommand.invoke')
    def test_get_openstack_nodename_no_match(self, mock_invoke):
        """Test getting OpenStack node name with no matching IP"""
        node_ip = '10.0.1.200'

        mock_output = """| 12345 | test-node | ACTIVE | network1=10.0.1.100 |"""
        mock_invoke.return_value = mock_output

        result = self.openstack.get_openstack_nodename(node_ip)

        self.assertIsNone(result)


class TestOpenstackNodeScenarios(unittest.TestCase):
    """Test cases for openstack_node_scenarios class"""

    def setUp(self):
        """Set up test fixtures"""
        self.kubecli = MagicMock(spec=KrknKubernetes)
        self.affected_nodes_status = AffectedNodeStatus()

        # Mock the OPENSTACKCLOUD class
        with patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD') as mock_openstack_class:
            self.mock_openstack = MagicMock()
            mock_openstack_class.return_value = self.mock_openstack
            self.scenario = openstack_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=True,
                affected_nodes_status=self.affected_nodes_status
            )

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.scenario = None
        self.kubecli = None
        self.mock_openstack = None
        self.affected_nodes_status = None

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_start_scenario_success(self, mock_wait_ready):
        """Test node start scenario successfully"""
        node = 'test-node'
        node_ip = '10.0.1.100'
        openstack_node_name = 'openstack-test-node'

        self.kubecli.get_node_ip.return_value = node_ip
        self.mock_openstack.get_instance_id.return_value = openstack_node_name
        self.mock_openstack.start_instances.return_value = None
        self.mock_openstack.wait_until_running.return_value = True

        self.scenario.node_start_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600,
            poll_interval=15
        )

        self.kubecli.get_node_ip.assert_called_once_with(node)
        self.mock_openstack.get_instance_id.assert_called_once_with(node_ip)
        self.mock_openstack.start_instances.assert_called_once_with(openstack_node_name)
        self.mock_openstack.wait_until_running.assert_called_once()
        mock_wait_ready.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_start_scenario_no_kube_check(self, mock_wait_ready):
        """Test node start scenario without kube check"""
        node = 'test-node'
        node_ip = '10.0.1.100'
        openstack_node_name = 'openstack-test-node'

        # Create scenario with node_action_kube_check=False
        with patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD') as mock_openstack_class:
            mock_openstack = MagicMock()
            mock_openstack_class.return_value = mock_openstack
            scenario = openstack_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            self.kubecli.get_node_ip.return_value = node_ip
            mock_openstack.get_instance_id.return_value = openstack_node_name
            mock_openstack.start_instances.return_value = None
            mock_openstack.wait_until_running.return_value = True

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
        node = 'test-node'
        node_ip = '10.0.1.100'

        self.kubecli.get_node_ip.return_value = node_ip
        self.mock_openstack.get_instance_id.side_effect = Exception("OpenStack error")

        with self.assertRaises(RuntimeError):
            self.scenario.node_start_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600,
                poll_interval=15
            )

    def test_node_start_scenario_multiple_kills(self):
        """Test node start scenario with multiple kill counts"""
        node = 'test-node'
        node_ip = '10.0.1.100'
        openstack_node_name = 'openstack-test-node'

        with patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD') as mock_openstack_class:
            mock_openstack = MagicMock()
            mock_openstack_class.return_value = mock_openstack
            scenario = openstack_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            self.kubecli.get_node_ip.return_value = node_ip
            mock_openstack.get_instance_id.return_value = openstack_node_name
            mock_openstack.start_instances.return_value = None
            mock_openstack.wait_until_running.return_value = True

            scenario.node_start_scenario(
                instance_kill_count=3,
                node=node,
                timeout=600,
                poll_interval=15
            )

            self.assertEqual(mock_openstack.start_instances.call_count, 3)
            self.assertEqual(len(scenario.affected_nodes_status.affected_nodes), 3)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_not_ready_status')
    def test_node_stop_scenario_success(self, mock_wait_not_ready):
        """Test node stop scenario successfully"""
        node = 'test-node'
        node_ip = '10.0.1.100'
        openstack_node_name = 'openstack-test-node'

        self.kubecli.get_node_ip.return_value = node_ip
        self.mock_openstack.get_instance_id.return_value = openstack_node_name
        self.mock_openstack.stop_instances.return_value = None
        self.mock_openstack.wait_until_stopped.return_value = True

        self.scenario.node_stop_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600,
            poll_interval=15
        )

        self.kubecli.get_node_ip.assert_called_once_with(node)
        self.mock_openstack.get_instance_id.assert_called_once_with(node_ip)
        self.mock_openstack.stop_instances.assert_called_once_with(openstack_node_name)
        self.mock_openstack.wait_until_stopped.assert_called_once()
        mock_wait_not_ready.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_not_ready_status')
    def test_node_stop_scenario_no_kube_check(self, mock_wait_not_ready):
        """Test node stop scenario without kube check"""
        node = 'test-node'
        node_ip = '10.0.1.100'
        openstack_node_name = 'openstack-test-node'

        # Create scenario with node_action_kube_check=False
        with patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD') as mock_openstack_class:
            mock_openstack = MagicMock()
            mock_openstack_class.return_value = mock_openstack
            scenario = openstack_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            self.kubecli.get_node_ip.return_value = node_ip
            mock_openstack.get_instance_id.return_value = openstack_node_name
            mock_openstack.stop_instances.return_value = None
            mock_openstack.wait_until_stopped.return_value = True

            scenario.node_stop_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600,
                poll_interval=15
            )

            # Should not call wait_for_not_ready_status
            mock_wait_not_ready.assert_not_called()

    def test_node_stop_scenario_failure(self):
        """Test node stop scenario with failure"""
        node = 'test-node'
        node_ip = '10.0.1.100'

        self.kubecli.get_node_ip.return_value = node_ip
        self.mock_openstack.get_instance_id.side_effect = Exception("OpenStack error")

        with self.assertRaises(RuntimeError):
            self.scenario.node_stop_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600,
                poll_interval=15
            )

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    def test_node_reboot_scenario_success(self, mock_wait_unknown, mock_wait_ready):
        """Test node reboot scenario successfully"""
        node = 'test-node'
        node_ip = '10.0.1.100'
        openstack_node_name = 'openstack-test-node'

        self.kubecli.get_node_ip.return_value = node_ip
        self.mock_openstack.get_instance_id.return_value = openstack_node_name
        self.mock_openstack.reboot_instances.return_value = None

        self.scenario.node_reboot_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600
        )

        self.kubecli.get_node_ip.assert_called_once_with(node)
        self.mock_openstack.get_instance_id.assert_called_once_with(node_ip)
        self.mock_openstack.reboot_instances.assert_called_once_with(openstack_node_name)
        mock_wait_unknown.assert_called_once()
        mock_wait_ready.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    def test_node_reboot_scenario_no_kube_check(self, mock_wait_unknown, mock_wait_ready):
        """Test node reboot scenario without kube check"""
        node = 'test-node'
        node_ip = '10.0.1.100'
        openstack_node_name = 'openstack-test-node'

        # Create scenario with node_action_kube_check=False
        with patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD') as mock_openstack_class:
            mock_openstack = MagicMock()
            mock_openstack_class.return_value = mock_openstack
            scenario = openstack_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            self.kubecli.get_node_ip.return_value = node_ip
            mock_openstack.get_instance_id.return_value = openstack_node_name
            mock_openstack.reboot_instances.return_value = None

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
        node = 'test-node'
        node_ip = '10.0.1.100'

        self.kubecli.get_node_ip.return_value = node_ip
        self.mock_openstack.get_instance_id.side_effect = Exception("OpenStack error")

        with self.assertRaises(RuntimeError):
            self.scenario.node_reboot_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600
            )

    def test_node_reboot_scenario_multiple_kills(self):
        """Test node reboot scenario with multiple kill counts"""
        node = 'test-node'
        node_ip = '10.0.1.100'
        openstack_node_name = 'openstack-test-node'

        with patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD') as mock_openstack_class:
            mock_openstack = MagicMock()
            mock_openstack_class.return_value = mock_openstack
            scenario = openstack_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            self.kubecli.get_node_ip.return_value = node_ip
            mock_openstack.get_instance_id.return_value = openstack_node_name
            mock_openstack.reboot_instances.return_value = None

            scenario.node_reboot_scenario(
                instance_kill_count=3,
                node=node,
                timeout=600
            )

            self.assertEqual(mock_openstack.reboot_instances.call_count, 3)
            self.assertEqual(len(scenario.affected_nodes_status.affected_nodes), 3)

    def test_helper_node_start_scenario_success(self):
        """Test helper node start scenario successfully"""
        node_ip = '192.168.1.50'
        openstack_node_name = 'helper-node'

        self.mock_openstack.get_openstack_nodename.return_value = openstack_node_name
        self.mock_openstack.start_instances.return_value = None
        self.mock_openstack.wait_until_running.return_value = True

        self.scenario.helper_node_start_scenario(
            instance_kill_count=1,
            node_ip=node_ip,
            timeout=600
        )

        self.mock_openstack.get_openstack_nodename.assert_called_once_with(node_ip.strip())
        self.mock_openstack.start_instances.assert_called_once_with(openstack_node_name)
        self.mock_openstack.wait_until_running.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    def test_helper_node_start_scenario_failure(self):
        """Test helper node start scenario with failure"""
        node_ip = '192.168.1.50'

        self.mock_openstack.get_openstack_nodename.side_effect = Exception("OpenStack error")

        with self.assertRaises(RuntimeError):
            self.scenario.helper_node_start_scenario(
                instance_kill_count=1,
                node_ip=node_ip,
                timeout=600
            )

    def test_helper_node_start_scenario_multiple_kills(self):
        """Test helper node start scenario with multiple kill counts"""
        node_ip = '192.168.1.50'
        openstack_node_name = 'helper-node'

        with patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD') as mock_openstack_class:
            mock_openstack = MagicMock()
            mock_openstack_class.return_value = mock_openstack
            scenario = openstack_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            mock_openstack.get_openstack_nodename.return_value = openstack_node_name
            mock_openstack.start_instances.return_value = None
            mock_openstack.wait_until_running.return_value = True

            scenario.helper_node_start_scenario(
                instance_kill_count=2,
                node_ip=node_ip,
                timeout=600
            )

            self.assertEqual(mock_openstack.start_instances.call_count, 2)
            self.assertEqual(len(scenario.affected_nodes_status.affected_nodes), 2)

    def test_helper_node_stop_scenario_success(self):
        """Test helper node stop scenario successfully"""
        node_ip = '192.168.1.50'
        openstack_node_name = 'helper-node'

        self.mock_openstack.get_openstack_nodename.return_value = openstack_node_name
        self.mock_openstack.stop_instances.return_value = None
        self.mock_openstack.wait_until_stopped.return_value = True

        self.scenario.helper_node_stop_scenario(
            instance_kill_count=1,
            node_ip=node_ip,
            timeout=600
        )

        self.mock_openstack.get_openstack_nodename.assert_called_once_with(node_ip.strip())
        self.mock_openstack.stop_instances.assert_called_once_with(openstack_node_name)
        self.mock_openstack.wait_until_stopped.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    def test_helper_node_stop_scenario_failure(self):
        """Test helper node stop scenario with failure"""
        node_ip = '192.168.1.50'

        self.mock_openstack.get_openstack_nodename.side_effect = Exception("OpenStack error")

        with self.assertRaises(RuntimeError):
            self.scenario.helper_node_stop_scenario(
                instance_kill_count=1,
                node_ip=node_ip,
                timeout=600
            )

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.check_service_status')
    def test_helper_node_service_status_success(self, mock_check_service):
        """Test helper node service status check successfully"""
        node_ip = '192.168.1.50'
        service = 'kubelet'
        ssh_private_key = '/path/to/key'
        timeout = 300

        mock_check_service.return_value = None

        self.scenario.helper_node_service_status(
            node_ip=node_ip,
            service=service,
            ssh_private_key=ssh_private_key,
            timeout=timeout
        )

        mock_check_service.assert_called_once_with(
            node_ip.strip(),
            service,
            ssh_private_key,
            timeout
        )

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.check_service_status')
    def test_helper_node_service_status_failure(self, mock_check_service):
        """Test helper node service status check with failure"""
        node_ip = '192.168.1.50'
        service = 'kubelet'
        ssh_private_key = '/path/to/key'
        timeout = 300

        mock_check_service.side_effect = Exception("Service check failed")

        with self.assertRaises(RuntimeError):
            self.scenario.helper_node_service_status(
                node_ip=node_ip,
                service=service,
                ssh_private_key=ssh_private_key,
                timeout=timeout
            )

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.check_service_status')
    def test_helper_node_service_status_with_whitespace_ip(self, mock_check_service):
        """Test helper node service status with whitespace in IP"""
        node_ip = '  192.168.1.50  '
        service = 'kubelet'
        ssh_private_key = '/path/to/key'
        timeout = 300

        mock_check_service.return_value = None

        self.scenario.helper_node_service_status(
            node_ip=node_ip,
            service=service,
            ssh_private_key=ssh_private_key,
            timeout=timeout
        )

        # Verify IP was stripped
        mock_check_service.assert_called_once_with(
            node_ip.strip(),
            service,
            ssh_private_key,
            timeout
        )


if __name__ == "__main__":
    unittest.main()
