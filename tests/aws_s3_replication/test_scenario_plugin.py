"""Unit tests for AWS S3 Replication scenario plugin."""

import os
import tempfile
import pytest
import yaml
from unittest.mock import Mock, patch, MagicMock
from krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin import (
    AwsS3ReplicationScenarioPlugin
)


@pytest.fixture
def mock_telemetry():
    """Provides a mocked telemetry object."""
    return Mock()


@pytest.fixture
def mock_scenario_telemetry():
    """Provides a mocked scenario telemetry object."""
    return Mock()


@pytest.fixture
def krkn_config():
    """Provides a sample Krkn configuration."""
    return {
        'tunings': {
            'wait_duration': 10
        },
        'telemetry': {
            'events_backup': False
        }
    }


@pytest.fixture
def valid_scenario_config():
    """Provides a valid scenario configuration."""
    return {
        'aws_s3_replication_scenarios': {
            'bucket_name': 'test-bucket',
            'duration': 60,
            'region': 'us-east-1'
        }
    }


@pytest.fixture
def scenario_config_file(valid_scenario_config):
    """Creates a temporary scenario configuration file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(valid_scenario_config, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestAwsS3ReplicationScenarioPlugin:
    """Tests for AwsS3ReplicationScenarioPlugin class."""

    def test_plugin_initialization(self):
        """Test plugin initialization."""
        plugin = AwsS3ReplicationScenarioPlugin()
        assert plugin is not None

    def test_get_scenario_types(self):
        """Test get_scenario_types method."""
        plugin = AwsS3ReplicationScenarioPlugin()
        scenario_types = plugin.get_scenario_types()
        
        assert isinstance(scenario_types, list)
        assert len(scenario_types) == 1
        assert 'aws_s3_replication_scenarios' in scenario_types

    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.AWSS3Replication')
    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.cerberus')
    def test_run_success(
        self,
        mock_cerberus,
        mock_s3_class,
        scenario_config_file,
        krkn_config,
        mock_telemetry,
        mock_scenario_telemetry
    ):
        """Test successful scenario execution."""
        # Setup mocks
        mock_s3_instance = Mock()
        mock_s3_instance.get_replication_configuration.return_value = {
            'Role': 'arn:aws:iam::123456789012:role/test-role',
            'Rules': [{'ID': 'rule-1', 'Status': 'Enabled', 'Priority': 1}]
        }
        mock_s3_instance.pause_replication.return_value = None
        mock_s3_instance.restore_replication.return_value = None
        mock_s3_instance.verify_replication_status.return_value = True
        mock_s3_class.return_value = mock_s3_instance
        
        # Run scenario
        plugin = AwsS3ReplicationScenarioPlugin()
        result = plugin.run(
            run_uuid='test-uuid',
            scenario=scenario_config_file,
            krkn_config=krkn_config,
            lib_telemetry=mock_telemetry,
            scenario_telemetry=mock_scenario_telemetry
        )
        
        # Verify
        assert result == 0
        mock_s3_instance.get_replication_configuration.assert_called_once_with('test-bucket')
        mock_s3_instance.pause_replication.assert_called_once_with('test-bucket')
        mock_s3_instance.restore_replication.assert_called_once()
        mock_cerberus.publish_kraken_status.assert_called_once()

    def test_run_missing_bucket_name(
        self,
        krkn_config,
        mock_telemetry,
        mock_scenario_telemetry
    ):
        """Test scenario execution with missing bucket_name."""
        config = {
            'aws_s3_replication_scenarios': {
                'duration': 60
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name
        
        try:
            plugin = AwsS3ReplicationScenarioPlugin()
            result = plugin.run(
                run_uuid='test-uuid',
                scenario=temp_path,
                krkn_config=krkn_config,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )
            
            assert result == 1
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_run_invalid_duration(
        self,
        krkn_config,
        mock_telemetry,
        mock_scenario_telemetry
    ):
        """Test scenario execution with invalid duration."""
        config = {
            'aws_s3_replication_scenarios': {
                'bucket_name': 'test-bucket',
                'duration': -10
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name
        
        try:
            plugin = AwsS3ReplicationScenarioPlugin()
            result = plugin.run(
                run_uuid='test-uuid',
                scenario=temp_path,
                krkn_config=krkn_config,
                lib_telemetry=mock_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )
            
            assert result == 1
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_run_file_not_found(
        self,
        krkn_config,
        mock_telemetry,
        mock_scenario_telemetry
    ):
        """Test scenario execution with non-existent config file."""
        plugin = AwsS3ReplicationScenarioPlugin()
        result = plugin.run(
            run_uuid='test-uuid',
            scenario='/nonexistent/file.yaml',
            krkn_config=krkn_config,
            lib_telemetry=mock_telemetry,
            scenario_telemetry=mock_scenario_telemetry
        )
        
        assert result == 1

    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.AWSS3Replication')
    def test_run_pause_failure(
        self,
        mock_s3_class,
        scenario_config_file,
        krkn_config,
        mock_telemetry,
        mock_scenario_telemetry
    ):
        """Test scenario execution when pause fails."""
        mock_s3_instance = Mock()
        mock_s3_instance.get_replication_configuration.return_value = {
            'Role': 'arn:aws:iam::123456789012:role/test-role',
            'Rules': [{'ID': 'rule-1', 'Status': 'Enabled'}]
        }
        mock_s3_instance.pause_replication.side_effect = RuntimeError("Pause failed")
        mock_s3_class.return_value = mock_s3_instance
        
        plugin = AwsS3ReplicationScenarioPlugin()
        result = plugin.run(
            run_uuid='test-uuid',
            scenario=scenario_config_file,
            krkn_config=krkn_config,
            lib_telemetry=mock_telemetry,
            scenario_telemetry=mock_scenario_telemetry
        )
        
        assert result == 1

    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.AWSS3Replication')
    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.cerberus')
    def test_run_restore_failure(
        self,
        mock_cerberus,
        mock_s3_class,
        scenario_config_file,
        krkn_config,
        mock_telemetry,
        mock_scenario_telemetry
    ):
        """Test scenario execution when restore fails."""
        mock_s3_instance = Mock()
        mock_s3_instance.get_replication_configuration.return_value = {
            'Role': 'arn:aws:iam::123456789012:role/test-role',
            'Rules': [{'ID': 'rule-1', 'Status': 'Enabled'}]
        }
        mock_s3_instance.pause_replication.return_value = None
        mock_s3_instance.restore_replication.side_effect = RuntimeError("Restore failed")
        mock_s3_class.return_value = mock_s3_instance
        
        plugin = AwsS3ReplicationScenarioPlugin()
        result = plugin.run(
            run_uuid='test-uuid',
            scenario=scenario_config_file,
            krkn_config=krkn_config,
            lib_telemetry=mock_telemetry,
            scenario_telemetry=mock_scenario_telemetry
        )
        
        assert result == 1


class TestRollbackFunction:
    """Tests for rollback_replication static method."""

    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.AWSS3Replication')
    def test_rollback_success(self, mock_s3_class, mock_telemetry):
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
            mock_telemetry
        )
        
        # Verify
        mock_s3_instance.restore_replication.assert_called_once_with(
            'test-bucket',
            rollback_data['original_config']
        )

    @patch('krkn.scenario_plugins.aws_s3_replication.aws_s3_replication_scenario_plugin.AWSS3Replication')
    def test_rollback_failure(self, mock_s3_class, mock_telemetry):
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
            mock_telemetry
        )
        
        # Verify restore was attempted
        mock_s3_instance.restore_replication.assert_called_once()
