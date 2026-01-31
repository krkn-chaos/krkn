"""AWS S3 Replication operations for chaos scenarios.

This module provides the core functionality for pausing and restoring
S3 bucket replication configurations.
"""

import logging
import copy
import boto3
from botocore.exceptions import ClientError, BotoCoreError


class AWSS3Replication:
    """Handles AWS S3 replication operations for chaos scenarios."""

    def __init__(self, region=None, s3_client=None):
        """Initialize AWS S3 Replication handler.

        Args:
            region: AWS region name (optional, uses default if not specified)
            s3_client: Pre-configured boto3 S3 client (optional, for testing)
        """
        if s3_client is not None:
            # Use provided client (for testing with moto/localstack)
            self.s3_client = s3_client
        else:
            # Create real AWS client
            if region:
                self.s3_client = boto3.client('s3', region_name=region)
            else:
                self.s3_client = boto3.client('s3')
        
        logging.info("AWS S3 Replication handler initialized")

    def get_replication_configuration(self, bucket_name):
        """Retrieve the current replication configuration for a bucket.

        Args:
            bucket_name: Name of the S3 bucket

        Returns:
            dict: The replication configuration

        Raises:
            RuntimeError: If unable to retrieve configuration
        """
        try:
            logging.info(f"Retrieving replication configuration for bucket: {bucket_name}")
            response = self.s3_client.get_bucket_replication(Bucket=bucket_name)
            
            if 'ReplicationConfiguration' not in response:
                logging.error(
                    f"Bucket {bucket_name} returned empty replication configuration"
                )
                raise RuntimeError(
                    f"Bucket {bucket_name} has no replication configuration"
                )
            
            config = response['ReplicationConfiguration']
            num_rules = len(config.get('Rules', []))
            logging.info(
                f"Successfully retrieved replication configuration with {num_rules} rule(s)"
            )
            return config
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'ReplicationConfigurationNotFoundError':
                logging.error(
                    f"Bucket '{bucket_name}' has no replication configured. "
                    f"This scenario requires S3 replication to be set up first. "
                    f"Please configure replication before running this chaos scenario."
                )
            elif error_code == 'NoSuchBucket':
                logging.error(
                    f"Bucket '{bucket_name}' does not exist. "
                    f"Please verify the bucket name and try again."
                )
            elif error_code == 'AccessDenied':
                logging.error(
                    f"Access denied when trying to get replication configuration for bucket '{bucket_name}'. "
                    f"The IAM user/role lacks 's3:GetReplicationConfiguration' permission. "
                    f"Please add the required IAM permissions and try again."
                )
            else:
                logging.error(
                    f"Failed to get replication configuration for bucket '{bucket_name}': "
                    f"{error_code} - {e.response['Error'].get('Message', 'Unknown error')}"
                )
            
            raise RuntimeError(
                f"Failed to retrieve replication configuration for bucket '{bucket_name}'"
            )
        
        except BotoCoreError as e:
            logging.error(
                f"AWS connection error while accessing bucket '{bucket_name}': {str(e)}"
            )
            raise RuntimeError(
                f"AWS connection error for bucket '{bucket_name}'"
            )
        
        except Exception as e:
            logging.error(
                f"Unexpected error retrieving replication configuration for bucket '{bucket_name}': {str(e)}"
            )
            raise RuntimeError(
                f"Unexpected error for bucket '{bucket_name}'"
            )

    def pause_replication(self, bucket_name):
        """Pause replication by disabling all replication rules.

        Args:
            bucket_name: Name of the S3 bucket

        Returns:
            dict: The original replication configuration (for restoration)

        Raises:
            RuntimeError: If unable to pause replication
        """
        try:
            # Get current configuration
            original_config = self.get_replication_configuration(bucket_name)
            
            # Create a deep copy to modify
            modified_config = copy.deepcopy(original_config)
            
            # Disable all replication rules
            disabled_count = 0
            for rule in modified_config.get('Rules', []):
                if rule.get('Status') == 'Enabled':
                    rule['Status'] = 'Disabled'
                    disabled_count += 1
                    logging.debug(f"Disabling replication rule: {rule.get('ID', 'unknown')}")
            
            if disabled_count == 0:
                logging.warning(
                    f"No enabled replication rules found for bucket '{bucket_name}'. "
                    f"Replication may already be paused."
                )
            
            # Apply the modified configuration
            logging.info(
                f"Pausing replication for bucket '{bucket_name}' "
                f"({disabled_count} rule(s) will be disabled)"
            )
            
            self.s3_client.put_bucket_replication(
                Bucket=bucket_name,
                ReplicationConfiguration=modified_config
            )
            
            logging.info(
                f"Successfully paused replication for bucket '{bucket_name}'"
            )
            
            # Return original config for restoration
            return original_config
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'AccessDenied':
                logging.error(
                    f"Access denied when trying to pause replication for bucket '{bucket_name}'. "
                    f"The IAM user/role lacks 's3:PutReplicationConfiguration' permission. "
                    f"Please add the required IAM permissions and try again."
                )
            else:
                logging.error(
                    f"Failed to pause replication for bucket '{bucket_name}': "
                    f"{error_code} - {e.response['Error'].get('Message', 'Unknown error')}"
                )
            
            raise RuntimeError(
                f"Failed to pause replication for bucket '{bucket_name}'"
            )
        
        except Exception as e:
            logging.error(
                f"Unexpected error pausing replication for bucket '{bucket_name}': {str(e)}"
            )
            raise RuntimeError(
                f"Unexpected error pausing replication for bucket '{bucket_name}'"
            )

    def restore_replication(self, bucket_name, original_config):
        """Restore replication by re-enabling rules from original configuration.

        Args:
            bucket_name: Name of the S3 bucket
            original_config: The original replication configuration to restore

        Raises:
            RuntimeError: If unable to restore replication
        """
        try:
            if not original_config:
                logging.error(
                    f"Cannot restore replication for bucket '{bucket_name}': "
                    f"original configuration is empty or None"
                )
                raise RuntimeError(
                    f"Cannot restore replication for bucket '{bucket_name}': "
                    f"original configuration is invalid or missing"
                )
            
            enabled_count = sum(
                1 for rule in original_config.get('Rules', [])
                if rule.get('Status') == 'Enabled'
            )
            
            logging.info(
                f"Restoring replication for bucket '{bucket_name}' "
                f"({enabled_count} rule(s) will be re-enabled)"
            )
            
            self.s3_client.put_bucket_replication(
                Bucket=bucket_name,
                ReplicationConfiguration=original_config
            )
            
            logging.info(
                f"Successfully restored replication for bucket '{bucket_name}'"
            )
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'AccessDenied':
                logging.error(
                    f"Access denied when trying to restore replication for bucket '{bucket_name}'. "
                    f"The IAM user/role lacks 's3:PutReplicationConfiguration' permission. "
                    f"Please add the required IAM permissions and try again."
                )
            else:
                logging.error(
                    f"Failed to restore replication for bucket '{bucket_name}': "
                    f"{error_code} - {e.response['Error'].get('Message', 'Unknown error')}"
                )
            
            raise RuntimeError(
                f"Failed to restore replication for bucket '{bucket_name}'"
            )
        
        except Exception as e:
            logging.error(
                f"Unexpected error restoring replication for bucket '{bucket_name}': {str(e)}"
            )
            raise RuntimeError(
                f"Unexpected error restoring replication for bucket '{bucket_name}'"
            )

    def verify_replication_status(self, bucket_name, expected_status='Enabled'):
        """Verify the current status of replication rules.

        Args:
            bucket_name: Name of the S3 bucket
            expected_status: Expected status ('Enabled' or 'Disabled')

        Returns:
            bool: True if all rules match expected status, False otherwise
        """
        try:
            config = self.get_replication_configuration(bucket_name)
            rules = config.get('Rules', [])
            
            if not rules:
                logging.warning(f"No replication rules found for bucket '{bucket_name}'")
                return False
            
            status_match = all(
                rule.get('Status') == expected_status
                for rule in rules
            )
            
            if status_match:
                logging.info(
                    f"All replication rules for bucket '{bucket_name}' are '{expected_status}'"
                )
            else:
                logging.warning(
                    f"Not all replication rules for bucket '{bucket_name}' are '{expected_status}'"
                )
            
            return status_match
            
        except Exception as e:
            logging.error(
                f"Failed to verify replication status for bucket '{bucket_name}': {str(e)}"
            )
            return False
