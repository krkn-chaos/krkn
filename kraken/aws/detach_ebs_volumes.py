import boto3
import logging
import re
import time
import yaml

from botocore.exceptions import ClientError, EndpointConnectionError
from urllib3.exceptions import ConnectionError, NewConnectionError

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.utils.functions import get_yaml_item_value


def run(
    scenarios_list: list[str],
    wait_duration: int,
    krkn_lib: KrknKubernetes,
    telemetry: KrknTelemetryKubernetes,
) -> (list[str], list[ScenarioTelemetry]):

    logging.info("Detach ebs volumes scenario running...")
    scenario_telemetries = list[ScenarioTelemetry]()
    failed_post_scenarios = []
    for scenario in scenarios_list:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = scenario
        scenario_telemetry.start_timestamp = time.time()
        telemetry.set_parameters_base64(scenario_telemetry, scenario)

        # Loading parameters from scenario config
        with open(scenario) as stream:
            scenario_config = yaml.safe_load(stream)

        # Load and validate credentials
        aws_access_key_id = scenario_config["aws_access_key_id"]
        aws_secret_access_key = scenario_config["aws_secret_access_key"]
        chaos_duration = scenario_config["chaos_duration"]
        regions = scenario_config["regions"]

        # Check that aws credentials are valid
        if not validate_credentials(aws_access_key_id, aws_secret_access_key):
            logging.error(
                f"Scenario {scenario} failed with "
                f"exception: AWS was not able to validate provided access "
                f"credentials. Please make sure the aws global credentials or "
                f"credentials provided in scenario config are correct."
            )
            fail(scenario_telemetry, scenario_telemetries)
            failed_post_scenarios.append(scenario)
            return failed_post_scenarios, scenario_telemetries

        for region in regions:
            if not region["region"]:
                logging.error("Region name must be specified! Skipping region")
                continue
            logging.info(f"Detaching specified volumes for "
                         f"region {region['region']}...")
            detach_volumes_for_region(
                region,
                chaos_duration,
                aws_secret_access_key,
                aws_access_key_id
            )

        logging.info(
            f"End of scenario {scenario}. "
            f"Waiting for the specified duration {wait_duration}..."
        )
        time.sleep(wait_duration)

        scenario_telemetry.exit_status = 0
        scenario_telemetry.end_timestamp = time.time()
        scenario_telemetries.append(scenario_telemetry)
        logging.info(f"Scenario {scenario} successfully finished")

    return failed_post_scenarios, scenario_telemetries


def fail(
    scenario_telemetry: ScenarioTelemetry,
    scenario_telemetries: list[ScenarioTelemetry],
):
    scenario_telemetry.exit_status = 1
    scenario_telemetry.end_timestamp = time.time()
    scenario_telemetries.append(scenario_telemetry)


def detach_volumes_for_region(
    region: dict,
    chaos_duration: int,
    aws_access_key_id: str,
    aws_secret_access_key: str
):
    region_name = region["region"]
    instance_ids = region["node_ids"]
    if not isinstance(instance_ids, list) and instance_ids is not None:
        instance_ids = re.split(r",+\s+|,+|\s+", instance_ids)
    volume_ids = get_yaml_item_value(region, "ebs_volume_ids", [])
    if not isinstance(volume_ids, list) and volume_ids is not None:
        volume_ids = re.split(r",+\s+|,+|\s+", volume_ids)

    # Get the EBS attachment details
    ec2, ec2_client = get_ec2_session(
        region_name, aws_access_key_id, aws_secret_access_key
    )

    if instance_ids:
        try:
            volume_ids = get_instance_attachment_details(
                instance_ids, volume_ids, ec2_client
            )
        except ClientError as e:
            logging.error(
                f"Detaching volumes in region {region_name} failed "
                f"with exception: {e}. Skipping region"
            )
            return
        except (ConnectionError, NewConnectionError, EndpointConnectionError) as e:
            logging.error(
                f"Detaching volumes in region {region_name} failed "
                f"with exception: {e}. Please make sure region name is "
                f"correct. Skipping region"
            )
            return

    # Check that there are any volume ids
    if not volume_ids:
        logging.warning(
            f"No volumes for region {region_name}! Skipping region"
        )
        return

    logging.info("Obtaining attachment details...")

    try:
        volume_details = get_ebs_volume_attachment_details(
            volume_ids, ec2_client
        )
    except ClientError as e:
        logging.error(
            f"Detaching volumes in region {region_name} failed "
            f"with exception: {e}. Skipping region"
        )
        return

    for volume in volume_details:
        logging.info(
            f"Volume {volume['VolumeId']} status: {volume['State']}"
        )

        # Detaching volume and attaching it back
        detach_ebs_volume(volume, ec2_client, ec2, chaos_duration)

    return


