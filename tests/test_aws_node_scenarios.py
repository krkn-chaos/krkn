#!/usr/bin/env python3

"""
Test suite for AWS node scenarios

This test suite covers both the AWS class and aws_node_scenarios class
using mocks to avoid actual AWS API calls.

Usage:
    python -m coverage run -a -m unittest tests/test_aws_node_scenarios.py -v

Assisted By: Claude Code
"""

import unittest
import sys
from unittest.mock import MagicMock, patch

# Mock external dependencies before any imports that use them
sys.modules['boto3'] = MagicMock()
sys.modules['paramiko'] = MagicMock()

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus
from krkn.scenario_plugins.node_actions.aws_node_scenarios import AWS, aws_node_scenarios


class TestAWS(unittest.TestCase):
    """Test cases for AWS class"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock boto3 to avoid actual AWS calls
        self.boto_client_patcher = patch('boto3.client')
        self.boto_resource_patcher = patch('boto3.resource')

        self.mock_client = self.boto_client_patcher.start()
        self.mock_resource = self.boto_resource_patcher.start()

        # Create AWS instance with mocked boto3
        self.aws = AWS()

    def tearDown(self):
        """Clean up after tests"""
        self.boto_client_patcher.stop()
        self.boto_resource_patcher.stop()

    def test_aws_init(self):
        """Test AWS class initialization"""
        self.assertIsNotNone(self.aws.boto_client)
        self.assertIsNotNone(self.aws.boto_resource)
        self.assertIsNotNone(self.aws.boto_instance)

    def test_get_instance_id_by_dns_name(self):
        """Test getting instance ID by DNS name"""
        mock_response = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-1234567890abcdef0'
                }]
            }]
        }
        self.aws.boto_client.describe_instances = MagicMock(return_value=mock_response)

        instance_id = self.aws.get_instance_id('ip-10-0-1-100.ec2.internal')

        self.assertEqual(instance_id, 'i-1234567890abcdef0')
        self.aws.boto_client.describe_instances.assert_called_once()

    def test_get_instance_id_by_ip_address(self):
        """Test getting instance ID by IP address when DNS name fails"""
        # First call returns empty, second call returns the instance
        mock_response_empty = {'Reservations': []}
        mock_response_with_instance = {
            'Reservations': [{
                'Instances': [{
                    'InstanceId': 'i-1234567890abcdef0'
                }]
            }]
        }
        self.aws.boto_client.describe_instances = MagicMock(
            side_effect=[mock_response_empty, mock_response_with_instance]
        )

        instance_id = self.aws.get_instance_id('ip-10-0-1-100')

        self.assertEqual(instance_id, 'i-1234567890abcdef0')
        self.assertEqual(self.aws.boto_client.describe_instances.call_count, 2)

    def test_start_instances_success(self):
        """Test starting instances successfully"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_client.start_instances = MagicMock()

        self.aws.start_instances(instance_id)

        self.aws.boto_client.start_instances.assert_called_once_with(
            InstanceIds=[instance_id]
        )

    def test_start_instances_failure(self):
        """Test starting instances with failure"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_client.start_instances = MagicMock(
            side_effect=Exception("AWS error")
        )

        with self.assertRaises(RuntimeError):
            self.aws.start_instances(instance_id)

    def test_stop_instances_success(self):
        """Test stopping instances successfully"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_client.stop_instances = MagicMock()

        self.aws.stop_instances(instance_id)

        self.aws.boto_client.stop_instances.assert_called_once_with(
            InstanceIds=[instance_id]
        )

    def test_stop_instances_failure(self):
        """Test stopping instances with failure"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_client.stop_instances = MagicMock(
            side_effect=Exception("AWS error")
        )

        with self.assertRaises(RuntimeError):
            self.aws.stop_instances(instance_id)

    def test_terminate_instances_success(self):
        """Test terminating instances successfully"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_client.terminate_instances = MagicMock()

        self.aws.terminate_instances(instance_id)

        self.aws.boto_client.terminate_instances.assert_called_once_with(
            InstanceIds=[instance_id]
        )

    def test_terminate_instances_failure(self):
        """Test terminating instances with failure"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_client.terminate_instances = MagicMock(
            side_effect=Exception("AWS error")
        )

        with self.assertRaises(RuntimeError):
            self.aws.terminate_instances(instance_id)

    def test_reboot_instances_success(self):
        """Test rebooting instances successfully"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_client.reboot_instances = MagicMock()

        self.aws.reboot_instances(instance_id)

        self.aws.boto_client.reboot_instances.assert_called_once_with(
            InstanceIds=[instance_id]
        )

    def test_reboot_instances_failure(self):
        """Test rebooting instances with failure"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_client.reboot_instances = MagicMock(
            side_effect=Exception("AWS error")
        )

        with self.assertRaises(RuntimeError):
            self.aws.reboot_instances(instance_id)

    def test_wait_until_running_success(self):
        """Test waiting until instance is running successfully"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_instance.wait_until_running = MagicMock()

        result = self.aws.wait_until_running(instance_id, timeout=600, poll_interval=15)

        self.assertTrue(result)
        self.aws.boto_instance.wait_until_running.assert_called_once()

    def test_wait_until_running_with_affected_node(self):
        """Test waiting until running with affected node tracking"""
        instance_id = 'i-1234567890abcdef0'
        affected_node = MagicMock(spec=AffectedNode)
        self.aws.boto_instance.wait_until_running = MagicMock()

        with patch('time.time', side_effect=[100, 110]):
            result = self.aws.wait_until_running(
                instance_id,
                timeout=600,
                affected_node=affected_node,
                poll_interval=15
            )

        self.assertTrue(result)
        affected_node.set_affected_node_status.assert_called_once_with("running", 10)

    def test_wait_until_running_failure(self):
        """Test waiting until running with failure"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_instance.wait_until_running = MagicMock(
            side_effect=Exception("Timeout")
        )

        result = self.aws.wait_until_running(instance_id)

        self.assertFalse(result)

    def test_wait_until_stopped_success(self):
        """Test waiting until instance is stopped successfully"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_instance.wait_until_stopped = MagicMock()

        result = self.aws.wait_until_stopped(instance_id, timeout=600, poll_interval=15)

        self.assertTrue(result)
        self.aws.boto_instance.wait_until_stopped.assert_called_once()

    def test_wait_until_stopped_with_affected_node(self):
        """Test waiting until stopped with affected node tracking"""
        instance_id = 'i-1234567890abcdef0'
        affected_node = MagicMock(spec=AffectedNode)
        self.aws.boto_instance.wait_until_stopped = MagicMock()

        with patch('time.time', side_effect=[100, 115]):
            result = self.aws.wait_until_stopped(
                instance_id,
                timeout=600,
                affected_node=affected_node,
                poll_interval=15
            )

        self.assertTrue(result)
        affected_node.set_affected_node_status.assert_called_once_with("stopped", 15)

    def test_wait_until_stopped_failure(self):
        """Test waiting until stopped with failure"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_instance.wait_until_stopped = MagicMock(
            side_effect=Exception("Timeout")
        )

        result = self.aws.wait_until_stopped(instance_id)

        self.assertFalse(result)

    def test_wait_until_terminated_success(self):
        """Test waiting until instance is terminated successfully"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_instance.wait_until_terminated = MagicMock()

        result = self.aws.wait_until_terminated(instance_id, timeout=600, poll_interval=15)

        self.assertTrue(result)
        self.aws.boto_instance.wait_until_terminated.assert_called_once()

    def test_wait_until_terminated_with_affected_node(self):
        """Test waiting until terminated with affected node tracking"""
        instance_id = 'i-1234567890abcdef0'
        affected_node = MagicMock(spec=AffectedNode)
        self.aws.boto_instance.wait_until_terminated = MagicMock()

        with patch('time.time', side_effect=[100, 120]):
            result = self.aws.wait_until_terminated(
                instance_id,
                timeout=600,
                affected_node=affected_node,
                poll_interval=15
            )

        self.assertTrue(result)
        affected_node.set_affected_node_status.assert_called_once_with("terminated", 20)

    def test_wait_until_terminated_failure(self):
        """Test waiting until terminated with failure"""
        instance_id = 'i-1234567890abcdef0'
        self.aws.boto_instance.wait_until_terminated = MagicMock(
            side_effect=Exception("Timeout")
        )

        result = self.aws.wait_until_terminated(instance_id)

        self.assertFalse(result)

    def test_create_default_network_acl_success(self):
        """Test creating default network ACL successfully"""
        vpc_id = 'vpc-12345678'
        acl_id = 'acl-12345678'
        mock_response = {
            'NetworkAcl': {
                'NetworkAclId': acl_id
            }
        }
        self.aws.boto_client.create_network_acl = MagicMock(return_value=mock_response)

        result = self.aws.create_default_network_acl(vpc_id)

        self.assertEqual(result, acl_id)
        self.aws.boto_client.create_network_acl.assert_called_once_with(VpcId=vpc_id)

    def test_create_default_network_acl_failure(self):
        """Test creating default network ACL with failure"""
        vpc_id = 'vpc-12345678'
        self.aws.boto_client.create_network_acl = MagicMock(
            side_effect=Exception("AWS error")
        )

        with self.assertRaises(RuntimeError):
            self.aws.create_default_network_acl(vpc_id)

    def test_replace_network_acl_association_success(self):
        """Test replacing network ACL association successfully"""
        association_id = 'aclassoc-12345678'
        acl_id = 'acl-12345678'
        new_association_id = 'aclassoc-87654321'
        mock_response = {
            'NewAssociationId': new_association_id
        }
        self.aws.boto_client.replace_network_acl_association = MagicMock(
            return_value=mock_response
        )

        result = self.aws.replace_network_acl_association(association_id, acl_id)

        self.assertEqual(result, new_association_id)
        self.aws.boto_client.replace_network_acl_association.assert_called_once_with(
            AssociationId=association_id, NetworkAclId=acl_id
        )

    def test_replace_network_acl_association_failure(self):
        """Test replacing network ACL association with failure"""
        association_id = 'aclassoc-12345678'
        acl_id = 'acl-12345678'
        self.aws.boto_client.replace_network_acl_association = MagicMock(
            side_effect=Exception("AWS error")
        )

        with self.assertRaises(RuntimeError):
            self.aws.replace_network_acl_association(association_id, acl_id)

    def test_describe_network_acls_success(self):
        """Test describing network ACLs successfully"""
        vpc_id = 'vpc-12345678'
        subnet_id = 'subnet-12345678'
        acl_id = 'acl-12345678'
        associations = [{'NetworkAclId': acl_id, 'SubnetId': subnet_id}]
        mock_response = {
            'NetworkAcls': [{
                'Associations': associations
            }]
        }
        self.aws.boto_client.describe_network_acls = MagicMock(return_value=mock_response)

        result_associations, result_acl_id = self.aws.describe_network_acls(vpc_id, subnet_id)

        self.assertEqual(result_associations, associations)
        self.assertEqual(result_acl_id, acl_id)

    def test_describe_network_acls_failure(self):
        """Test describing network ACLs with failure"""
        vpc_id = 'vpc-12345678'
        subnet_id = 'subnet-12345678'
        self.aws.boto_client.describe_network_acls = MagicMock(
            side_effect=Exception("AWS error")
        )

        with self.assertRaises(RuntimeError):
            self.aws.describe_network_acls(vpc_id, subnet_id)

    def test_delete_network_acl_success(self):
        """Test deleting network ACL successfully"""
        acl_id = 'acl-12345678'
        self.aws.boto_client.delete_network_acl = MagicMock()

        self.aws.delete_network_acl(acl_id)

        self.aws.boto_client.delete_network_acl.assert_called_once_with(NetworkAclId=acl_id)

    def test_delete_network_acl_failure(self):
        """Test deleting network ACL with failure"""
        acl_id = 'acl-12345678'
        self.aws.boto_client.delete_network_acl = MagicMock(
            side_effect=Exception("AWS error")
        )

        with self.assertRaises(RuntimeError):
            self.aws.delete_network_acl(acl_id)

    def test_detach_volumes_success(self):
        """Test detaching volumes successfully"""
        volume_ids = ['vol-12345678', 'vol-87654321']
        self.aws.boto_client.detach_volume = MagicMock()

        self.aws.detach_volumes(volume_ids)

        self.assertEqual(self.aws.boto_client.detach_volume.call_count, 2)
        self.aws.boto_client.detach_volume.assert_any_call(VolumeId='vol-12345678', Force=True)
        self.aws.boto_client.detach_volume.assert_any_call(VolumeId='vol-87654321', Force=True)

    def test_detach_volumes_partial_failure(self):
        """Test detaching volumes with partial failure"""
        volume_ids = ['vol-12345678', 'vol-87654321']
        # First call succeeds, second fails - should not raise exception
        self.aws.boto_client.detach_volume = MagicMock(
            side_effect=[None, Exception("AWS error")]
        )

        # Should not raise exception, just log error
        self.aws.detach_volumes(volume_ids)

        self.assertEqual(self.aws.boto_client.detach_volume.call_count, 2)

    def test_attach_volume_success(self):
        """Test attaching volume successfully"""
        attachment = {
            'VolumeId': 'vol-12345678',
            'InstanceId': 'i-1234567890abcdef0',
            'Device': '/dev/sdf'
        }
        mock_volume = MagicMock()
        mock_volume.state = 'available'
        self.aws.boto_resource.Volume = MagicMock(return_value=mock_volume)
        self.aws.boto_client.attach_volume = MagicMock()

        self.aws.attach_volume(attachment)

        self.aws.boto_client.attach_volume.assert_called_once_with(
            InstanceId=attachment['InstanceId'],
            Device=attachment['Device'],
            VolumeId=attachment['VolumeId']
        )

    def test_attach_volume_already_in_use(self):
        """Test attaching volume that is already in use"""
        attachment = {
            'VolumeId': 'vol-12345678',
            'InstanceId': 'i-1234567890abcdef0',
            'Device': '/dev/sdf'
        }
        mock_volume = MagicMock()
        mock_volume.state = 'in-use'
        self.aws.boto_resource.Volume = MagicMock(return_value=mock_volume)
        self.aws.boto_client.attach_volume = MagicMock()

        self.aws.attach_volume(attachment)

        # Should not attempt to attach
        self.aws.boto_client.attach_volume.assert_not_called()

    def test_attach_volume_failure(self):
        """Test attaching volume with failure"""
        attachment = {
            'VolumeId': 'vol-12345678',
            'InstanceId': 'i-1234567890abcdef0',
            'Device': '/dev/sdf'
        }
        mock_volume = MagicMock()
        mock_volume.state = 'available'
        self.aws.boto_resource.Volume = MagicMock(return_value=mock_volume)
        self.aws.boto_client.attach_volume = MagicMock(
            side_effect=Exception("AWS error")
        )

        with self.assertRaises(RuntimeError):
            self.aws.attach_volume(attachment)

    def test_get_volumes_ids(self):
        """Test getting volume IDs from instance"""
        instance_id = ['i-1234567890abcdef0']
        mock_response = {
            'Reservations': [{
                'Instances': [{
                    'BlockDeviceMappings': [
                        {'DeviceName': '/dev/sda1', 'Ebs': {'VolumeId': 'vol-root'}},
                        {'DeviceName': '/dev/sdf', 'Ebs': {'VolumeId': 'vol-12345678'}},
                        {'DeviceName': '/dev/sdg', 'Ebs': {'VolumeId': 'vol-87654321'}}
                    ]
                }]
            }]
        }
        mock_instance = MagicMock()
        mock_instance.root_device_name = '/dev/sda1'
        self.aws.boto_resource.Instance = MagicMock(return_value=mock_instance)
        self.aws.boto_client.describe_instances = MagicMock(return_value=mock_response)

        volume_ids = self.aws.get_volumes_ids(instance_id)

        self.assertEqual(len(volume_ids), 2)
        self.assertIn('vol-12345678', volume_ids)
        self.assertIn('vol-87654321', volume_ids)
        self.assertNotIn('vol-root', volume_ids)

    def test_get_volume_attachment_details(self):
        """Test getting volume attachment details"""
        volume_ids = ['vol-12345678', 'vol-87654321']
        mock_response = {
            'Volumes': [
                {'VolumeId': 'vol-12345678', 'State': 'in-use'},
                {'VolumeId': 'vol-87654321', 'State': 'available'}
            ]
        }
        self.aws.boto_client.describe_volumes = MagicMock(return_value=mock_response)

        details = self.aws.get_volume_attachment_details(volume_ids)

        self.assertEqual(len(details), 2)
        self.assertEqual(details[0]['VolumeId'], 'vol-12345678')
        self.assertEqual(details[1]['VolumeId'], 'vol-87654321')

    def test_get_root_volume_id(self):
        """Test getting root volume ID"""
        instance_id = ['i-1234567890abcdef0']
        mock_instance = MagicMock()
        mock_instance.root_device_name = '/dev/sda1'
        self.aws.boto_resource.Instance = MagicMock(return_value=mock_instance)

        root_volume = self.aws.get_root_volume_id(instance_id)

        self.assertEqual(root_volume, '/dev/sda1')

    def test_get_volume_state(self):
        """Test getting volume state"""
        volume_id = 'vol-12345678'
        mock_volume = MagicMock()
        mock_volume.state = 'available'
        self.aws.boto_resource.Volume = MagicMock(return_value=mock_volume)

        state = self.aws.get_volume_state(volume_id)

        self.assertEqual(state, 'available')


