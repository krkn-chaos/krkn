"""AWS S3 Replication Chaos Scenario Plugin.

This plugin implements chaos scenarios for AWS S3 bucket replication,
allowing testing of application resilience when replication is temporarily paused.
"""

import base64
import json
import logging
import time
from typing import Any

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

    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, Any],
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
                config_yaml = yaml.safe_load(f)
                scenario_config = config_yaml["aws_s3_replication_scenarios"]

            # Parse configuration parameters
            bucket_name = get_yaml_item_value(scenario_config, "bucket_name", None)

            try:
                duration = int(get_yaml_item_value(scenario_config, "duration", 300))
            except (TypeError, ValueError):
                logging.error(f"AwsS3ReplicationScenarioPlugin: Invalid duration value '{scenario_config.get('duration')}', must be an integer.")
                return 1
                
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
            s3_handler = AWSS3Replication(region=region)

            # Record start time for telemetry
            start_time = int(time.time())

            # Step 1: Save current replication config and pause replication
            # pause_replication() internally retrieves and returns the original config
            logging.info(
                f"Step 1/3: Pausing replication for bucket '{bucket_name}'..."
            )
            
            try:
                original_config = s3_handler.pause_replication(bucket_name)
                if not original_config or not original_config.get("Rules"):
                    logging.error(f"AwsS3ReplicationScenarioPlugin: No original replication config retrieved for bucket '{bucket_name}', aborting.")
                    return 1
                
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

            # Step 2: Wait for specified duration (chaos period)
            logging.info(
                f"Step 2/3: Replication paused. Waiting for {duration}s (chaos period)..."
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

            # Step 3: Restore replication
            logging.info(
                f"Step 3/3: Restoring replication for bucket '{bucket_name}'..."
            )
            
            try:
                s3_handler.restore_replication(bucket_name, original_config)
                logging.info(f"Successfully restored replication for bucket '{bucket_name}'")
                
                # Verify that all replication rules are currently enabled.
                # Note: this checks the enabled/disabled status of rules, not that the
                # current configuration exactly matches the original_config.
                if s3_handler.verify_replication_status(bucket_name, expected_status='Enabled'):
                    logging.info(
                        "Replication status verification: all replication rules are currently "
                        "'Enabled'. This does not by itself guarantee the policy matches the "
                        "original configuration."
                    )
                else:
                    logging.warning(
                        "Replication status verification: not all replication rules are "
                        "currently 'Enabled'. This does not necessarily mean restoration "
                        "failed (the original configuration may include disabled rules); "
                        "please verify the replication configuration manually.")
                
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
