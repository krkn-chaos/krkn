"""Unit tests for AWS S3 Replication scenario plugin."""

import os
import tempfile
import unittest
import yaml
from unittest.mock import Mock, patch
from krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin import (
    AwsS3ReplicationScenarioPlugin
)


class TestAwsS3ReplicationScenarioPlugin(unittest.TestCase):
    """Tests for AwsS3ReplicationScenarioPlugin class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_telemetry = Mock()
        self.mock_scenario_telemetry = Mock()
        
        self.valid_scenario_config = {
            'aws_s3_replication_scenarios': {
                'bucket_name': 'test-bucket',
                'duration': 1,  # Short duration for tests
                'region': 'us-east-1'
            }
        }

    def _create_scenario_config_file(self, config):
        """Helper method to create a temporary scenario configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            return f.name

    def test_plugin_initialization(self):
        """Test plugin initialization."""
        plugin = AwsS3ReplicationScenarioPlugin("aws_s3_replication_scenarios")
        self.assertIsNotNone(plugin)

    def test_get_scenario_types(self):
        """Test get_scenario_types method."""
        plugin = AwsS3ReplicationScenarioPlugin("aws_s3_replication_scenarios")
        scenario_types = plugin.get_scenario_types()
        
        self.assertIsInstance(scenario_types, list)
        self.assertEqual(len(scenario_types), 1)
        self.assertIn('aws_s3_replication_scenarios', scenario_types)

    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.AWSS3Replication')
    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.time.sleep')
    def test_run_success(self, mock_sleep, mock_s3_class):
        """Test successful scenario execution."""
        scenario_config_file = self._create_scenario_config_file(self.valid_scenario_config)
        
        try:
            # Setup mocks
            original_config = {
                'Role': 'arn:aws:iam::123456789012:role/test-role',
                'Rules': [{'ID': 'rule-1', 'Status': 'Enabled', 'Priority': 1}]
            }
            mock_s3_instance = Mock()
            mock_s3_instance.pause_replication.return_value = original_config
            mock_s3_instance.restore_replication.return_value = None
            mock_s3_instance.verify_replication_status.return_value = True
            mock_s3_instance.get_replication_configuration.return_value = original_config
            mock_s3_class.return_value = mock_s3_instance
            
            # Run scenario
            plugin = AwsS3ReplicationScenarioPlugin("aws_s3_replication_scenarios")
            result = plugin.run(
                run_uuid='test-uuid',
                scenario=scenario_config_file,
                lib_telemetry=self.mock_telemetry,
                scenario_telemetry=self.mock_scenario_telemetry
            )
            
            # Verify
            self.assertEqual(result, 0)
            mock_s3_instance.pause_replication.assert_called_once_with('test-bucket')
            mock_s3_instance.restore_replication.assert_called_once_with('test-bucket', original_config)
        finally:
            if os.path.exists(scenario_config_file):
                os.unlink(scenario_config_file)

    def test_run_missing_bucket_name(self):
        """Test scenario execution with missing bucket_name."""
        config = {
            'aws_s3_replication_scenarios': {
                'duration': 60
            }
        }
        
        scenario_config_file = self._create_scenario_config_file(config)
        
        try:
            plugin = AwsS3ReplicationScenarioPlugin("aws_s3_replication_scenarios")
            result = plugin.run(
                run_uuid='test-uuid',
                scenario=scenario_config_file,
                lib_telemetry=self.mock_telemetry,
                scenario_telemetry=self.mock_scenario_telemetry
            )
            
            self.assertEqual(result, 1)
        finally:
            if os.path.exists(scenario_config_file):
                os.unlink(scenario_config_file)

    def test_run_invalid_duration(self):
        """Test scenario execution with invalid duration."""
        config = {
            'aws_s3_replication_scenarios': {
                'bucket_name': 'test-bucket',
                'duration': -10
            }
        }
        
        scenario_config_file = self._create_scenario_config_file(config)
        
        try:
            plugin = AwsS3ReplicationScenarioPlugin("aws_s3_replication_scenarios")
            result = plugin.run(
                run_uuid='test-uuid',
                scenario=scenario_config_file,
                lib_telemetry=self.mock_telemetry,
                scenario_telemetry=self.mock_scenario_telemetry
            )
            
            self.assertEqual(result, 1)
        finally:
            if os.path.exists(scenario_config_file):
                os.unlink(scenario_config_file)

    def test_run_file_not_found(self):
        """Test scenario execution with non-existent config file."""
        plugin = AwsS3ReplicationScenarioPlugin("aws_s3_replication_scenarios")
        result = plugin.run(
            run_uuid='test-uuid',
            scenario='/nonexistent/file.yaml',
            lib_telemetry=self.mock_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry
        )
        
        self.assertEqual(result, 1)

    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.AWSS3Replication')
    def test_run_pause_failure(self, mock_s3_class):
        """Test scenario execution when pause fails."""
        scenario_config_file = self._create_scenario_config_file(self.valid_scenario_config)
        
        try:
            mock_s3_instance = Mock()
            mock_s3_instance.pause_replication.side_effect = RuntimeError("Pause failed")
            mock_s3_class.return_value = mock_s3_instance
            
            plugin = AwsS3ReplicationScenarioPlugin("aws_s3_replication_scenarios")
            result = plugin.run(
                run_uuid='test-uuid',
                scenario=scenario_config_file,
                lib_telemetry=self.mock_telemetry,
                scenario_telemetry=self.mock_scenario_telemetry
            )
            
            self.assertEqual(result, 1)
        finally:
            if os.path.exists(scenario_config_file):
                os.unlink(scenario_config_file)

    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.AWSS3Replication')
    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.time.sleep')
    def test_run_restore_failure(self, mock_sleep, mock_s3_class):
        """Test scenario execution when restore fails."""
        scenario_config_file = self._create_scenario_config_file(self.valid_scenario_config)
        
        try:
            original_config = {
                'Role': 'arn:aws:iam::123456789012:role/test-role',
                'Rules': [{'ID': 'rule-1', 'Status': 'Enabled'}]
            }
            mock_s3_instance = Mock()
            mock_s3_instance.pause_replication.return_value = original_config
            mock_s3_instance.restore_replication.side_effect = RuntimeError("Restore failed")
            mock_s3_class.return_value = mock_s3_instance
            
            plugin = AwsS3ReplicationScenarioPlugin("aws_s3_replication_scenarios")
            result = plugin.run(
                run_uuid='test-uuid',
                scenario=scenario_config_file,
                lib_telemetry=self.mock_telemetry,
                scenario_telemetry=self.mock_scenario_telemetry
            )
            
            self.assertEqual(result, 1)
        finally:
            if os.path.exists(scenario_config_file):
                os.unlink(scenario_config_file)


