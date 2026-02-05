"""Unit tests for AWS S3 Replication scenarios module."""

import pytest
from krkn.scenario_plugins.aws_s3_replication.aws_s3_scenarios import AWSS3Replication


class TestAWSS3ReplicationInit:
    """Tests for AWSS3Replication initialization."""

    def test_init_with_client(self, s3_client):
        """Test initialization with provided S3 client."""
        handler = AWSS3Replication(s3_client=s3_client)
        assert handler.s3_client is not None
        assert handler.s3_client == s3_client

    def test_init_with_region(self):
        """Test initialization with region parameter."""
        handler = AWSS3Replication(region='us-west-2')
        assert handler.s3_client is not None


class TestGetReplicationConfiguration:
    """Tests for get_replication_configuration method."""

    def test_get_replication_config_success(self, s3_bucket_with_replication):
        """Test successfully retrieving replication configuration."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        config = handler.get_replication_configuration(source_bucket)
        
        assert config is not None
        assert 'Role' in config
        assert 'Rules' in config
        assert len(config['Rules']) > 0
        assert config['Rules'][0]['Status'] == 'Enabled'

    def test_get_replication_config_no_replication(self, s3_bucket_without_replication):
        """Test error handling when bucket has no replication configured."""
        s3_client, bucket_name = s3_bucket_without_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        with pytest.raises(RuntimeError, match="Failed to retrieve replication configuration"):
            handler.get_replication_configuration(bucket_name)

    def test_get_replication_config_nonexistent_bucket(self, s3_client):
        """Test error handling when bucket does not exist."""
        handler = AWSS3Replication(s3_client=s3_client)
        
        with pytest.raises(RuntimeError, match="Failed to retrieve replication configuration"):
            handler.get_replication_configuration('nonexistent-bucket')


class TestPauseReplication:
    """Tests for pause_replication method."""

    def test_pause_replication_success(self, s3_bucket_with_replication):
        """Test successfully pausing replication."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        # Pause replication
        original_config = handler.pause_replication(source_bucket)
        
        # Verify original config was returned
        assert original_config is not None
        assert original_config['Rules'][0]['Status'] == 'Enabled'
        
        # Verify replication is now paused
        current_config = handler.get_replication_configuration(source_bucket)
        assert current_config['Rules'][0]['Status'] == 'Disabled'

    def test_pause_replication_multiple_rules(self, s3_client, multi_rule_replication_config):
        """Test pausing replication with multiple rules."""
        bucket_name = 'test-multi-rule-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        s3_client.put_bucket_replication(
            Bucket=bucket_name,
            ReplicationConfiguration=multi_rule_replication_config
        )
        
        handler = AWSS3Replication(s3_client=s3_client)
        original_config = handler.pause_replication(bucket_name)
        
        # Verify all enabled rules are now disabled
        current_config = handler.get_replication_configuration(bucket_name)
        for rule in current_config['Rules']:
            assert rule['Status'] == 'Disabled'
        
        # Verify original config had enabled rules
        enabled_count = sum(1 for rule in original_config['Rules'] if rule['Status'] == 'Enabled')
        assert enabled_count == 2  # rule-1 and rule-2 were enabled

    def test_pause_replication_already_paused(self, s3_bucket_with_replication):
        """Test pausing replication when already paused."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        # Pause once
        handler.pause_replication(source_bucket)
        
        # Pause again (should not fail)
        original_config = handler.pause_replication(source_bucket)
        assert original_config is not None

    def test_pause_replication_no_replication(self, s3_bucket_without_replication):
        """Test error handling when pausing bucket without replication."""
        s3_client, bucket_name = s3_bucket_without_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        with pytest.raises(RuntimeError):
            handler.pause_replication(bucket_name)


class TestRestoreReplication:
    """Tests for restore_replication method."""

    def test_restore_replication_success(self, s3_bucket_with_replication):
        """Test successfully restoring replication."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        # Pause replication
        original_config = handler.pause_replication(source_bucket)
        
        # Verify it's paused
        config = handler.get_replication_configuration(source_bucket)
        assert config['Rules'][0]['Status'] == 'Disabled'
        
        # Restore replication
        handler.restore_replication(source_bucket, original_config)
        
        # Verify it's restored
        config = handler.get_replication_configuration(source_bucket)
        assert config['Rules'][0]['Status'] == 'Enabled'

    def test_restore_replication_multiple_rules(self, s3_client, multi_rule_replication_config):
        """Test restoring replication with multiple rules."""
        bucket_name = 'test-multi-rule-restore'
        s3_client.create_bucket(Bucket=bucket_name)
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        s3_client.put_bucket_replication(
            Bucket=bucket_name,
            ReplicationConfiguration=multi_rule_replication_config
        )
        
        handler = AWSS3Replication(s3_client=s3_client)
        
        # Pause and restore
        original_config = handler.pause_replication(bucket_name)
        handler.restore_replication(bucket_name, original_config)
        
        # Verify restoration
        config = handler.get_replication_configuration(bucket_name)
        enabled_count = sum(1 for rule in config['Rules'] if rule['Status'] == 'Enabled')
        disabled_count = sum(1 for rule in config['Rules'] if rule['Status'] == 'Disabled')
        
        assert enabled_count == 2  # rule-1 and rule-2
        assert disabled_count == 1  # rule-3 was originally disabled

    def test_restore_replication_empty_config(self, s3_bucket_with_replication):
        """Test error handling when restoring with empty config."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        with pytest.raises(RuntimeError, match="restoring replication"):
            handler.restore_replication(source_bucket, None)

    def test_restore_replication_invalid_config(self, s3_bucket_with_replication):
        """Test error handling when restoring with invalid config."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        with pytest.raises(RuntimeError, match="restoring replication"):
            handler.restore_replication(source_bucket, {})


