"""Tests for NodeActionsScenarioPlugin node outage rollback functionality."""
import unittest
import pytest
from unittest.mock import Mock, patch


from krkn.scenario_plugins.node_actions.node_actions_scenario_plugin import NodeActionsScenarioPlugin
from krkn.rollback.config import RollbackContent


class TestNodeOutageRollback(unittest.TestCase):

    @patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS')
    def test_rollback_node_outage_aws_success(self, mock_aws_class):
        mock_aws = Mock()
        mock_aws_class.return_value = mock_aws
        mock_aws.start_instances.return_value = None
        mock_aws.wait_until_running.return_value = True

        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-12345",),
            skip_kubernetes=True,
        )
        mock_telemetry = Mock()

        NodeActionsScenarioPlugin.rollback_node_outage(rollback_content, mock_telemetry)

        mock_aws.start_instances.assert_called_once_with("i-12345")
        mock_aws.wait_until_running.assert_called_once_with("i-12345", 300, None)

    @patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS')
    def test_rollback_node_outage_multiple_nodes(self, mock_aws_class):
        mock_aws = Mock()
        mock_aws_class.return_value = mock_aws
        mock_aws.start_instances.return_value = None
        mock_aws.wait_until_running.return_value = True

        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-12345", "i-67890"),
            skip_kubernetes=True,
        )
        mock_telemetry = Mock()

        NodeActionsScenarioPlugin.rollback_node_outage(rollback_content, mock_telemetry)

        self.assertEqual(mock_aws.start_instances.call_count, 2)
        mock_aws.start_instances.assert_any_call("i-12345")
        mock_aws.start_instances.assert_any_call("i-67890")
        self.assertEqual(mock_aws.wait_until_running.call_count, 2)

    @patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS')
    def test_rollback_node_outage_partial_failure(self, mock_aws_class):
        mock_aws = Mock()
        mock_aws_class.return_value = mock_aws
        
        def start_side_effect(instance_id):
            if instance_id == "i-fail":
                raise Exception("Failed to start")
            return None
        
        mock_aws.start_instances.side_effect = start_side_effect
        mock_aws.wait_until_running.return_value = True

        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-12345", "i-fail"),
            skip_kubernetes=True,
        )
        mock_telemetry = Mock()

        NodeActionsScenarioPlugin.rollback_node_outage(rollback_content, mock_telemetry)

        self.assertEqual(mock_aws.start_instances.call_count, 2)
        mock_aws.wait_until_running.assert_called_once_with("i-12345", 300, None)

    def test_rollback_node_outage_empty_node_list(self):
        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=tuple(),
            skip_kubernetes=True,
        )
        mock_telemetry = Mock()

        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            NodeActionsScenarioPlugin.rollback_node_outage(rollback_content, mock_telemetry)
            mock_aws_class.assert_not_called()

    def test_rollback_node_outage_unsupported_cloud(self):
        rollback_content = RollbackContent(
            cloud_type="unsupported",
            instance_ids=("i-12345",),
            skip_kubernetes=True,
        )
        mock_telemetry = Mock()

        # Should handle gracefully without raising
        NodeActionsScenarioPlugin.rollback_node_outage(rollback_content, mock_telemetry)

    @patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS')
    def test_rollback_node_outage_cloud_exception(self, mock_aws_class):
        mock_aws = Mock()
        mock_aws_class.return_value = mock_aws
        mock_aws.start_instances.side_effect = Exception("Cloud API Error")

        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-12345",),
            skip_kubernetes=True,
        )
        mock_telemetry = Mock()

        # Should not raise exception
        NodeActionsScenarioPlugin.rollback_node_outage(rollback_content, mock_telemetry)

        mock_aws.start_instances.assert_called_once_with("i-12345")
        mock_aws.wait_until_running.assert_not_called()

    @patch('krkn.scenario_plugins.node_actions.gcp_node_scenarios.GCP')
    def test_rollback_node_outage_gcp(self, mock_gcp_class):
        mock_gcp = Mock()
        mock_gcp_class.return_value = mock_gcp
        mock_gcp.start_instances.return_value = None
        mock_gcp.wait_until_running.return_value = True

        rollback_content = RollbackContent(
            cloud_type="gcp",
            instance_ids=("instance-1",),
            skip_kubernetes=True,
        )
        mock_telemetry = Mock()

        NodeActionsScenarioPlugin.rollback_node_outage(rollback_content, mock_telemetry)

        mock_gcp.start_instances.assert_called_once_with("instance-1")

    @patch('krkn.scenario_plugins.node_actions.az_node_scenarios.Azure')
    def test_rollback_node_outage_azure(self, mock_az_class):
        mock_az = Mock()
        mock_az_class.return_value = mock_az
        mock_az.start_instances.return_value = None
        mock_az.wait_until_running.return_value = True

        rollback_content = RollbackContent(
            cloud_type="azure",
            instance_ids=(("vm-1", "resource-group-1"),),
            skip_kubernetes=True,
        )
        mock_telemetry = Mock()

        NodeActionsScenarioPlugin.rollback_node_outage(rollback_content, mock_telemetry)

        mock_az.start_instances.assert_called_once_with("resource-group-1", "vm-1")
        mock_az.wait_until_running.assert_called_once_with("resource-group-1", "vm-1", 300, None)

    @patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD')
    def test_rollback_node_outage_openstack(self, mock_os_class):
        mock_os = Mock()
        mock_os_class.return_value = mock_os
        mock_os.start_instances.return_value = None
        mock_os.wait_until_running.return_value = True

        rollback_content = RollbackContent(
            cloud_type="openstack",
            instance_ids=("os-node-1",),
            skip_kubernetes=True,
        )
        mock_telemetry = Mock()

        NodeActionsScenarioPlugin.rollback_node_outage(rollback_content, mock_telemetry)

        mock_os.start_instances.assert_called_once_with("os-node-1")
        mock_os.wait_until_running.assert_called_once_with("os-node-1", 300, None)

    @patch('krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios.IbmCloud')
    def test_rollback_node_outage_ibmcloud(self, mock_ibm_class):
        mock_ibm = Mock()
        mock_ibm_class.return_value = mock_ibm
        mock_ibm.start_instances.return_value = None
        mock_ibm.wait_until_running.return_value = True

        rollback_content = RollbackContent(
            cloud_type="ibmcloud",
            instance_ids=("ibm-node-1",),
            skip_kubernetes=True,
        )
        mock_telemetry = Mock()

        NodeActionsScenarioPlugin.rollback_node_outage(rollback_content, mock_telemetry)

        mock_ibm.start_instances.assert_called_once_with("ibm-node-1")
        mock_ibm.wait_until_running.assert_called_once_with("ibm-node-1", 300, None)

    def test_rollback_content_structured_fields(self):
        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-12345",),
            skip_kubernetes=True,
        )
        self.assertEqual(rollback_content.cloud_type, "aws")
        self.assertEqual(rollback_content.instance_ids, ("i-12345",))
        self.assertTrue(rollback_content.skip_kubernetes)

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin._get_node_cloud_object')
    @patch('krkn.scenario_plugins.node_actions.common_node_functions.get_node_by_name')
    def test_rollback_registration_in_inject(self, mock_get_node, mock_get_cloud):
        plugin = NodeActionsScenarioPlugin()
        plugin.rollback_handler = Mock()
        
        mock_get_node.return_value = ["node1"]
        mock_cloud_obj = Mock()
        mock_cloud_obj.get_instance_id.return_value = "i-123"
        mock_get_cloud.return_value = mock_cloud_obj
        
        mock_kubecli = Mock()
        mock_telemetry = Mock()
        mock_scenario_obj = Mock()
        mock_scenario_obj.affected_nodes_status = Mock()
        mock_scenario_obj.affected_nodes_status.affected_nodes = []

        scenario_yaml = {
            "node_name": "node1",
            "cloud_type": "aws",
        }

        plugin.inject_node_scenario(
            "node_stop_scenario", 
            scenario_yaml, 
            mock_scenario_obj, 
            mock_kubecli, 
            mock_telemetry
        )

        plugin.rollback_handler.set_rollback_callable.assert_called_once()
        args, _ = plugin.rollback_handler.set_rollback_callable.call_args
        self.assertEqual(args[0], NodeActionsScenarioPlugin.rollback_node_outage)
        self.assertEqual(args[1].cloud_type, "aws")
        self.assertEqual(args[1].instance_ids, ("i-123",))
        self.assertTrue(args[1].skip_kubernetes)

    @patch('krkn.scenario_plugins.node_actions.common_node_functions.get_node_by_name')
    def test_rollback_not_registered_for_generic(self, mock_get_node):
        plugin = NodeActionsScenarioPlugin()
        plugin.rollback_handler = Mock()
        
        mock_get_node.return_value = ["node1"]
        mock_kubecli = Mock()
        mock_telemetry = Mock()
        mock_scenario_obj = Mock()
        mock_scenario_obj.affected_nodes_status = Mock()
        mock_scenario_obj.affected_nodes_status.affected_nodes = []

        scenario_yaml = {
            "node_name": "node1",
            "cloud_type": "generic",
        }

        plugin.inject_node_scenario(
            "node_stop_scenario", 
            scenario_yaml, 
            mock_scenario_obj, 
            mock_kubecli, 
            mock_telemetry
        )

        plugin.rollback_handler.set_rollback_callable.assert_not_called()

    @patch("krkn.rollback.handler.RollbackConfig.search_rollback_version_files")
    @patch("krkn.rollback.handler._parse_rollback_module")
    @patch("os.rename")
    def test_execute_rollback_passes_none_telemetry(
        self, mock_rename, mock_parse, mock_search
    ):
        from krkn.rollback.handler import execute_rollback_version_files
        
        mock_search.return_value = ["/tmp/test.py"]
        
        mock_callable = Mock()
        mock_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-123",),
            skip_kubernetes=True
        )
        mock_parse.return_value = (mock_callable, mock_content)
        
        execute_rollback_version_files(
            telemetry_ocp=Mock(),
            run_uuid="uuid",
            scenario_type="node_scenarios",
            ignore_auto_rollback_config=True
        )
        
        mock_callable.assert_called_once_with(mock_content, None)

if __name__ == "__main__":
    pytest.main([__file__])