def detach_ebs_volume(volume: dict, ec2_client, ec2_resource, duration: int):
    if volume["State"] == "in-use":
        logging.info(f"Detaching volume {volume['VolumeId']}...")
        try:
            ec2_client.detach_volume(VolumeId=volume['VolumeId'], Force=True)
        except ClientError as e:
            logging.error(
                f"Detaching volume failed with exception: {e}. Skipping"
            )
            return
        if not check_attachment_state(volume, ec2_resource, "available"):
            return
        logging.info(f"Volume {volume['VolumeId']} successfully detached")
        logging.info("Waiting for chaos duration...")
        time.sleep(duration)

        # Attach volume back
        attach_ebs_volume(volume, ec2_client)
        if not check_attachment_state(volume, ec2_resource, "in-use"):
            return
        logging.info(f"Volume {volume['VolumeId']} successfully attached")


def get_ec2_session(
    region: str, aws_access_key_id: str, aws_secret_access_key: str
):
    if aws_access_key_id and aws_secret_access_key:
        ec2_client = boto3.client(
            "ec2",
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        ec2_resource = boto3.resource(
            "ec2",
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
    else:
        ec2_resource = boto3.resource("ec2", region_name=region)
        ec2_client = boto3.client("ec2", region_name=region)

    return ec2_resource, ec2_client


def get_ebs_volume_attachment_details(volume_ids: list, ec2_client):
    response = ec2_client.describe_volumes(VolumeIds=volume_ids)
    volumes_details = response["Volumes"]
    return volumes_details


def get_instance_attachment_details(
    instance_ids: list, volume_ids: list, ec2_client
):
    response = ec2_client.describe_instances(InstanceIds=instance_ids)
    instances_attachment_details = response['Reservations'][0]['Instances'][0]['BlockDeviceMappings']
    for device in instances_attachment_details:
        volume_id = device['Ebs']['VolumeId']
        volume_ids.append(volume_id)
    volume_ids = list(dict.fromkeys(volume_ids))
    return volume_ids


def get_ebs_volume_state(volume_id: str, ec2_resource):
    volume = ec2_resource.Volume(volume_id)
    state = volume.state
    return state


def attach_ebs_volume(volume: dict, ec2_client):
    for attachment in volume["Attachments"]:
        ec2_client.attach_volume(
            InstanceId=attachment["InstanceId"],
            Device=attachment["Device"],
            VolumeId=volume["VolumeId"],
        )


def check_attachment_state(volume, ec2, desired_state: str):
    time.sleep(5)
    for i in range(5):
        state = get_ebs_volume_state(volume["VolumeId"], ec2)
        if state == desired_state:
            return True
        logging.debug(f"Volume {volume} in undesired state {state}...")
        time.sleep(3)

    logging.warning(
        f"Something went wrong, volume {volume['VolumeId']} "
        f"state was {state}, desired state is {desired_state}. "
        f"Please check status of your volume!"
    )
    return False


def validate_credentials(aws_access_key_id: str, aws_secret_access_key: str):

    logging.info("Validating credentials...")
    if aws_access_key_id and aws_secret_access_key:
        sts = boto3.client(
            "sts",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name="us-east-2"
        )
    else:
        sts = boto3.client("sts", region_name="us-east-2")

    try:
        sts.get_caller_identity()
    except ClientError:
        return False

    logging.info("Credential are validated")
    return True