class TestAWSNodeScenarios(unittest.TestCase):
    """Test cases for aws_node_scenarios class"""

    def setUp(self):
        """Set up test fixtures"""
        self.kubecli = MagicMock(spec=KrknKubernetes)
        self.affected_nodes_status = AffectedNodeStatus()

        # Mock the AWS class
        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            self.mock_aws = MagicMock()
            mock_aws_class.return_value = self.mock_aws
            self.scenario = aws_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=True,
                affected_nodes_status=self.affected_nodes_status
            )

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_start_scenario_success(self, mock_wait_ready):
        """Test node start scenario successfully"""
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'

        self.mock_aws.get_instance_id.return_value = instance_id
        self.mock_aws.start_instances.return_value = None
        self.mock_aws.wait_until_running.return_value = True

        self.scenario.node_start_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600,
            poll_interval=15
        )

        self.mock_aws.get_instance_id.assert_called_once_with(node)
        self.mock_aws.start_instances.assert_called_once_with(instance_id)
        self.mock_aws.wait_until_running.assert_called_once()
        mock_wait_ready.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)
        self.assertEqual(self.affected_nodes_status.affected_nodes[0].node_name, node)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_start_scenario_no_kube_check(self, mock_wait_ready):
        """Test node start scenario without kube check"""
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'

        # Create scenario with node_action_kube_check=False
        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            mock_aws = MagicMock()
            mock_aws_class.return_value = mock_aws
            scenario = aws_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            mock_aws.get_instance_id.return_value = instance_id
            mock_aws.start_instances.return_value = None
            mock_aws.wait_until_running.return_value = True

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
        node = 'ip-10-0-1-100.ec2.internal'

        self.mock_aws.get_instance_id.side_effect = Exception("AWS error")

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
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'

        self.mock_aws.get_instance_id.return_value = instance_id
        self.mock_aws.stop_instances.return_value = None
        self.mock_aws.wait_until_stopped.return_value = True

        self.scenario.node_stop_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600,
            poll_interval=15
        )

        self.mock_aws.get_instance_id.assert_called_once_with(node)
        self.mock_aws.stop_instances.assert_called_once_with(instance_id)
        self.mock_aws.wait_until_stopped.assert_called_once()
        mock_wait_unknown.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    def test_node_stop_scenario_no_kube_check(self, mock_wait_unknown):
        """Test node stop scenario without kube check"""
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'

        # Create scenario with node_action_kube_check=False
        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            mock_aws = MagicMock()
            mock_aws_class.return_value = mock_aws
            scenario = aws_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            mock_aws.get_instance_id.return_value = instance_id
            mock_aws.stop_instances.return_value = None
            mock_aws.wait_until_stopped.return_value = True

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
        node = 'ip-10-0-1-100.ec2.internal'

        self.mock_aws.get_instance_id.side_effect = Exception("AWS error")

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
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'

        self.mock_aws.get_instance_id.return_value = instance_id
        self.mock_aws.terminate_instances.return_value = None
        self.mock_aws.wait_until_terminated.return_value = True
        self.kubecli.list_nodes.return_value = []

        self.scenario.node_termination_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600,
            poll_interval=15
        )

        self.mock_aws.get_instance_id.assert_called_once_with(node)
        self.mock_aws.terminate_instances.assert_called_once_with(instance_id)
        self.mock_aws.wait_until_terminated.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('time.sleep')
    def test_node_termination_scenario_node_still_exists(self, _mock_sleep):
        """Test node termination scenario when node still exists"""
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'

        self.mock_aws.get_instance_id.return_value = instance_id
        self.mock_aws.terminate_instances.return_value = None
        self.mock_aws.wait_until_terminated.return_value = True
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
        node = 'ip-10-0-1-100.ec2.internal'

        self.mock_aws.get_instance_id.side_effect = Exception("AWS error")

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
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'

        self.mock_aws.get_instance_id.return_value = instance_id
        self.mock_aws.reboot_instances.return_value = None

        self.scenario.node_reboot_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600
        )

        self.mock_aws.get_instance_id.assert_called_once_with(node)
        self.mock_aws.reboot_instances.assert_called_once_with(instance_id)
        mock_wait_unknown.assert_called_once()
        mock_wait_ready.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status')
    def test_node_reboot_scenario_no_kube_check(self, mock_wait_ready, mock_wait_unknown):
        """Test node reboot scenario without kube check"""
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'

        # Create scenario with node_action_kube_check=False
        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            mock_aws = MagicMock()
            mock_aws_class.return_value = mock_aws
            scenario = aws_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            mock_aws.get_instance_id.return_value = instance_id
            mock_aws.reboot_instances.return_value = None

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
        node = 'ip-10-0-1-100.ec2.internal'

        self.mock_aws.get_instance_id.side_effect = Exception("AWS error")

        with self.assertRaises(RuntimeError):
            self.scenario.node_reboot_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600
            )

    def test_node_reboot_scenario_multiple_kills(self):
        """Test node reboot scenario with multiple kill counts"""
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'

        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            mock_aws = MagicMock()
            mock_aws_class.return_value = mock_aws
            scenario = aws_node_scenarios(
                kubecli=self.kubecli,
                node_action_kube_check=False,
                affected_nodes_status=AffectedNodeStatus()
            )

            mock_aws.get_instance_id.return_value = instance_id
            mock_aws.reboot_instances.return_value = None

            scenario.node_reboot_scenario(
                instance_kill_count=3,
                node=node,
                timeout=600
            )

            self.assertEqual(mock_aws.reboot_instances.call_count, 3)
            self.assertEqual(len(scenario.affected_nodes_status.affected_nodes), 3)

    def test_get_disk_attachment_info_success(self):
        """Test getting disk attachment info successfully"""
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'
        volume_ids = ['vol-12345678']
        attachment_details = [
            {
                'VolumeId': 'vol-12345678',
                'Attachments': [{
                    'InstanceId': instance_id,
                    'Device': '/dev/sdf'
                }]
            }
        ]

        self.mock_aws.get_instance_id.return_value = instance_id
        self.mock_aws.get_volumes_ids.return_value = volume_ids
        self.mock_aws.get_volume_attachment_details.return_value = attachment_details

        result = self.scenario.get_disk_attachment_info(
            instance_kill_count=1,
            node=node
        )

        self.assertEqual(result, attachment_details)
        self.mock_aws.get_instance_id.assert_called_once_with(node)
        self.mock_aws.get_volumes_ids.assert_called_once()
        self.mock_aws.get_volume_attachment_details.assert_called_once_with(volume_ids)

    def test_get_disk_attachment_info_no_volumes(self):
        """Test getting disk attachment info when no volumes exist"""
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'

        self.mock_aws.get_instance_id.return_value = instance_id
        self.mock_aws.get_volumes_ids.return_value = []

        result = self.scenario.get_disk_attachment_info(
            instance_kill_count=1,
            node=node
        )

        self.assertIsNone(result)
        self.mock_aws.get_volume_attachment_details.assert_not_called()

    def test_get_disk_attachment_info_failure(self):
        """Test getting disk attachment info with failure"""
        node = 'ip-10-0-1-100.ec2.internal'

        self.mock_aws.get_instance_id.side_effect = Exception("AWS error")

        with self.assertRaises(RuntimeError):
            self.scenario.get_disk_attachment_info(
                instance_kill_count=1,
                node=node
            )

    def test_disk_detach_scenario_success(self):
        """Test disk detach scenario successfully"""
        node = 'ip-10-0-1-100.ec2.internal'
        instance_id = 'i-1234567890abcdef0'
        volume_ids = ['vol-12345678', 'vol-87654321']

        self.mock_aws.get_instance_id.return_value = instance_id
        self.mock_aws.get_volumes_ids.return_value = volume_ids
        self.mock_aws.detach_volumes.return_value = None

        self.scenario.disk_detach_scenario(
            instance_kill_count=1,
            node=node,
            timeout=600
        )

        self.mock_aws.get_instance_id.assert_called_once_with(node)
        self.mock_aws.get_volumes_ids.assert_called_once()
        self.mock_aws.detach_volumes.assert_called_once_with(volume_ids)

    def test_disk_detach_scenario_failure(self):
        """Test disk detach scenario with failure"""
        node = 'ip-10-0-1-100.ec2.internal'

        self.mock_aws.get_instance_id.side_effect = Exception("AWS error")

        with self.assertRaises(RuntimeError):
            self.scenario.disk_detach_scenario(
                instance_kill_count=1,
                node=node,
                timeout=600
            )

    def test_disk_attach_scenario_success(self):
        """Test disk attach scenario successfully"""
        attachment_details = [
            {
                'VolumeId': 'vol-12345678',
                'Attachments': [{
                    'InstanceId': 'i-1234567890abcdef0',
                    'Device': '/dev/sdf',
                    'VolumeId': 'vol-12345678'
                }]
            },
            {
                'VolumeId': 'vol-87654321',
                'Attachments': [{
                    'InstanceId': 'i-1234567890abcdef0',
                    'Device': '/dev/sdg',
                    'VolumeId': 'vol-87654321'
                }]
            }
        ]

        self.mock_aws.attach_volume.return_value = None

        self.scenario.disk_attach_scenario(
            instance_kill_count=1,
            attachment_details=attachment_details,
            timeout=600
        )

        self.assertEqual(self.mock_aws.attach_volume.call_count, 2)

    def test_disk_attach_scenario_multiple_kills(self):
        """Test disk attach scenario with multiple kill counts"""
        attachment_details = [
            {
                'VolumeId': 'vol-12345678',
                'Attachments': [{
                    'InstanceId': 'i-1234567890abcdef0',
                    'Device': '/dev/sdf',
                    'VolumeId': 'vol-12345678'
                }]
            }
        ]

        self.mock_aws.attach_volume.return_value = None

        self.scenario.disk_attach_scenario(
            instance_kill_count=3,
            attachment_details=attachment_details,
            timeout=600
        )

        # Should call attach_volume 3 times (once per kill count)
        self.assertEqual(self.mock_aws.attach_volume.call_count, 3)


if __name__ == "__main__":
    unittest.main()
