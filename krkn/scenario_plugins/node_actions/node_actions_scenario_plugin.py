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
import logging
import time
from multiprocessing.pool import ThreadPool
from itertools import repeat

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.models.k8s import AffectedNodeStatus
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value, log_exception

from krkn import cerberus, utils
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.node_actions import common_node_functions
from krkn.scenario_plugins.node_actions.aws_node_scenarios import aws_node_scenarios
from krkn.scenario_plugins.node_actions.az_node_scenarios import azure_node_scenarios
from krkn.scenario_plugins.node_actions.docker_node_scenarios import (
    docker_node_scenarios,
)
from krkn.scenario_plugins.node_actions.gcp_node_scenarios import gcp_node_scenarios
from krkn.scenario_plugins.node_actions.general_cloud_node_scenarios import (
    general_node_scenarios,
)
from krkn.scenario_plugins.node_actions.vmware_node_scenarios import (
    vmware_node_scenarios,
)
from krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios import (
    ibm_node_scenarios,
)

from krkn.scenario_plugins.node_actions.ibmcloud_power_node_scenarios import (
     ibmcloud_power_node_scenarios,
)
from krkn.rollback.handler import set_rollback_context_decorator
from krkn.rollback.config import RollbackContent
from krkn.scenario_plugins.node_actions.aws_node_scenarios import AWS
from krkn.scenario_plugins.node_actions.gcp_node_scenarios import GCP
from krkn.scenario_plugins.node_actions.az_node_scenarios import Azure
from krkn.scenario_plugins.node_actions.openstack_node_scenarios import OPENSTACKCLOUD
from krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios import IbmCloud

node_general = False


def _get_node_cloud_object(cloud_type: str):
    """Return cloud provider instance for rollback. Mirrors shut_down_scenario_plugin pattern."""
    ct = cloud_type.lower()
    if ct == "aws":
        return AWS()
    elif ct == "gcp":
        return GCP()
    elif ct == "openstack":
        return OPENSTACKCLOUD()
    elif ct in ("azure", "az"):
        return Azure()
    elif ct in ("ibm", "ibmcloud"):
        return IbmCloud()
    else:
        raise ValueError(f"Cloud type '{cloud_type}' is not supported for node outage rollback")


