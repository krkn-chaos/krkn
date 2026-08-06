"""Unit tests for AWS S3 Replication scenarios module."""

import unittest
import boto3
from moto import mock_aws
from krkn.scenario_plugins.aws_s3_replication.aws_s3_scenarios import AWSS3Replication


class TestAWSS3ReplicationInit(unittest.TestCase):
    """Tests for AWSS3Replication initialization."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock = mock_aws()
        self.mock.start()
        self.s3_client = boto3.client('s3', region_name='us-east-1')

    def tearDown(self):
        """Clean up test fixtures."""
        self.mock.stop()

    def test_init_with_client(self):
        """Test initialization with provided S3 client."""
        handler = AWSS3Replication(s3_client=self.s3_client)
        self.assertIsNotNone(handler.s3_client)
        self.assertEqual(handler.s3_client, self.s3_client)

    def test_init_with_region(self):
        """Test initialization with region parameter."""
        handler = AWSS3Replication(region='us-west-2')
        self.assertIsNotNone(handler.s3_client)


class TestGetReplicationConfiguration(unittest.TestCase):
    """Tests for get_replication_configuration method."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock = mock_aws()
        self.mock.start()
        self.s3_client = boto3.client('s3', region_name='us-east-1')
        
        # Sample replication config
        self.sample_replication_config = {
            'Role': 'arn:aws:iam::123456789012:role/s3-replication-role',
            'Rules': [
                {
                    'ID': 'rule-1',
                    'Status': 'Enabled',
                    'Priority': 1,
                    'Filter': {'Prefix': ''},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket',
                        'StorageClass': 'STANDARD'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                }
            ]
        }

    def tearDown(self):
        """Clean up test fixtures."""
        self.mock.stop()

    def _create_bucket_with_replication(self):
        """Helper method to create buckets with replication."""
        source_bucket = 'test-source-bucket'
        dest_bucket = 'test-destination-bucket'
        
        self.s3_client.create_bucket(Bucket=source_bucket)
        self.s3_client.create_bucket(Bucket=dest_bucket)
        
        self.s3_client.put_bucket_versioning(
            Bucket=source_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        self.s3_client.put_bucket_versioning(
            Bucket=dest_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        self.s3_client.put_bucket_replication(
            Bucket=source_bucket,
            ReplicationConfiguration=self.sample_replication_config
        )
        
        return source_bucket, dest_bucket

    def _create_bucket_without_replication(self):
        """Helper method to create bucket without replication."""
        bucket_name = 'test-bucket-no-replication'
        
        self.s3_client.create_bucket(Bucket=bucket_name)
        self.s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        return bucket_name

    def test_get_replication_config_success(self):
        """Test successfully retrieving replication configuration."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        config = handler.get_replication_configuration(source_bucket)
        
        self.assertIsNotNone(config)
        self.assertIn('Role', config)
        self.assertIn('Rules', config)
        self.assertGreater(len(config['Rules']), 0)
        self.assertEqual(config['Rules'][0]['Status'], 'Enabled')

    def test_get_replication_config_no_replication(self):
        """Test error handling when bucket has no replication configured."""
        bucket_name = self._create_bucket_without_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        with self.assertRaisesRegex(RuntimeError, "Failed to retrieve replication configuration"):
            handler.get_replication_configuration(bucket_name)

    def test_get_replication_config_nonexistent_bucket(self):
        """Test error handling when bucket does not exist."""
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        with self.assertRaisesRegex(RuntimeError, "Failed to retrieve replication configuration"):
            handler.get_replication_configuration('nonexistent-bucket')


class TestPauseReplication(unittest.TestCase):
    """Tests for pause_replication method."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock = mock_aws()
        self.mock.start()
        self.s3_client = boto3.client('s3', region_name='us-east-1')
        
        self.sample_replication_config = {
            'Role': 'arn:aws:iam::123456789012:role/s3-replication-role',
            'Rules': [
                {
                    'ID': 'rule-1',
                    'Status': 'Enabled',
                    'Priority': 1,
                    'Filter': {'Prefix': ''},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket',
                        'StorageClass': 'STANDARD'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                }
            ]
        }

    def tearDown(self):
        """Clean up test fixtures."""
        self.mock.stop()

    def _create_bucket_with_replication(self):
        """Helper method to create buckets with replication."""
        source_bucket = 'test-source-bucket'
        dest_bucket = 'test-destination-bucket'
        
        self.s3_client.create_bucket(Bucket=source_bucket)
        self.s3_client.create_bucket(Bucket=dest_bucket)
        
        self.s3_client.put_bucket_versioning(
            Bucket=source_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        self.s3_client.put_bucket_versioning(
            Bucket=dest_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        self.s3_client.put_bucket_replication(
            Bucket=source_bucket,
            ReplicationConfiguration=self.sample_replication_config
        )
        
        return source_bucket, dest_bucket

    def _create_bucket_without_replication(self):
        """Helper method to create bucket without replication."""
        bucket_name = 'test-bucket-no-replication'
        
        self.s3_client.create_bucket(Bucket=bucket_name)
        self.s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        return bucket_name

    def test_pause_replication_success(self):
        """Test successfully pausing replication."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        # Pause replication
        original_config = handler.pause_replication(source_bucket)
        
        # Verify original config was returned
        self.assertIsNotNone(original_config)
        self.assertEqual(original_config['Rules'][0]['Status'], 'Enabled')
        
        # Verify replication is now paused
        current_config = handler.get_replication_configuration(source_bucket)
        self.assertEqual(current_config['Rules'][0]['Status'], 'Disabled')

    def test_pause_replication_multiple_rules(self):
        """Test pausing replication with multiple rules."""
        bucket_name = 'test-multi-rule-bucket'
        self.s3_client.create_bucket(Bucket=bucket_name)
        self.s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        multi_rule_config = {
            'Role': 'arn:aws:iam::123456789012:role/s3-replication-role',
            'Rules': [
                {
                    'ID': 'rule-1',
                    'Status': 'Enabled',
                    'Priority': 1,
                    'Filter': {'Prefix': 'documents/'},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket-1'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                },
                {
                    'ID': 'rule-2',
                    'Status': 'Enabled',
                    'Priority': 2,
                    'Filter': {'Prefix': 'images/'},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket-2'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                },
                {
                    'ID': 'rule-3',
                    'Status': 'Disabled',
                    'Priority': 3,
                    'Filter': {'Prefix': 'archive/'},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket-3'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                }
            ]
        }
        
        self.s3_client.put_bucket_replication(
            Bucket=bucket_name,
            ReplicationConfiguration=multi_rule_config
        )
        
        handler = AWSS3Replication(s3_client=self.s3_client)
        original_config = handler.pause_replication(bucket_name)
        
        # Verify all enabled rules are now disabled
        current_config = handler.get_replication_configuration(bucket_name)
        for rule in current_config['Rules']:
            self.assertEqual(rule['Status'], 'Disabled')
        
        # Verify original config had enabled rules
        enabled_count = sum(1 for rule in original_config['Rules'] if rule['Status'] == 'Enabled')
        self.assertEqual(enabled_count, 2)  # rule-1 and rule-2 were enabled

    def test_pause_replication_already_paused(self):
        """Test pausing replication when already paused."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        # Pause once
        handler.pause_replication(source_bucket)
        
        # Pause again (should not fail)
        original_config = handler.pause_replication(source_bucket)
        self.assertIsNotNone(original_config)

    def test_pause_replication_no_replication(self):
        """Test error handling when pausing bucket without replication."""
        bucket_name = self._create_bucket_without_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        with self.assertRaises(RuntimeError):
            handler.pause_replication(bucket_name)


class TestRestoreReplication(unittest.TestCase):
    """Tests for restore_replication method."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock = mock_aws()
        self.mock.start()
        self.s3_client = boto3.client('s3', region_name='us-east-1')
        
        self.sample_replication_config = {
            'Role': 'arn:aws:iam::123456789012:role/s3-replication-role',
            'Rules': [
                {
                    'ID': 'rule-1',
                    'Status': 'Enabled',
                    'Priority': 1,
                    'Filter': {'Prefix': ''},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket',
                        'StorageClass': 'STANDARD'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                }
            ]
        }

    def tearDown(self):
        """Clean up test fixtures."""
        self.mock.stop()

    def _create_bucket_with_replication(self):
        """Helper method to create buckets with replication."""
        source_bucket = 'test-source-bucket'
        dest_bucket = 'test-destination-bucket'
        
        self.s3_client.create_bucket(Bucket=source_bucket)
        self.s3_client.create_bucket(Bucket=dest_bucket)
        
        self.s3_client.put_bucket_versioning(
            Bucket=source_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        self.s3_client.put_bucket_versioning(
            Bucket=dest_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        self.s3_client.put_bucket_replication(
            Bucket=source_bucket,
            ReplicationConfiguration=self.sample_replication_config
        )
        
        return source_bucket, dest_bucket

    def test_restore_replication_success(self):
        """Test successfully restoring replication."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        # Pause replication
        original_config = handler.pause_replication(source_bucket)
        
        # Verify it's paused
        config = handler.get_replication_configuration(source_bucket)
        self.assertEqual(config['Rules'][0]['Status'], 'Disabled')
        
        # Restore replication
        handler.restore_replication(source_bucket, original_config)
        
        # Verify it's restored
        config = handler.get_replication_configuration(source_bucket)
        self.assertEqual(config['Rules'][0]['Status'], 'Enabled')

    def test_restore_replication_multiple_rules(self):
        """Test restoring replication with multiple rules."""
        bucket_name = 'test-multi-rule-restore'
        self.s3_client.create_bucket(Bucket=bucket_name)
        self.s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        multi_rule_config = {
            'Role': 'arn:aws:iam::123456789012:role/s3-replication-role',
            'Rules': [
                {
                    'ID': 'rule-1',
                    'Status': 'Enabled',
                    'Priority': 1,
                    'Filter': {'Prefix': 'documents/'},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket-1'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                },
                {
                    'ID': 'rule-2',
                    'Status': 'Enabled',
                    'Priority': 2,
                    'Filter': {'Prefix': 'images/'},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket-2'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                },
                {
                    'ID': 'rule-3',
                    'Status': 'Disabled',
                    'Priority': 3,
                    'Filter': {'Prefix': 'archive/'},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket-3'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                }
            ]
        }
        
        self.s3_client.put_bucket_replication(
            Bucket=bucket_name,
            ReplicationConfiguration=multi_rule_config
        )
        
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        # Pause and restore
        original_config = handler.pause_replication(bucket_name)
        handler.restore_replication(bucket_name, original_config)
        
        # Verify restoration
        config = handler.get_replication_configuration(bucket_name)
        enabled_count = sum(1 for rule in config['Rules'] if rule['Status'] == 'Enabled')
        disabled_count = sum(1 for rule in config['Rules'] if rule['Status'] == 'Disabled')
        
        self.assertEqual(enabled_count, 2)  # rule-1 and rule-2
        self.assertEqual(disabled_count, 1)  # rule-3 was originally disabled

    def test_restore_replication_empty_config(self):
        """Test error handling when restoring with empty config."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        with self.assertRaisesRegex(RuntimeError, "restoring replication"):
            handler.restore_replication(source_bucket, None)

    def test_restore_replication_invalid_config(self):
        """Test error handling when restoring with invalid config."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        with self.assertRaisesRegex(RuntimeError, "restoring replication"):
            handler.restore_replication(source_bucket, {})


class TestVerifyReplicationStatus(unittest.TestCase):
    """Tests for verify_replication_status method."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock = mock_aws()
        self.mock.start()
        self.s3_client = boto3.client('s3', region_name='us-east-1')
        
        self.sample_replication_config = {
            'Role': 'arn:aws:iam::123456789012:role/s3-replication-role',
            'Rules': [
                {
                    'ID': 'rule-1',
                    'Status': 'Enabled',
                    'Priority': 1,
                    'Filter': {'Prefix': ''},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket',
                        'StorageClass': 'STANDARD'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                }
            ]
        }

    def tearDown(self):
        """Clean up test fixtures."""
        self.mock.stop()

    def _create_bucket_with_replication(self):
        """Helper method to create buckets with replication."""
        source_bucket = 'test-source-bucket'
        dest_bucket = 'test-destination-bucket'
        
        self.s3_client.create_bucket(Bucket=source_bucket)
        self.s3_client.create_bucket(Bucket=dest_bucket)
        
        self.s3_client.put_bucket_versioning(
            Bucket=source_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        self.s3_client.put_bucket_versioning(
            Bucket=dest_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        self.s3_client.put_bucket_replication(
            Bucket=source_bucket,
            ReplicationConfiguration=self.sample_replication_config
        )
        
        return source_bucket, dest_bucket

    def _create_bucket_without_replication(self):
        """Helper method to create bucket without replication."""
        bucket_name = 'test-bucket-no-replication'
        
        self.s3_client.create_bucket(Bucket=bucket_name)
        self.s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        return bucket_name

    def test_verify_status_enabled(self):
        """Test verifying enabled replication status."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        result = handler.verify_replication_status(source_bucket, expected_status='Enabled')
        self.assertTrue(result)

    def test_verify_status_disabled(self):
        """Test verifying disabled replication status."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        # Pause replication
        handler.pause_replication(source_bucket)
        
        # Verify disabled status
        result = handler.verify_replication_status(source_bucket, expected_status='Disabled')
        self.assertTrue(result)

    def test_verify_status_mismatch(self):
        """Test verification when status doesn't match expected."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        # Replication is enabled, but we expect disabled
        result = handler.verify_replication_status(source_bucket, expected_status='Disabled')
        self.assertFalse(result)

    def test_verify_status_no_replication(self):
        """Test verification when bucket has no replication."""
        bucket_name = self._create_bucket_without_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        result = handler.verify_replication_status(bucket_name, expected_status='Enabled')
        self.assertFalse(result)


class TestEndToEndScenario(unittest.TestCase):
    """End-to-end tests for complete chaos scenario workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock = mock_aws()
        self.mock.start()
        self.s3_client = boto3.client('s3', region_name='us-east-1')
        
        self.sample_replication_config = {
            'Role': 'arn:aws:iam::123456789012:role/s3-replication-role',
            'Rules': [
                {
                    'ID': 'rule-1',
                    'Status': 'Enabled',
                    'Priority': 1,
                    'Filter': {'Prefix': ''},
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::destination-bucket',
                        'StorageClass': 'STANDARD'
                    },
                    'DeleteMarkerReplication': {'Status': 'Disabled'}
                }
            ]
        }

    def tearDown(self):
        """Clean up test fixtures."""
        self.mock.stop()

    def _create_bucket_with_replication(self):
        """Helper method to create buckets with replication."""
        source_bucket = 'test-source-bucket'
        dest_bucket = 'test-destination-bucket'
        
        self.s3_client.create_bucket(Bucket=source_bucket)
        self.s3_client.create_bucket(Bucket=dest_bucket)
        
        self.s3_client.put_bucket_versioning(
            Bucket=source_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        self.s3_client.put_bucket_versioning(
            Bucket=dest_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        self.s3_client.put_bucket_replication(
            Bucket=source_bucket,
            ReplicationConfiguration=self.sample_replication_config
        )
        
        return source_bucket, dest_bucket

    def test_complete_pause_restore_cycle(self):
        """Test complete pause and restore cycle."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        # Get initial config
        initial_config = handler.get_replication_configuration(source_bucket)
        self.assertEqual(initial_config['Rules'][0]['Status'], 'Enabled')
        
        # Pause replication
        original_config = handler.pause_replication(source_bucket)
        paused_config = handler.get_replication_configuration(source_bucket)
        self.assertEqual(paused_config['Rules'][0]['Status'], 'Disabled')
        
        # Restore replication
        handler.restore_replication(source_bucket, original_config)
        restored_config = handler.get_replication_configuration(source_bucket)
        self.assertEqual(restored_config['Rules'][0]['Status'], 'Enabled')
        
        # Verify final state matches initial state
        self.assertEqual(restored_config['Rules'][0]['Status'], initial_config['Rules'][0]['Status'])

    def test_multiple_pause_restore_cycles(self):
        """Test multiple pause and restore cycles."""
        source_bucket, _ = self._create_bucket_with_replication()
        handler = AWSS3Replication(s3_client=self.s3_client)
        
        for i in range(3):
            # Pause
            original_config = handler.pause_replication(source_bucket)
            self.assertTrue(handler.verify_replication_status(source_bucket, 'Disabled'))
            
            # Restore
            handler.restore_replication(source_bucket, original_config)
            self.assertTrue(handler.verify_replication_status(source_bucket, 'Enabled'))
