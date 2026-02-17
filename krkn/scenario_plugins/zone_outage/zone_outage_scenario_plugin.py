import logging
import time

import yaml

from multiprocessing.pool import ThreadPool
from itertools import repeat

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNodeStatus
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn_lib.utils import get_yaml_item_value
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.native.network import cerberus

from krkn.scenario_plugins.node_actions.aws_node_scenarios import AWS
from krkn.scenario_plugins.node_actions.gcp_node_scenarios import gcp_node_scenarios

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
                cloud_type = scenario_config["cloud_type"]
                kube_check = get_yaml_item_value(scenario_config, "kube_check", True)
                start_time = int(time.time())
                if cloud_type.lower() == "aws":
                    self.cloud_object = AWS()
                    self.network_based_zone(scenario_config)
                else:
                    kubecli = lib_telemetry.get_lib_kubernetes()
                    if cloud_type.lower() == "gcp":
                        affected_nodes_status = AffectedNodeStatus()
                        self.cloud_object = gcp_node_scenarios(kubecli, kube_check, affected_nodes_status)
                        self.node_based_zone(scenario_config, kubecli)
                        affected_nodes_status = self.cloud_object.affected_nodes_status
                        scenario_telemetry.affected_nodes.extend(affected_nodes_status.affected_nodes)
                    else:
                        logging.error(
                            "ZoneOutageScenarioPlugin Cloud type %s is not currently supported for "
                            "zone outage scenarios" % cloud_type
                        )
                        return 1

                end_time = int(time.time())
                cerberus.publish_kraken_status(krkn_config, [], start_time, end_time)
        except (RuntimeError, Exception) as e:
            logging.error(
                f"ZoneOutageScenarioPlugin scenario {scenario} failed with exception: {e}"
            )
            return 1
        else:
            return 0
        
    def node_based_zone(self, scenario_config: dict[str, any], kubecli: KrknKubernetes ):
        zone = scenario_config["zone"]
        duration = get_yaml_item_value(scenario_config, "duration", 60)
        timeout = get_yaml_item_value(scenario_config, "timeout", 180)
        label_selector = f"topology.kubernetes.io/zone={zone}"
        try: 
            # get list of nodes in zone/region
            nodes = kubecli.list_killable_nodes(label_selector)
            # stop nodes in parallel 
            pool = ThreadPool(processes=len(nodes))
    
            pool.starmap(
                self.cloud_object.node_stop_scenario,zip(repeat(1), nodes, repeat(timeout))
            )

            pool.close()

            logging.info(
                "Waiting for the specified duration " "in the config: %s" % duration
            )
            time.sleep(duration)

            # start nodes in parallel 
            pool = ThreadPool(processes=len(nodes))
            pool.starmap(
                self.cloud_object.node_start_scenario,zip(repeat(1), nodes, repeat(timeout))
            )
            pool.close()
        except Exception as e:
            logging.info(
                f"Node based zone outage scenario failed with exception: {e}"
            )
            return 1
        else:
            return 0

    def network_based_zone(self, scenario_config: dict[str, any]):

        vpc_id = scenario_config["vpc_id"]
        subnet_ids = scenario_config["subnet_id"]
        duration = scenario_config["duration"]
        # Add support for user-provided default network ACL
        default_acl_id = scenario_config.get("default_acl_id")
        ids = {}
        acl_ids_created = []
        for subnet_id in subnet_ids:
            logging.info("Targeting subnet_id")
            network_association_ids = []
            associations, original_acl_id = self.cloud_object.describe_network_acls(
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
                logging.info(
                    "Using provided default ACL ID %s - this ACL will not be deleted after the scenario", 
                    default_acl_id
                )
                # Don't add to acl_ids_created since we don't want to delete user-provided ACLs at cleanup
            else:
                acl_id = self.cloud_object.create_default_network_acl(vpc_id)
                logging.info("Created new default ACL %s", acl_id)
                acl_ids_created.append(acl_id)

            new_association_id = self.cloud_object.replace_network_acl_association(
                network_association_ids[0], acl_id
            )

            # capture the original_acl_id, created_acl_id and
            # new association_id to use during the recovery
            ids[new_association_id] = original_acl_id

        # wait for the specified duration
        logging.info(
            "Waiting for the specified duration " "in the config: %s" % duration
        )
        time.sleep(duration)

        # replace the applied acl with the previous acl in use
        for new_association_id, original_acl_id in ids.items():
            self.cloud_object.replace_network_acl_association(
                new_association_id, original_acl_id
            )
        logging.info(
            "Waiting for 60 seconds to make sure " "the changes are in place"
        )
        time.sleep(60)

        # delete the network acl created for the run
        for acl_id in acl_ids_created:
            self.cloud_object.delete_network_acl(acl_id)


    def get_scenario_types(self) -> list[str]:
        return ["zone_outages_scenarios"]