class NodeActionsScenarioPlugin(AbstractScenarioPlugin):
    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        with open(scenario, "r") as f:
            node_scenario_config = yaml.safe_load(f)
            for index, node_scenario in enumerate(node_scenario_config["node_scenarios"]):
                try:
                    actions = node_scenario.get("actions")
                    if not actions:
                        logging.error(
                            "NodeActionsScenarioPlugin: 'actions' must be defined and non-empty in %s node_scenarios[%s]"
                            % (scenario, index)
                        )
                        return 1
                    node_scenario_object = self.get_node_scenario_object(
                        node_scenario, lib_telemetry.get_lib_kubernetes()
                    )
                    for action in actions:
                        start_time = int(time.time())
                        self.inject_node_scenario(
                            action,
                            node_scenario,
                            node_scenario_object,
                            lib_telemetry.get_lib_kubernetes(),
                            scenario_telemetry,
                        )
                        end_time = int(time.time())
                        cerberus.get_status(start_time, end_time)
                except (RuntimeError, Exception) as e:
                    logging.error("Node Actions exiting due to Exception %s" % e)
                    return 1
            return 0

    def get_node_scenario_object(self, node_scenario, kubecli: KrknKubernetes):
        affected_nodes_status = AffectedNodeStatus()

        node_action_kube_check = get_yaml_item_value(node_scenario, "kube_check", True)
        if (
            "cloud_type" not in node_scenario.keys()
            or node_scenario["cloud_type"] == "generic"
        ):
            global node_general
            node_general = True
            return general_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        if node_scenario["cloud_type"].lower() == "aws":
            return aws_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif node_scenario["cloud_type"].lower() == "gcp":
            return gcp_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif node_scenario["cloud_type"].lower() == "openstack":
            from krkn.scenario_plugins.node_actions.openstack_node_scenarios import (
                openstack_node_scenarios,
            )

            return openstack_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif (
            node_scenario["cloud_type"].lower() == "azure"
            or node_scenario["cloud_type"].lower() == "az"
        ):
            return azure_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif (
            node_scenario["cloud_type"].lower() == "alibaba"
            or node_scenario["cloud_type"].lower() == "alicloud"
        ):
            from krkn.scenario_plugins.node_actions.alibaba_node_scenarios import (
                alibaba_node_scenarios,
            )

            return alibaba_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif node_scenario["cloud_type"].lower() == "bm":
            from krkn.scenario_plugins.node_actions.bm_node_scenarios import (
                bm_node_scenarios,
            )

            return bm_node_scenarios(
                node_scenario.get("bmc_info"),
                node_scenario.get("bmc_user", None),
                node_scenario.get("bmc_password", None),
                kubecli,
                node_action_kube_check,
                affected_nodes_status,
            )
        elif node_scenario["cloud_type"].lower() == "docker":
            return docker_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif (
            node_scenario["cloud_type"].lower() == "vsphere"
            or node_scenario["cloud_type"].lower() == "vmware"
        ):
            return vmware_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif (
            node_scenario["cloud_type"].lower() == "ibm"
            or node_scenario["cloud_type"].lower() == "ibmcloud"
        ):
            disable_ssl_verification = get_yaml_item_value(node_scenario, "disable_ssl_verification", True)
            return ibm_node_scenarios(kubecli, node_action_kube_check, affected_nodes_status, disable_ssl_verification)
        elif (
            node_scenario["cloud_type"].lower() == "ibmpower"
            or node_scenario["cloud_type"].lower() == "ibmcloudpower"
        ):
            disable_ssl_verification = get_yaml_item_value(node_scenario, "disable_ssl_verification", True)
            return ibmcloud_power_node_scenarios(kubecli, node_action_kube_check, affected_nodes_status, disable_ssl_verification)
        else:
            logging.error(
                "Cloud type "
                + node_scenario["cloud_type"]
                + " is not currently supported; "
                "try using 'generic' if wanting to stop/start kubelet or fork bomb on any "
                "cluster"
            )
            raise Exception(
                "Cloud type "
                + node_scenario["cloud_type"]
                + " is not currently supported; "
                "try using 'generic' if wanting to stop/start kubelet or fork bomb on any "
                "cluster"
            )

    def inject_node_scenario(
        self,
        action,
        node_scenario,
        node_scenario_object,
        kubecli: KrknKubernetes,
        scenario_telemetry: ScenarioTelemetry,
    ):

        # Get the node scenario configurations for setting nodes

        instance_kill_count = get_yaml_item_value(node_scenario, "instance_count", 1)
        node_name = get_yaml_item_value(node_scenario, "node_name", "")
        label_selector = get_yaml_item_value(node_scenario, "label_selector", "")
        exclude_label = get_yaml_item_value(node_scenario, "exclude_label", "")
        parallel_nodes = get_yaml_item_value(node_scenario, "parallel", False)

        # Get the node to apply the scenario
        if node_name:
            node_name_list = node_name.split(",")
            nodes = common_node_functions.get_node_by_name(node_name_list, kubecli)
        else:
            nodes = common_node_functions.get_node(
                label_selector, instance_kill_count, kubecli
            )
            if exclude_label:
                exclude_nodes = common_node_functions.get_node(
                    exclude_label, 0, kubecli
                )
                if exclude_nodes:
                    logging.info(
                        f"excluding nodes {exclude_nodes} with exclude label {exclude_label}"
                    )
                nodes = [node for node in nodes if node not in exclude_nodes]

        ROLLBACK_ACTIONS = {"node_stop_scenario", "node_termination_scenario"}
        cloud_type = node_scenario.get("cloud_type", "generic")
        if action in ROLLBACK_ACTIONS and cloud_type != "generic":
            try:
                cloud_object = _get_node_cloud_object(cloud_type)
                instance_ids = tuple(cloud_object.get_instance_id(node) for node in nodes)
                rollback_content = RollbackContent(
                    cloud_type=cloud_type,
                    instance_ids=instance_ids,
                    skip_kubernetes=True,
                )
                self.rollback_handler.set_rollback_callable(
                    NodeActionsScenarioPlugin.rollback_node_outage,
                    rollback_content,
                )
                logging.info(f"Registered rollback for {len(nodes)} nodes on {cloud_type}")
            except Exception as e:
                logging.warning(f"Could not register node outage rollback: {e}")

        # GCP api doesn't support multiprocessing calls, will only actually run 1
        if parallel_nodes:
            self.multiprocess_nodes(nodes, node_scenario_object, action, node_scenario)
        else:
            for single_node in nodes:
                self.run_node(single_node, node_scenario_object, action, node_scenario)
        affected_nodes_status = node_scenario_object.affected_nodes_status
        scenario_telemetry.affected_nodes.extend(affected_nodes_status.affected_nodes)

    def multiprocess_nodes(self, nodes, node_scenario_object, action, node_scenario):
        try:
            # pool object with number of element
            pool = ThreadPool(processes=len(nodes))

            pool.starmap(
                self.run_node,
                zip(
                    nodes,
                    repeat(node_scenario_object),
                    repeat(action),
                    repeat(node_scenario),
                ),
            )

            pool.close()
        except Exception as e:
            logging.info("Error on pool multiprocessing: " + str(e))

    def run_node(self, single_node, node_scenario_object, action, node_scenario):
        # Get the scenario specifics for running action nodes
        run_kill_count = get_yaml_item_value(node_scenario, "runs", 1)
        duration = get_yaml_item_value(node_scenario, "duration", 120)
        poll_interval = get_yaml_item_value(node_scenario, "poll_interval", 15)
        timeout = get_yaml_item_value(node_scenario, "timeout", 120)
        service = get_yaml_item_value(node_scenario, "service", "")
        soft_reboot = get_yaml_item_value(node_scenario, "soft_reboot", False)
        ssh_private_key = get_yaml_item_value(
            node_scenario, "ssh_private_key", "~/.ssh/id_rsa"
        )
        generic_cloud_scenarios = ("stop_kubelet_scenario", "node_crash_scenario")

        if node_general and action not in generic_cloud_scenarios:
            logging.info(
                "Scenario: "
                + action
                + " is not set up for generic cloud type, skipping action"
            )
        else:
            if action == "node_start_scenario":
                node_scenario_object.node_start_scenario(
                    run_kill_count, single_node, timeout, poll_interval
                )
            elif action == "node_stop_scenario":
                node_scenario_object.node_stop_scenario(
                    run_kill_count, single_node, timeout, poll_interval
                )
            elif action == "node_stop_start_scenario":
                node_scenario_object.node_stop_start_scenario(
                    run_kill_count, single_node, timeout, duration, poll_interval
                )
            elif action == "node_termination_scenario":
                node_scenario_object.node_termination_scenario(
                    run_kill_count, single_node, timeout, poll_interval
                )
            elif action == "node_reboot_scenario":
                node_scenario_object.node_reboot_scenario(
                    run_kill_count, single_node, timeout, soft_reboot
                )
            elif action == "node_disk_detach_attach_scenario":
                node_scenario_object.node_disk_detach_attach_scenario(
                    run_kill_count, single_node, timeout, duration
                )
            elif action == "stop_start_kubelet_scenario":
                node_scenario_object.stop_start_kubelet_scenario(
                    run_kill_count, single_node, timeout
                )
            elif action == "restart_kubelet_scenario":
                node_scenario_object.restart_kubelet_scenario(
                    run_kill_count, single_node, timeout
                )
            elif action == "stop_kubelet_scenario":
                node_scenario_object.stop_kubelet_scenario(
                    run_kill_count, single_node, timeout
                )
            elif action == "node_crash_scenario":
                node_scenario_object.node_crash_scenario(
                    run_kill_count, single_node, timeout
                )
            elif action == "stop_start_helper_node_scenario":
                if node_scenario["cloud_type"] != "openstack":
                    logging.error(
                        "Scenario: " + action + " is not supported for "
                        "cloud type "
                        + node_scenario["cloud_type"]
                        + ", skipping action"
                    )
                else:
                    if not node_scenario["helper_node_ip"]:
                        logging.error("Helper node IP address is not provided")
                        raise Exception("Helper node IP address is not provided")
                    node_scenario_object.helper_node_stop_start_scenario(
                        run_kill_count, node_scenario["helper_node_ip"], timeout
                    )
                    node_scenario_object.helper_node_service_status(
                        node_scenario["helper_node_ip"],
                        service,
                        ssh_private_key,
                        timeout,
                    )
            elif action == "node_block_scenario":
                node_scenario_object.node_block_scenario(
                    run_kill_count, single_node, timeout, duration
                )
            else:
                logging.info(
                    "There is no node action that matches %s, skipping scenario"
                    % action
                )

    def get_scenario_types(self) -> list[str]:
        return ["node_scenarios"]

    @staticmethod
    def rollback_node_outage(rollback_content: RollbackContent, lib_telemetry: KrknTelemetryOpenshift = None):
        """
        Restore stopped/terminated nodes. Operates independently of Kubernetes API.
        Called by execute_rollback_version_files() on scenario failure.
        """
        import time
        try:
            cloud_type = rollback_content.cloud_type
            node_ids = list(rollback_content.instance_ids or ())
            if not cloud_type or not node_ids:
                # Legacy fallback
                content_parts = rollback_content.resource_identifier.split(":", 1)
                if len(content_parts) != 2:
                    logging.error(f"Invalid rollback content: {rollback_content.resource_identifier}")
                    return
                cloud_type = content_parts[0]
                node_ids = [n.strip() for n in content_parts[1].split(",") if n.strip()]
            if not node_ids:
                logging.warning("No node IDs found in rollback content")
                return
            if cloud_type.lower() == "aws":
                from krkn.scenario_plugins.node_actions.aws_node_scenarios import AWS
                cloud_object = AWS()
            elif cloud_type.lower() == "gcp":
                from krkn.scenario_plugins.node_actions.gcp_node_scenarios import GCP
                cloud_object = GCP()
            elif cloud_type.lower() == "openstack":
                from krkn.scenario_plugins.node_actions.openstack_node_scenarios import OPENSTACKCLOUD
                cloud_object = OPENSTACKCLOUD()
            elif cloud_type.lower() in ["azure", "az"]:
                from krkn.scenario_plugins.node_actions.az_node_scenarios import Azure
                cloud_object = Azure()
            elif cloud_type.lower() in ["ibm", "ibmcloud"]:
                from krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios import IbmCloud
                cloud_object = IbmCloud()
            else:
                logging.error(f"Unsupported cloud type for rollback: {cloud_type}")
                return
            timeout = 300
            failed = []
            for node_id in node_ids:
                try:
                    logging.info(f"Starting node for rollback: {node_id}")
                    if isinstance(node_id, tuple):
                        cloud_object.start_instances(node_id[1], node_id[0])
                    else:
                        cloud_object.start_instances(node_id)
                except Exception as e:
                    logging.error(f"Failed to start {node_id}: {e}")
                    failed.append(node_id)
            for node_id in node_ids:
                if node_id in failed:
                    continue
                try:
                    if isinstance(node_id, tuple):
                        node_status = cloud_object.wait_until_running(node_id[1], node_id[0], timeout, None)
                    else:
                        node_status = cloud_object.wait_until_running(node_id, timeout, None)
                    if not node_status:
                        logging.warning(f"Timeout waiting for {node_id}")
                        failed.append(node_id)
                    else:
                        logging.info(f"Node {node_id} restored")
                except Exception as e:
                    logging.error(f"Error waiting for {node_id}: {e}")
                    failed.append(node_id)
            total = len(node_ids)
            restored = total - len(failed)
            if not failed:
                logging.info(f"Node outage rollback complete: {total}/{total} restored")
            else:
                logging.warning(f"Node outage rollback partial: {restored}/{total} restored. Failed: {failed}")
            if restored > 0:
                logging.info("Waiting 60s for cluster initialization...")
                time.sleep(60)
            logging.info("rollback_node_outage complete.")
        except Exception as e:
            logging.error(f"rollback_node_outage failed: {e}")
            raise

