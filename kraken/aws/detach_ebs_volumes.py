import boto3
import logging
import re
import time
import yaml

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes


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

        volume_ids = scenario_config["ebs_volume_id"]
        volume_ids = re.split(r",+\s+|,+|\s+", volume_ids)
        regions = scenario_config["region"]
        # TODO support for multiple regions
        # regions = re.split(r",+\s+|,+|\s+", regions)
        aws_access_key_id = scenario_config["aws_access_key_id"]
        aws_secret_access_key = scenario_config["aws_secret_access_key"]
        chaos_duration = scenario_config["chaos_duration"]

        # TODO implement detaching volumes based on tag and instance
        volume_tag = scenario_config["ebs_volume_tag"]

        # Get the EBS attachment details
        ec2, ec2_client = get_ec2_session(
            regions, aws_access_key_id, aws_secret_access_key
        )
        volume_details = get_ebs_volume_attachment_details(
            volume_ids, ec2_client
        )
        logging.info("Obtaining attachment details...")
        for volume in volume_details:
            logging.info(
                f"Volume {volume['VolumeId']} status: {volume['State']}"
            )

            # Try detach volume
            detach_ebs_volume(volume, ec2_client, ec2, chaos_duration)

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


def get_ebs_volume_attachment_details(volume_ids: list, ec2_client):
    response = ec2_client.describe_volumes(VolumeIds=volume_ids)
    volumes_details = response["Volumes"]
    return volumes_details


def get_ebs_volume_state(volume_id: str, ec2_resource):
    volume = ec2_resource.Volume(volume_id)
    state = volume.state
    return state


def detach_ebs_volume(volume: dict, ec2_client, ec2_resource, duration: int):
    if volume["State"] == "in-use":
        logging.info(f"Detaching volume {volume['VolumeId']}...")
        ec2_client.detach_volume(VolumeId=volume['VolumeId'])
        if check_attachment_state(volume, ec2_resource, "available") == 1:
            return
        logging.info(f"Volume {volume['VolumeId']} successfully detached")
        logging.info("Waiting for chaos duration...")
        time.sleep(duration)

        # Attach volume back
        attach_ebs_volume(volume, ec2_client)
        if check_attachment_state(volume, ec2_resource, "in-use") == 1:
            return
        logging.info(f"Volume {volume['VolumeId']} successfully attached")


def attach_ebs_volume(volume: dict, ec2_client):
    for attachment in volume["Attachments"]:
        ec2_client.attach_volume(
            InstanceId=attachment["InstanceId"],
            Device=attachment["Device"],
            VolumeId=volume["VolumeId"],
        )


def get_ec2_session(
    region: str, aws_access_key_id: str, aws_secret_access_key: str
):
    ec2 = boto3.resource(
        "ec2",
        region_name=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )
    ec2_client = boto3.client(
        "ec2",
        region_name=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )
    return ec2, ec2_client


def check_attachment_state(volume, ec2, desired_state: str):
    time.sleep(5)
    state = get_ebs_volume_state(volume["VolumeId"], ec2)
    for i in range(5):
        if state == desired_state:
            return 0
        logging.debug(f"Volume in undesired state {state}...")
        time.sleep(3)
    else:
        logging.error(
            f"Something went wrong, last volume {volume['VolumeId']} "
            f"state was {state}, desired state {desired_state}"
        )
        return 1
