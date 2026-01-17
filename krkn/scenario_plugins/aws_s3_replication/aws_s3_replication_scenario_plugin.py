"""AWS S3 Replication Chaos Scenario Plugin.

This plugin implements chaos scenarios for AWS S3 bucket replication,
allowing testing of application resilience when replication is temporarily paused.
"""

import base64
import json
import logging
import time

import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value

from krkn import cerberus
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.aws_s3_replication.aws_s3_scenarios import AWSS3Replication
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator


class AwsS3ReplicationScenarioPlugin(AbstractScenarioPlugin):
    """Plugin for AWS S3 replication chaos scenarios."""

    def __init__(self):
        """Initialize the AWS S3 Replication scenario plugin."""
        super().__init__(scenario_type="aws_s3_replication_scenarios")

    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        """Execute the AWS S3 replication chaos scenario.

        Args:
            run_uuid: Unique identifier for this chaos run
            scenario: Path to the scenario configuration file
            krkn_config: Krkn configuration dictionary
            lib_telemetry: Telemetry object for monitoring
            scenario_telemetry: Scenario-specific telemetry

        Returns:
            int: 0 if successful, 1 if failed
        """
        try:
            # Load scenario configuration
            with open(scenario, "r") as f:
                config_yaml = yaml.full_load(f)
                scenario_config = config_yaml["aws_s3_replication_scenarios"]

            # Parse configuration parameters
            bucket_name = get_yaml_item_value(scenario_config, "bucket_name", None)
            duration = get_yaml_item_value(scenario_config, "duration", 300)
            region = get_yaml_item_value(scenario_config, "region", None)

            logging.info(
                "AWS S3 Replication Chaos Scenario - Input parameters:\n"
                f"  Bucket name: '{bucket_name}'\n"
                f"  Duration: {duration}s\n"
                f"  Region: '{region if region else 'default'}'"
            )

            # Validate required parameters
            if not bucket_name:
                logging.error(
                    "AwsS3ReplicationScenarioPlugin: 'bucket_name' is required. "
                    "Please specify the S3 bucket name in the scenario configuration."
                )
                return 1

            if duration <= 0:
                logging.error(
                    f"AwsS3ReplicationScenarioPlugin: Invalid duration '{duration}'. "
                    f"Duration must be a positive integer (seconds)."
                )
                return 1

            # Initialize AWS S3 handler
            logging.info("Initializing AWS S3 replication handler...")
            s3_handler = AWSS3Replication(region=region)

            # Record start time for telemetry
            start_time = int(time.time())

            # Step 1: Get and save current replication configuration
            logging.info(
                f"Step 1/4: Retrieving current replication configuration for bucket '{bucket_name}'..."
            )
            original_config = s3_handler.get_replication_configuration(bucket_name)
            
            if not original_config:
                logging.error(
                    f"AwsS3ReplicationScenarioPlugin: Failed to retrieve replication configuration "
                    f"for bucket '{bucket_name}'"
                )
                return 1

            logging.info(
                f"Successfully retrieved replication configuration with "
                f"{len(original_config.get('Rules', []))} rule(s)"
            )

            # Step 2: Pause replication
            logging.info(
                f"Step 2/4: Pausing replication for bucket '{bucket_name}'..."
            )
            
            try:
                s3_handler.pause_replication(bucket_name)
                logging.info(f"Successfully paused replication for bucket '{bucket_name}'")
                
                # Set rollback callable to ensure replication is restored on failure or interruption
                rollback_data = {
                    "bucket_name": bucket_name,
                    "region": region,
                    "original_config": original_config,
                }
                json_str = json.dumps(rollback_data)
                encoded_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                
                self.rollback_handler.set_rollback_callable(
                    self.rollback_replication,
                    RollbackContent(
                        namespace="aws-s3",  # Logical namespace for AWS resources
                        resource_identifier=encoded_data,
                    ),
                )
                
            except Exception as e:
                logging.error(
                    f"AwsS3ReplicationScenarioPlugin: Failed to pause replication: {str(e)}"
                )
                return 1

            # Step 3: Wait for specified duration (chaos period)
            logging.info(
                f"Step 3/4: Replication paused. Waiting for {duration}s (chaos period)..."
            )
            
            # Log periodic status updates during wait
            elapsed = 0
            log_interval = min(60, duration // 4) if duration >= 60 else duration
            
            while elapsed < duration:
                wait_time = min(log_interval, duration - elapsed)
                time.sleep(wait_time)
                elapsed += wait_time
                
                if elapsed < duration:
                    remaining = duration - elapsed
                    logging.info(
                        f"Chaos period in progress... {elapsed}s elapsed, {remaining}s remaining"
                    )
            
            logging.info(f"Chaos period completed ({duration}s)")

            # Step 4: Restore replication
            logging.info(
                f"Step 4/4: Restoring replication for bucket '{bucket_name}'..."
            )
            
            try:
                s3_handler.restore_replication(bucket_name, original_config)
                logging.info(f"Successfully restored replication for bucket '{bucket_name}'")
                
                # Verify restoration
                if s3_handler.verify_replication_status(bucket_name, expected_status='Enabled'):
                    logging.info("Replication status verified: All rules are enabled")
                else:
                    logging.warning(
                        "Replication status verification: Some rules may not be enabled. "
                        "Please verify manually."
                    )
                
            except Exception as e:
                logging.error(
                    f"AwsS3ReplicationScenarioPlugin: Failed to restore replication: {str(e)}"
                )
                return 1

            # Record end time and publish status
            end_time = int(time.time())
            total_duration = end_time - start_time
            
            logging.info(
                f"AWS S3 Replication chaos scenario completed successfully in {total_duration}s"
            )
            
            cerberus.publish_kraken_status(krkn_config, [], start_time, end_time)
            
            return 0

        except FileNotFoundError:
            logging.error(
                f"AwsS3ReplicationScenarioPlugin: Scenario configuration file not found: {scenario}"
            )
            return 1
        
        except yaml.YAMLError as e:
            logging.error(
                f"AwsS3ReplicationScenarioPlugin: Failed to parse scenario configuration: {str(e)}"
            )
            return 1
        
        except KeyError as e:
            logging.error(
                f"AwsS3ReplicationScenarioPlugin: Missing required configuration key: {str(e)}. "
                f"Please ensure 'aws_s3_replication_scenarios' is defined in the scenario file."
            )
            return 1
        
        except RuntimeError as e:
            logging.error(
                f"AwsS3ReplicationScenarioPlugin: Runtime error during scenario execution: {str(e)}"
            )
            return 1
        
        except Exception as e:
            logging.error(
                f"AwsS3ReplicationScenarioPlugin: Unexpected error during scenario execution: {str(e)}"
            )
            return 1

    @staticmethod
    def rollback_replication(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        """Rollback function to restore S3 replication configuration.

        This function is called automatically if the scenario fails or is interrupted,
        ensuring that replication is restored to its original state.

        Args:
            rollback_content: Rollback content containing encoded configuration data
            lib_telemetry: Telemetry object (not used for AWS operations)
        """
        try:
            # Decode rollback data
            decoded_data = base64.b64decode(
                rollback_content.resource_identifier.encode('utf-8')
            ).decode('utf-8')
            rollback_data = json.loads(decoded_data)
            
            bucket_name = rollback_data["bucket_name"]
            region = rollback_data.get("region")
            original_config = rollback_data["original_config"]
            
            logging.info(
                f"Rolling back AWS S3 replication scenario: "
                f"Restoring replication for bucket '{bucket_name}'"
            )
            
            # Initialize S3 handler and restore configuration
            s3_handler = AWSS3Replication(region=region)
            s3_handler.restore_replication(bucket_name, original_config)
            
            logging.info(
                f"AWS S3 replication rollback completed successfully for bucket '{bucket_name}'"
            )
            
        except Exception as e:
            logging.error(
                f"Failed to rollback AWS S3 replication scenario: {str(e)}. "
                f"Manual intervention may be required to restore replication."
            )

    def get_scenario_types(self) -> list[str]:
        """Return the scenario types handled by this plugin.

        Returns:
            list[str]: List containing 'aws_s3_replication_scenarios'
        """
        return ["aws_s3_replication_scenarios"]
