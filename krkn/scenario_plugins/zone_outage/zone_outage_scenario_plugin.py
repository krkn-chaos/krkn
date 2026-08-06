# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn_lib.utils import get_yaml_item_value
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator

from krkn.scenario_plugins.node_actions.aws_node_scenarios import AWS
from krkn.scenario_plugins.node_actions.gcp_node_scenarios import gcp_node_scenarios
from krkn.scenario_plugins.node_actions.az_node_scenarios import Azure


class ZoneOutageScenarioPlugin(AbstractScenarioPlugin):
    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario, "r") as f:
                zone_outage_config_yaml = yaml.safe_load(f)
                scenario_config = zone_outage_config_yaml["zone_outage"]
                cloud_type = scenario_config["cloud_type"]
                kube_check = get_yaml_item_value(scenario_config, "kube_check", True)
                start_time = int(time.time())
                if cloud_type.lower() == "aws":
                    self.cloud_object = AWS()
                    result = self.network_based_zone(scenario_config)
                    if result != 0:
                        return 1
                elif cloud_type.lower() in ["azure", "az"]:
                    self.cloud_object = Azure()
                    result = self.network_based_zone_azure(scenario_config)
                    if result != 0:
                        return result
                else:
                    kubecli = lib_telemetry.get_lib_kubernetes()
                    if cloud_type.lower() == "gcp":
                        affected_nodes_status = AffectedNodeStatus()
                        self.cloud_object = gcp_node_scenarios(kubecli, kube_check, affected_nodes_status)
                        result = self.node_based_zone(scenario_config, kubecli)
                        if result != 0:
                            return result
                        affected_nodes_status = self.cloud_object.affected_nodes_status
                        scenario_telemetry.affected_nodes.extend(affected_nodes_status.affected_nodes)
                    else:
                        logging.error(
                            "ZoneOutageScenarioPlugin Cloud type %s is not currently supported for "
                            "zone outage scenarios" % cloud_type
                        )
                        return 1

        except (RuntimeError, Exception) as e:
            logging.error(
                f"ZoneOutageScenarioPlugin scenario {scenario} failed with exception: {e}"
            )
            return 1
        else:
            return 0

    def node_based_zone(self, scenario_config: dict[str, any], kubecli: KrknKubernetes):
        zone = scenario_config["zone"]
        duration = get_yaml_item_value(scenario_config, "duration", 60)
        timeout = get_yaml_item_value(scenario_config, "timeout", 180)
        kube_check = get_yaml_item_value(scenario_config, "kube_check", True)
        label_selector = f"topology.kubernetes.io/zone={zone}"
        try:
            # get list of nodes in zone/region
            nodes = kubecli.list_killable_nodes(label_selector)

            # set rollback callable before stopping nodes
            rollback_data = {
                "nodes": nodes,
                "timeout": timeout,
                "kube_check": kube_check,
            }
            encoded = base64.b64encode(
                json.dumps(rollback_data).encode("utf-8")
            ).decode("utf-8")
            self.rollback_handler.set_rollback_callable(
                self.rollback_gcp_zone_outage,
                RollbackContent(resource_identifier=encoded),
            )

            # stop nodes in parallel
            pool = ThreadPool(processes=len(nodes))
            pool.starmap(
                self.cloud_object.node_stop_scenario,
                zip(repeat(1), nodes, repeat(timeout), repeat(None)),
            )
            pool.close()

            logging.info(
                "Waiting for the specified duration " "in the config: %s" % duration
            )
            time.sleep(duration)

            # start nodes in parallel
            pool = ThreadPool(processes=len(nodes))
            pool.starmap(
                self.cloud_object.node_start_scenario,
                zip(repeat(1), nodes, repeat(timeout), repeat(None)),
            )
            pool.close()
        except Exception as e:
            logging.info(
                f"Node based zone outage scenario failed with exception: {e}"
            )
            return 1
        else:
            return 0

    @staticmethod
    def rollback_gcp_zone_outage(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        """Rollback function to restart stopped nodes after a GCP zone outage
        scenario failure.

        :param rollback_content: Rollback content containing encoded node
            list and config.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for
            Kubernetes operations.
        """
        try:
            import json
            import base64
            from krkn_lib.models.k8s import AffectedNodeStatus
            from krkn.scenario_plugins.node_actions.gcp_node_scenarios import (
                gcp_node_scenarios,
            )

            decoded = base64.b64decode(
                rollback_content.resource_identifier.encode("utf-8")
            ).decode("utf-8")
            rollback_data = json.loads(decoded)
            nodes = rollback_data["nodes"]
            timeout = rollback_data["timeout"]
            kube_check = rollback_data["kube_check"]

            kubecli = lib_telemetry.get_lib_kubernetes()
            affected_nodes_status = AffectedNodeStatus()
            cloud_object = gcp_node_scenarios(
                kubecli, kube_check, affected_nodes_status
            )

            logging.info(
                "Rolling back GCP zone outage: starting %d stopped nodes"
                % len(nodes)
            )
            for node in nodes:
                try:
                    cloud_object.node_start_scenario(1, node, timeout, None)
                except Exception as node_error:
                    logging.error(
                        "Failed to start node %s during rollback: %s"
                        % (node, node_error)
                    )
            logging.info("GCP zone outage rollback completed.")
        except Exception as e:
            logging.error("Failed to rollback GCP zone outage: %s" % e)
            raise

    def network_based_zone_azure(self, scenario_config: dict[str, any]) -> int:
        chaos_nsg_id = None
        resource_group = None
        vnet_name = None
        subnet_name = None
        nsg_name = None
        original_nsg_id = None
        try:
            resource_group = scenario_config["resource_group"]
            vnet_name = scenario_config["vnet_name"]
            subnet_name = scenario_config["subnet_name"]
            duration = get_yaml_item_value(scenario_config, "duration", 60)
            location = scenario_config.get("location")
            nsg_prefix = scenario_config.get("nsg_name_prefix", "chaos-zone-deny")

            if not location:
                location = self.cloud_object.get_subnet_location(resource_group, vnet_name, subnet_name)

            nsg_name = f"{nsg_prefix}-{subnet_name}"
            logging.info(
                f"Starting Azure network-based zone outage on subnet {subnet_name} "
                f"in VNet {vnet_name} (resource group: {resource_group})"
            )

            # Get current NSG association
            original_nsg_id = self.cloud_object.get_subnet_nsg(resource_group, vnet_name, subnet_name)

            # Set rollback callable before creating deny NSG
            rollback_data = {
                "resource_group": resource_group,
                "vnet_name": vnet_name,
                "subnet_name": subnet_name,
                "original_nsg_id": original_nsg_id,
                "nsg_name": nsg_name,
            }
            encoded = base64.b64encode(
                json.dumps(rollback_data).encode("utf-8")
            ).decode("utf-8")
            self.rollback_handler.set_rollback_callable(
                self.rollback_azure_zone_outage,
                RollbackContent(resource_identifier=encoded),
            )

            # Create deny-all security group
            chaos_nsg_id = self.cloud_object.create_subnet_deny_security_group(
                resource_group, nsg_name, location
            )

            # Associate deny NSG with target subnet
            self.cloud_object.update_subnet_nsg(
                resource_group, vnet_name, subnet_name, chaos_nsg_id
            )
            logging.info(
                f"Subnet {subnet_name} isolated with deny-all NSG {nsg_name}. "
                f"Waiting for duration of {duration} seconds."
            )
            time.sleep(duration)

            # Restore original NSG association
            self.cloud_object.update_subnet_nsg(
                resource_group, vnet_name, subnet_name, original_nsg_id
            )
            logging.info(f"Subnet {subnet_name} restored to original NSG association.")

            # Delete temporary deny NSG
            self.cloud_object.delete_security_group(resource_group, nsg_name)
            logging.info(f"Temporary chaos NSG {nsg_name} deleted successfully.")
        except Exception as e:
            logging.error(
                f"Azure network-based zone outage scenario failed with exception: {e}"
            )
            if chaos_nsg_id and resource_group and vnet_name and subnet_name:
                try:
                    self.cloud_object.update_subnet_nsg(
                        resource_group, vnet_name, subnet_name, original_nsg_id
                    )
                except Exception as restore_err:
                    logging.error(
                        f"Failed to restore original NSG during error recovery: {restore_err}"
                    )
                if nsg_name:
                    try:
                        self.cloud_object.delete_security_group(resource_group, nsg_name)
                    except Exception as del_err:
                        logging.warning(
                            f"Failed to delete chaos NSG during error recovery: {del_err}"
                        )
            return 1
        else:
            return 0

    @staticmethod
    def rollback_azure_zone_outage(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift = None,
    ):
        """Rollback function to restore subnet NSG association after an Azure zone outage failure.

        :param rollback_content: Rollback content containing encoded target IDs.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift (unused).
        """
        try:
            decoded = base64.b64decode(
                rollback_content.resource_identifier.encode("utf-8")
            ).decode("utf-8")
            rollback_data = json.loads(decoded)
            resource_group = rollback_data["resource_group"]
            vnet_name = rollback_data["vnet_name"]
            subnet_name = rollback_data["subnet_name"]
            original_nsg_id = rollback_data.get("original_nsg_id")
            nsg_name = rollback_data.get("nsg_name")

            from krkn.scenario_plugins.node_actions.az_node_scenarios import Azure
            cloud_object = Azure()
            logging.info(
                f"Rolling back Azure zone outage: restoring subnet {subnet_name} in VNet {vnet_name}"
            )
            try:
                cloud_object.update_subnet_nsg(
                    resource_group, vnet_name, subnet_name, original_nsg_id
                )
                logging.info(f"Subnet {subnet_name} restored to original NSG: {original_nsg_id}")
            except Exception as re_err:
                logging.error(
                    f"Failed to restore original NSG on subnet {subnet_name} during rollback: {re_err}"
                )

            if nsg_name:
                try:
                    cloud_object.delete_security_group(resource_group, nsg_name)
                    logging.info(f"Deleted temporary chaos NSG {nsg_name} during rollback")
                except Exception as del_err:
                    logging.warning(
                        f"Could not delete temporary chaos NSG {nsg_name} during rollback: {del_err}"
                    )

            logging.info("Azure zone outage rollback completed.")
        except Exception as e:
            logging.error(f"Failed to rollback Azure zone outage: {e}")
            raise

    def network_based_zone(self, scenario_config: dict[str, any]):
        try:
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
                self.cloud_object.replace_network_acl_association(
                    new_association_id, original_acl_id
                )
            logging.info(
                "Wating for 60 seconds to make sure " "the changes are in place"
            )
            time.sleep(60)

            # delete the network acl created for the run
            for acl_id in acl_ids_created:
                self.cloud_object.delete_network_acl(acl_id)
        except Exception as e:
            logging.error(
                f"Network based zone outage scenario failed with exception: {e}"
            )
            return 1
        
        return 0

    def get_scenario_types(self) -> list[str]:
        return ["zone_outages_scenarios"]