class TestVerifyReplicationStatus:
    """Tests for verify_replication_status method."""

    def test_verify_status_enabled(self, s3_bucket_with_replication):
        """Test verifying enabled replication status."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        result = handler.verify_replication_status(source_bucket, expected_status='Enabled')
        assert result is True

    def test_verify_status_disabled(self, s3_bucket_with_replication):
        """Test verifying disabled replication status."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        # Pause replication
        handler.pause_replication(source_bucket)
        
        # Verify disabled status
        result = handler.verify_replication_status(source_bucket, expected_status='Disabled')
        assert result is True

    def test_verify_status_mismatch(self, s3_bucket_with_replication):
        """Test verification when status doesn't match expected."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        # Replication is enabled, but we expect disabled
        result = handler.verify_replication_status(source_bucket, expected_status='Disabled')
        assert result is False

    def test_verify_status_no_replication(self, s3_bucket_without_replication):
        """Test verification when bucket has no replication."""
        s3_client, bucket_name = s3_bucket_without_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        result = handler.verify_replication_status(bucket_name, expected_status='Enabled')
        assert result is False


class TestEndToEndScenario:
    """End-to-end tests for complete chaos scenario workflow."""

    def test_complete_pause_restore_cycle(self, s3_bucket_with_replication):
        """Test complete pause and restore cycle."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        # Get initial config
        initial_config = handler.get_replication_configuration(source_bucket)
        assert initial_config['Rules'][0]['Status'] == 'Enabled'
        
        # Pause replication
        original_config = handler.pause_replication(source_bucket)
        paused_config = handler.get_replication_configuration(source_bucket)
        assert paused_config['Rules'][0]['Status'] == 'Disabled'
        
        # Restore replication
        handler.restore_replication(source_bucket, original_config)
        restored_config = handler.get_replication_configuration(source_bucket)
        assert restored_config['Rules'][0]['Status'] == 'Enabled'
        
        # Verify final state matches initial state
        assert restored_config['Rules'][0]['Status'] == initial_config['Rules'][0]['Status']

    def test_multiple_pause_restore_cycles(self, s3_bucket_with_replication):
        """Test multiple pause and restore cycles."""
        s3_client, source_bucket, _ = s3_bucket_with_replication
        handler = AWSS3Replication(s3_client=s3_client)
        
        for i in range(3):
            # Pause
            original_config = handler.pause_replication(source_bucket)
            assert handler.verify_replication_status(source_bucket, 'Disabled')
            
            # Restore
            handler.restore_replication(source_bucket, original_config)
            assert handler.verify_replication_status(source_bucket, 'Enabled')
