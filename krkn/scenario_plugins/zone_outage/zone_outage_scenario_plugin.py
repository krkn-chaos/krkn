import logging
import time

import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import log_exception

from krkn import utils
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.native.network import cerberus
from krkn.scenario_plugins.node_actions.aws_node_scenarios import AWS


class ZoneOutageScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario, "r") as f:
                zone_outage_config_yaml = yaml.full_load(f)
                scenario_config = zone_outage_config_yaml["zone_outage"]
                vpc_id = scenario_config["vpc_id"]
                subnet_ids = scenario_config["subnet_id"]
                duration = scenario_config["duration"]
                cloud_type = scenario_config["cloud_type"]
                # Add support for user-provided default network ACL
                default_acl_id = scenario_config.get("default_acl_id")
                ids = {}
                acl_ids_created = []

                if cloud_type.lower() == "aws":
                    cloud_object = AWS()
                else:
                    logging.error(
                        "ZoneOutageScenarioPlugin Cloud type %s is not currently supported for "
                        "zone outage scenarios" % cloud_type
                    )
                    return 1

                start_time = int(time.time())

                for subnet_id in subnet_ids:
                    logging.info("Targeting subnet_id")
                    network_association_ids = []
                    associations, original_acl_id = cloud_object.describe_network_acls(
                        vpc_id, subnet_id
                    )
                    for entry in associations:
                        if entry["SubnetId"] == subnet_id:
                            network_association_ids.append(
                                entry["NetworkAclAssociationId"]
                            )
                    logging.info(
                        "Network association ids associated with "
                        "the subnet %s: %s" % (subnet_id, network_association_ids)
                    )
                    
                    # Use provided default ACL if available, otherwise create a new one
                    if default_acl_id:
                        acl_id = default_acl_id
                        # Don't add to acl_id since we didn't create it
                    else:
                        acl_id = cloud_object.create_default_network_acl(vpc_id)
                        acl_ids_created.append(acl_id)

                    new_association_id = cloud_object.replace_network_acl_association(
                        network_association_ids[0], acl_id
                    )

                    # capture the orginal_acl_id, created_acl_id and
                    # new association_id to use during the recovery
                    ids[new_association_id] = original_acl_id

                # wait for the specified duration
                logging.info(
                    "Waiting for the specified duration " "in the config: %s" % duration
                )
                time.sleep(duration)

                # replace the applied acl with the previous acl in use
                for new_association_id, original_acl_id in ids.items():
                    cloud_object.replace_network_acl_association(
                        new_association_id, original_acl_id
                    )
                logging.info(
                    "Wating for 60 seconds to make sure " "the changes are in place"
                )
                time.sleep(60)

                # delete the network acl created for the run
                for acl_id in acl_ids_created:
                    cloud_object.delete_network_acl(acl_id)

                end_time = int(time.time())
                cerberus.publish_kraken_status(krkn_config, [], start_time, end_time)
        except (RuntimeError, Exception):
            logging.error(
                f"ZoneOutageScenarioPlugin scenario {scenario} failed with exception: {e}"
            )
            return 1
        else:
            return 0

    def get_scenario_types(self) -> list[str]:
        return ["zone_outages_scenarios"]