class TestRollbackFunction(unittest.TestCase):
    """Tests for rollback_replication static method."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_telemetry = Mock()

    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.AWSS3Replication')
    def test_rollback_success(self, mock_s3_class):
        """Test successful rollback execution."""
        import base64
        import json
        from krkn.rollback.config import RollbackContent
        
        # Prepare rollback data
        rollback_data = {
            'bucket_name': 'test-bucket',
            'region': 'us-east-1',
            'original_config': {
                'Role': 'arn:aws:iam::123456789012:role/test-role',
                'Rules': [{'ID': 'rule-1', 'Status': 'Enabled'}]
            }
        }
        json_str = json.dumps(rollback_data)
        encoded_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        
        rollback_content = RollbackContent(
            namespace='aws-s3',
            resource_identifier=encoded_data
        )
        
        # Setup mock
        mock_s3_instance = Mock()
        mock_s3_class.return_value = mock_s3_instance
        
        # Execute rollback
        AwsS3ReplicationScenarioPlugin.rollback_replication(
            rollback_content,
            self.mock_telemetry
        )
        
        # Verify
        mock_s3_instance.restore_replication.assert_called_once_with(
            'test-bucket',
            rollback_data['original_config']
        )

    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.AWSS3Replication')
    def test_rollback_failure(self, mock_s3_class):
        """Test rollback execution when restore fails."""
        import base64
        import json
        from krkn.rollback.config import RollbackContent
        
        rollback_data = {
            'bucket_name': 'test-bucket',
            'region': 'us-east-1',
            'original_config': {
                'Role': 'arn:aws:iam::123456789012:role/test-role',
                'Rules': [{'ID': 'rule-1', 'Status': 'Enabled'}]
            }
        }
        json_str = json.dumps(rollback_data)
        encoded_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        
        rollback_content = RollbackContent(
            namespace='aws-s3',
            resource_identifier=encoded_data
        )
        
        # Setup mock to raise exception
        mock_s3_instance = Mock()
        mock_s3_instance.restore_replication.side_effect = RuntimeError("Restore failed")
        mock_s3_class.return_value = mock_s3_instance
        
        # Execute rollback (should not raise exception, just log error)
        AwsS3ReplicationScenarioPlugin.rollback_replication(
            rollback_content,
            self.mock_telemetry
        )
        
        # Verify restore was attempted
        mock_s3_instance.restore_replication.assert_called_once()
