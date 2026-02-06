import base64
import json
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
from krkn.rollback.config import RollbackCallable, RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.native.network import cerberus

from krkn.scenario_plugins.node_actions.aws_node_scenarios import AWS
from krkn.scenario_plugins.node_actions.gcp_node_scenarios import gcp_node_scenarios

class ZoneOutageScenarioPlugin(AbstractScenarioPlugin):
    @set_rollback_context_decorator
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
                rollback_data = {}
                if cloud_type.lower() == "aws":
                    # Get region from scenario config or fall back to environment/AWS config
                    region = get_yaml_item_value(scenario_config, "region", None)
                    rollback_data["cloud_object"] = self.cloud_object = AWS(region=region)
                    rollback_data["network_based_zone"] = self.network_based_zone(scenario_config)
                else:
                    kubecli = lib_telemetry.get_lib_kubernetes()
                    if cloud_type.lower() == "gcp":
                        affected_nodes_status = AffectedNodeStatus()
                        rollback_data["cloud_object"] = self.cloud_object = gcp_node_scenarios(kubecli, kube_check, affected_nodes_status)
                        rollback_data["node_based_zone"] = self.node_based_zone(scenario_config, kubecli)
                        affected_nodes_status = self.cloud_object.affected_nodes_status
                        scenario_telemetry.affected_nodes.extend(affected_nodes_status.affected_nodes)
                    else:
                        logging.error(
                            "ZoneOutageScenarioPlugin Cloud type %s is not currently supported for "
                            "zone outage scenarios" % cloud_type
                        )
                        return 1
                rollback_data["scenario_config"] = scenario_config
                rollback_payload = base64.b64encode(json.dumps(rollback_data).encode('utf-8')).decode('utf-8')
                RollbackCallable(
                    self.rollback_zone_outage,
                    RollbackContent(
                        resource_identifier=rollback_payload,
                        namespace=None,
                    ),
                )
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

    def network_based_zone(self, scenario_config: dict[str, any]) -> dict[dict[str, any], dict[str, any]]:
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

        return {
            "acl_ids_created": acl_ids_created,
            "ids": ids,
        }

    def get_scenario_types(self) -> list[str]:
        return ["zone_outages_scenarios"]
    
    @staticmethod
    def rollback_zone_outage(rollback_content: RollbackContent, lib_telemetry: KrknTelemetryOpenshift):
        try:
            import base64 # noqa
            import json # noqa
            rollback_data = json.loads(base64.b64decode(rollback_content.resource_identifier.encode('utf-8')).decode('utf-8'))
            scenario_config = rollback_data["scenario_config"]
            cloud_object = rollback_data["cloud_object"]
            cloud_type = scenario_config["cloud_type"]
            if cloud_type.lower() == "aws":
                ZoneOutageScenarioPlugin.rollback_aws_zone_outage(cloud_object, rollback_data["network_based_zone"], lib_telemetry)
            elif cloud_type.lower() == "gcp":
                ZoneOutageScenarioPlugin.rollback_gcp_zone_outage(cloud_object, rollback_data["network_based_zone"], lib_telemetry)
            else:
                logging.error(f"Unsupported cloud type for rollback: {cloud_type}")
        except Exception as e:
            logging.error(f"Failed to rollback zone outage: {e}")
    
    @staticmethod
    def rollback_aws_zone_outage(cloud_object: AWS, network_based_zone: dict[str, any], lib_telemetry: KrknTelemetryOpenshift):
        try:
            ids = network_based_zone["ids"]
            acl_ids_created = network_based_zone["acl_ids_created"]
            # replace the applied acl with the previous acl in use
            for new_association_id, original_acl_id in ids.items():
                cloud_object.replace_network_acl_association(
                    new_association_id, original_acl_id
                )
            logging.info("Replaced the applied ACL with the previous ACL in use")
            for acl_id in acl_ids_created:
                cloud_object.delete_network_acl(acl_id)
            logging.info("Deleted the network ACLs created for the run")
            logging.info("Zone outage rollback completed successfully")
        except Exception as e:
            logging.error(f"Failed to rollback AWS zone outage: {e}")

    @staticmethod
    def rollback_gcp_zone_outage(cloud_object: gcp_node_scenarios, network_based_zone: dict[str, any], lib_telemetry: KrknTelemetryOpenshift):
        try:
            pass
        except Exception as e:
            logging.error(f"Failed to rollback GCP zone outage: {e}")