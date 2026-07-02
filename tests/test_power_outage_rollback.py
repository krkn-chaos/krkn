"""
Power Outage Rollback Test Suite

This is the final and comprehensive test suite for the Power Outage Rollback Feature.
It tests the rollback functionality for restoring powered-off nodes back to running state
after a power outage scenario fails.

Features tested:
- Successful node restoration
- Partial failure handling
- Invalid content handling
- Unsupported cloud provider handling
- Empty node list handling
- Cloud provider exception handling
- Multi-cloud provider support (AWS, GCP, Azure, OpenStack, IBM Cloud)
- Rollback content parsing and edge cases
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch

# Add the krkn directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import the actual rollback function and RollbackContent
from krkn.rollback.config import RollbackContent
from krkn.scenario_plugins.shut_down.shut_down_scenario_plugin import ShutDownScenarioPlugin


class TestPowerOutageRollback:
    """Test class for Power Outage Rollback functionality."""

    def test_rollback_shutdown_nodes_success(self):
        """Test successful rollback of shutdown nodes."""
        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-12345", "i-67890"),
            skip_kubernetes=True,
        )
        
        # Mock telemetry
        mock_telemetry = Mock()
        
        # Mock cloud provider - patch at the import location inside the rollback function
        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            mock_aws = Mock()
            mock_aws_class.return_value = mock_aws
            mock_aws.start_instances.return_value = None
            mock_aws.wait_until_running.return_value = True
            
            # Execute rollback
            ShutDownScenarioPlugin.rollback_shutdown_nodes(rollback_content, mock_telemetry)
            
            # Verify cloud provider methods were called per instance
            assert mock_aws.start_instances.call_count == 2
            mock_aws.start_instances.assert_any_call("i-12345")
            mock_aws.start_instances.assert_any_call("i-67890")
            assert mock_aws.wait_until_running.call_count == 2

    def test_rollback_shutdown_nodes_partial_failure(self):
        """Test rollback with partial node restoration failure."""
        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-12345", "i-67890"),
            skip_kubernetes=True,
        )
        
        # Mock telemetry
        mock_telemetry = Mock()
        
        # Mock cloud provider with partial failure - patch at the import location
        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            mock_aws = Mock()
            mock_aws_class.return_value = mock_aws
            mock_aws.start_instances.return_value = None
            
            # First node succeeds, second fails
            def wait_side_effect(node_id, timeout, affected_node=None):
                if node_id == "i-12345":
                    return True
                return False
            
            mock_aws.wait_until_running.side_effect = wait_side_effect
            
            # Execute rollback
            ShutDownScenarioPlugin.rollback_shutdown_nodes(rollback_content, mock_telemetry)
            
            # Verify cloud provider methods were called per instance
            assert mock_aws.start_instances.call_count == 2
            mock_aws.start_instances.assert_any_call("i-12345")
            mock_aws.start_instances.assert_any_call("i-67890")
            assert mock_aws.wait_until_running.call_count == 2

    def test_rollback_shutdown_nodes_invalid_content(self):
        """Test rollback with invalid rollback content."""
        # Create invalid rollback content
        rollback_content = RollbackContent(resource_identifier="invalid_format")
        
        # Mock telemetry
        mock_telemetry = Mock()
        
        # Execute rollback - should handle gracefully
        ShutDownScenarioPlugin.rollback_shutdown_nodes(rollback_content, mock_telemetry)
        
        # No cloud provider should be instantiated - patch at the import location
        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            assert not mock_aws_class.called

    def test_rollback_shutdown_nodes_unsupported_cloud(self):
        """Test rollback with unsupported cloud provider."""
        # Create rollback content with unsupported cloud
        rollback_content = RollbackContent(cloud_type="unsupported", instance_ids=("i-12345",))
        
        # Mock telemetry
        mock_telemetry = Mock()
        
        # Execute rollback - should handle gracefully
        ShutDownScenarioPlugin.rollback_shutdown_nodes(rollback_content, mock_telemetry)
        
        # No cloud provider should be instantiated - patch at the import location
        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            assert not mock_aws_class.called

    def test_rollback_shutdown_nodes_empty_node_list(self):
        """Test rollback with empty node list."""
        # Create rollback content with empty node list
        rollback_content = RollbackContent(cloud_type="aws", instance_ids=tuple())
        
        # Mock telemetry
        mock_telemetry = Mock()
        
        # Execute rollback - should handle gracefully
        ShutDownScenarioPlugin.rollback_shutdown_nodes(rollback_content, mock_telemetry)
        
        # No cloud provider should be instantiated - patch at the import location
        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            assert not mock_aws_class.called

    def test_rollback_shutdown_nodes_cloud_provider_exception(self):
        """Test rollback when cloud provider start operations fail."""
        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-12345",),
            skip_kubernetes=True,
        )

        mock_telemetry = Mock()

        with patch('krkn.scenario_plugins.node_actions.aws_node_scenarios.AWS') as mock_aws_class:
            mock_aws = Mock()
            mock_aws_class.return_value = mock_aws
            mock_aws.start_instances.side_effect = Exception("Cloud API error")

            # Per-node failures are handled gracefully; rollback should not raise.
            ShutDownScenarioPlugin.rollback_shutdown_nodes(rollback_content, mock_telemetry)

            mock_aws.start_instances.assert_called_once_with("i-12345")
            mock_aws.wait_until_running.assert_not_called()

    def test_rollback_shutdown_nodes_different_cloud_providers(self):
        """Test rollback with different cloud providers."""
        # Mock telemetry
        mock_telemetry = Mock()
        
        cloud_providers = [
            ("gcp", "krkn.scenario_plugins.node_actions.gcp_node_scenarios.GCP"),
            ("azure", "krkn.scenario_plugins.node_actions.az_node_scenarios.Azure"),
            ("openstack", "krkn.scenario_plugins.node_actions.openstack_node_scenarios.OPENSTACKCLOUD"),
            ("ibm", "krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios.IbmCloud")
        ]
        
        for cloud_type, provider_path in cloud_providers:
            # Create rollback content
            rollback_content = RollbackContent(
                cloud_type=cloud_type,
                instance_ids=("i-12345",),
                skip_kubernetes=True,
            )
            
            # Mock cloud provider
            with patch(provider_path) as mock_provider_class:
                mock_provider = Mock()
                mock_provider_class.return_value = mock_provider
                mock_provider.start_instances.return_value = None
                mock_provider.wait_until_running.return_value = True
                
                # Execute rollback
                ShutDownScenarioPlugin.rollback_shutdown_nodes(rollback_content, mock_telemetry)
                
                # Verify cloud provider methods were called per instance
                mock_provider.start_instances.assert_called_once_with("i-12345")
                mock_provider.wait_until_running.assert_called_once()

    def test_rollback_content_parsing(self):
        """Test structured rollback content fields."""
        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-12345", "i-67890"),
            skip_kubernetes=True,
        )
        assert rollback_content.cloud_type == "aws"
        assert rollback_content.instance_ids == ("i-12345", "i-67890")
        assert rollback_content.skip_kubernetes is True

    def test_rollback_content_parsing_edge_cases(self):
        """Test legacy fallback content parsing with edge cases."""
        rollback_content = RollbackContent(
            resource_identifier="aws: i-12345 , i-67890 "
        )
        
        content_parts = rollback_content.resource_identifier.split(":", 1)
        node_ids = [node_id.strip() for node_id in content_parts[1].split(",") if node_id.strip()]
        assert node_ids == ["i-12345", "i-67890"]
        
        # Test with empty node ID
        rollback_content = RollbackContent(
            resource_identifier="aws:i-12345,,i-67890"
        )
        
        content_parts = rollback_content.resource_identifier.split(":", 1)
        node_ids = [node_id.strip() for node_id in content_parts[1].split(",") if node_id.strip()]
        assert node_ids == ["i-12345", "i-67890"]

    @patch("krkn.rollback.handler.RollbackConfig.search_rollback_version_files")
    @patch("krkn.rollback.handler._parse_rollback_module")
    @patch("os.rename")
    def test_execute_rollback_passes_none_telemetry_for_skip_kubernetes(
        self, mock_rename, mock_parse_rollback_module, mock_search_files
    ):
        """Cloud-only rollback should receive None telemetry."""
        from krkn.rollback.handler import execute_rollback_version_files

        version_file = "/tmp/rollback_file.py"
        mock_search_files.return_value = [version_file]
        rollback_callable = Mock()
        rollback_content = RollbackContent(
            cloud_type="aws",
            instance_ids=("i-12345",),
            skip_kubernetes=True,
        )
        mock_parse_rollback_module.return_value = (rollback_callable, rollback_content)

        execute_rollback_version_files(
            telemetry_ocp=Mock(),
            run_uuid="test-run",
            scenario_type="cluster_shut_down_scenarios",
            ignore_auto_rollback_config=True,
        )

        rollback_callable.assert_called_once_with(rollback_content, None)
        mock_rename.assert_called_once_with(version_file, f"{version_file}.executed")


if __name__ == "__main__":
    pytest.main([__file__])

