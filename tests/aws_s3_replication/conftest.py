"""Pytest fixtures for AWS S3 Replication scenario tests."""

import pytest
import boto3
from moto import mock_aws


@pytest.fixture
def s3_client():
    """Provides a mocked S3 client for testing."""
    with mock_aws():
        yield boto3.client('s3', region_name='us-east-1')


@pytest.fixture
def sample_replication_config():
    """Provides a sample replication configuration for testing."""
    return {
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


@pytest.fixture
def s3_bucket_with_replication(s3_client, sample_replication_config):
    """Creates test S3 buckets with replication configured."""
    source_bucket = 'test-source-bucket'
    dest_bucket = 'test-destination-bucket'
    
    # Create buckets
    s3_client.create_bucket(Bucket=source_bucket)
    s3_client.create_bucket(Bucket=dest_bucket)
    
    # Enable versioning on source bucket (required for replication)
    s3_client.put_bucket_versioning(
        Bucket=source_bucket,
        VersioningConfiguration={'Status': 'Enabled'}
    )
    
    # Enable versioning on destination bucket
    s3_client.put_bucket_versioning(
        Bucket=dest_bucket,
        VersioningConfiguration={'Status': 'Enabled'}
    )
    
    # Configure replication
    s3_client.put_bucket_replication(
        Bucket=source_bucket,
        ReplicationConfiguration=sample_replication_config
    )
    
    return s3_client, source_bucket, dest_bucket


@pytest.fixture
def s3_bucket_without_replication(s3_client):
    """Creates a test S3 bucket without replication configured."""
    bucket_name = 'test-bucket-no-replication'
    
    s3_client.create_bucket(Bucket=bucket_name)
    s3_client.put_bucket_versioning(
        Bucket=bucket_name,
        VersioningConfiguration={'Status': 'Enabled'}
    )
    
    return s3_client, bucket_name


@pytest.fixture
def multi_rule_replication_config():
    """Provides a replication configuration with multiple rules."""
    return {
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
