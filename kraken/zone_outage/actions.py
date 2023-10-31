import yaml
import logging
import time
from ..node_actions.aws_node_scenarios import AWS
from ..cerberus import setup as cerberus
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.utils.functions import log_exception

def run(scenarios_list, config, wait_duration, telemetry: KrknTelemetryKubernetes) -> (list[str], list[ScenarioTelemetry]) :
    """
    filters the subnet of interest and applies the network acl
    to create zone outage
    """
    failed_post_scenarios = ""
    scenario_telemetries: list[ScenarioTelemetry] = []
    failed_scenarios = []

    for zone_outage_config in scenarios_list:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = zone_outage_config
        scenario_telemetry.startTimeStamp = time.time()
        telemetry.set_parameters_base64(scenario_telemetry, zone_outage_config)
        try:
            if len(zone_outage_config) > 1:
                with open(zone_outage_config, "r") as f:
                    zone_outage_config_yaml = yaml.full_load(f)
                    scenario_config = zone_outage_config_yaml["zone_outage"]
                    vpc_id = scenario_config["vpc_id"]
                    subnet_ids = scenario_config["subnet_id"]
                    duration = scenario_config["duration"]
                    cloud_type = scenario_config["cloud_type"]
                    ids = {}
                    acl_ids_created = []

                    if cloud_type.lower() == "aws":
                        cloud_object = AWS()
                    else:
                        logging.error(
                            "Cloud type %s is not currently supported for "
                            "zone outage scenarios"
                            % cloud_type
                        )
                        # removed_exit
                        # sys.exit(1)
                        raise RuntimeError()

                    start_time = int(time.time())

                    for subnet_id in subnet_ids:
                        logging.info("Targeting subnet_id")
                        network_association_ids = []
                        associations, original_acl_id = \
                            cloud_object.describe_network_acls(vpc_id, subnet_id)
                        for entry in associations:
                            if entry["SubnetId"] == subnet_id:
                                network_association_ids.append(
                                    entry["NetworkAclAssociationId"]
                                )
                        logging.info(
                            "Network association ids associated with "
                            "the subnet %s: %s"
                            % (subnet_id, network_association_ids)
                        )
                        acl_id = cloud_object.create_default_network_acl(vpc_id)
                        new_association_id = \
                            cloud_object.replace_network_acl_association(
                                network_association_ids[0], acl_id
                            )

                        # capture the orginal_acl_id, created_acl_id and
                        # new association_id to use during the recovery
                        ids[new_association_id] = original_acl_id
                        acl_ids_created.append(acl_id)

                    # wait for the specified duration
                    logging.info(
                        "Waiting for the specified duration "
                        "in the config: %s" % (duration)
                    )
                    time.sleep(duration)

                    # replace the applied acl with the previous acl in use
                    for new_association_id, original_acl_id in ids.items():
                        cloud_object.replace_network_acl_association(
                            new_association_id,
                            original_acl_id
                        )
                    logging.info(
                        "Wating for 60 seconds to make sure "
                        "the changes are in place"
                    )
                    time.sleep(60)

                    # delete the network acl created for the run
                    for acl_id in acl_ids_created:
                        cloud_object.delete_network_acl(acl_id)

                    logging.info(
                        "End of scenario. "
                        "Waiting for the specified duration: %s" % (wait_duration)
                    )
                    time.sleep(wait_duration)

                    end_time = int(time.time())
                    cerberus.publish_kraken_status(
                        config,
                        failed_post_scenarios,
                        start_time,
                        end_time
                    )
        except (RuntimeError, Exception):
            scenario_telemetry.exitStatus = 1
            failed_scenarios.append(zone_outage_config)
            log_exception(zone_outage_config)
        else:
            scenario_telemetry.exitStatus = 0
        scenario_telemetry.endTimeStamp = time.time()
        scenario_telemetries.append(scenario_telemetry)
    return failed_scenarios, scenario_telemetries

