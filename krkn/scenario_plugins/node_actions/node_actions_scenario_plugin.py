import json
import logging
import time
from multiprocessing.pool import ThreadPool
from itertools import repeat
import base64

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.models.k8s import AffectedNodeStatus
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value, log_exception

from krkn import cerberus, utils
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator
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
node_general = False


class NodeActionsScenarioPlugin(AbstractScenarioPlugin):
    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        with open(scenario, "r") as f:
            node_scenario_config = yaml.full_load(f)
            node_details = {}
            for idx , node_scenario in enumerate(node_scenario_config["node_scenarios"]):
                node_details[idx] = { "node_details": node_scenario , "rollback_action": ""}
                try:
                    node_scenario_object = self.get_node_scenario_object(
                        node_scenario, lib_telemetry.get_lib_kubernetes()
                    )
                    if node_scenario["actions"]:
                        for action in node_scenario["actions"]:
                            node_details[idx]["rollback_action"] = action
                            start_time = int(time.time())
                            self.inject_node_scenario(
                                action,
                                node_scenario,
                                node_scenario_object,
                                lib_telemetry.get_lib_kubernetes(),
                                scenario_telemetry,
                            )
                            end_time = int(time.time())
                            cerberus.get_status(krkn_config, start_time, end_time)
                except (RuntimeError, Exception) as e:
                    node_details[idx]["node_details"] = { "status": "failed", "error": str(e) }
                    logging.error("Node Actions exiting due to Exception %s" % e)
                    self.rollback_handler.set_rollback_callable(
                        self.rollback_node_action,
                        RollbackContent(
                            namespace=None,
                            resource_identifier=str(base64.b64encode(json.dumps(node_details[idx]).encode('utf-8')).decode('utf-8')),
                        ),
                    )
                    return 1
            return 0

    @staticmethod
    def get_node_scenario_object(node_scenario, kubecli: KrknKubernetes):
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
    def rollback_node_action(rollback_content: RollbackContent, lib_telemetry: KrknTelemetryOpenshift):
        """
        Rollback function to recover nodes that are in Stopped or NotReady states.
        
        :param rollback_content: Rollback content containing serialized node scenario details
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations
        """
        try:
            logging.info("Starting node action rollback...")
            import json # noqa
            import base64 # noqa
            rollback_data = json.loads(base64.b64decode(rollback_content.resource_identifier.encode('utf-8')).decode('utf-8'))
            node_scenario = rollback_data["node_details"]
            failed_action = rollback_data["rollback_action"]
            
            logging.info(f"Attempting rollback for failed action: {failed_action}")
            
            no_rollback_actions = [
                "node_start_scenario",
                "node_stop_scenario", 
                "node_termination_scenario",
                "node_reboot_scenario"
            ]
            
            if failed_action in no_rollback_actions:
                logging.info(f"Action {failed_action} does not require rollback. Skipping.")
                return
            
            kubecli = lib_telemetry.get_lib_kubernetes()
            
            node_name = get_yaml_item_value(node_scenario, "node_name", "")
            label_selector = get_yaml_item_value(node_scenario, "label_selector", "")
            instance_count = get_yaml_item_value(node_scenario, "instance_count", 1)
            timeout = get_yaml_item_value(node_scenario, "timeout", 300)
            
            if node_name:
                node_name_list = node_name.split(",")
                nodes = node_name_list
                logging.info(f"Target nodes by name: {nodes}")
            else:
                # Get nodes by label selector
                try:
                    nodes = common_node_functions.get_node(
                        label_selector, instance_count, kubecli
                    )
                    logging.info(f"Target nodes by label: {nodes}")
                except Exception as e:
                    logging.error(f"Could not identify target nodes: {e}")
                    # Try to get all nodes matching label (even NotReady ones)
                    nodes = []
                    all_nodes = kubecli.list_nodes()
                    for node_obj in all_nodes:
                        node_name = node_obj.metadata.name
                        if label_selector:
                            node_labels = node_obj.metadata.labels or {}
                            for label in label_selector.split(","):
                                if "=" in label:
                                    key, value = label.split("=", 1)
                                    if node_labels.get(key) == value:
                                        nodes.append(node_name)
                                        break
                    logging.info(f"Found nodes (including NotReady): {nodes}")
            
            if not nodes:
                logging.warning("No target nodes found for rollback")
                return
            
            try:

                cloud_type = node_scenario.get("cloud_type", "generic")
                node_scenario_object = NodeActionsScenarioPlugin.get_node_scenario_object(node_scenario, kubecli)
                logging.info(f"Created scenario object for cloud type: {cloud_type}")
                
            except Exception as e:
                logging.error(f"Failed to create node scenario object: {e}")
                return
            
            # Check each node state and recover
            for node in nodes:
                try:
                    logging.info(f"Checking state of node: {node}")
                    
                    # Check Kubernetes node status
                    try:
                        node_info = kubecli.get_node_info(node)
                        node_ready = False
                        
                        if node_info and node_info.status and node_info.status.conditions:
                            for condition in node_info.status.conditions:
                                if condition.type == "Ready":
                                    node_ready = (condition.status == "True")
                                    break
                        
                        logging.info(f"Node {node} Kubernetes Ready state: {node_ready}")
                        
                        if node_ready:
                            logging.info(f"Node {node} is already in Ready state. No recovery needed.")
                            continue
                        
                        # Node is NotReady - attempt recovery
                        logging.info(f"Node {node} is NotReady. Attempting to recover...")
                        
                        # For Docker/Kind and generic scenarios, try reboot
                        if cloud_type in ["docker", "generic"]:
                            logging.info(f"Attempting to restart kubelet on node {node}")
                            try:
                                # Try restart kubelet first (less invasive)
                                node_scenario_object.restart_kubelet_scenario(1, node, timeout)
                                logging.info(f"Kubelet restart initiated for node {node}")
                                
                                # Wait for node to become ready
                                common_node_functions.wait_for_ready_status(node, timeout, kubecli)
                                logging.info(f"Node {node} successfully recovered to Ready state")
                                
                            except Exception as restart_error:
                                logging.warning(f"Kubelet restart failed, trying node reboot: {restart_error}")
                                try:
                                    node_scenario_object.node_reboot_scenario(1, node, timeout, False)
                                    logging.info(f"Node reboot initiated for node {node}")
                                    common_node_functions.wait_for_ready_status(node, timeout, kubecli)
                                    logging.info(f"Node {node} successfully recovered after reboot")
                                except Exception as reboot_error:
                                    logging.error(f"Failed to recover node {node} via reboot: {reboot_error}")
                        else:
                            # For other cloud types, try to start the node first
                            logging.info(f"Attempting to start node {node}")
                            try:
                                node_scenario_object.node_start_scenario(1, node, timeout)
                                common_node_functions.wait_for_ready_status(node, timeout, kubecli)
                                logging.info(f"Node {node} successfully started and ready")
                            except Exception as start_error:
                                logging.warning(f"Node start failed, trying reboot: {start_error}")
                                node_scenario_object.node_reboot_scenario(1, node, timeout, False)
                                common_node_functions.wait_for_ready_status(node, timeout, kubecli)
                                logging.info(f"Node {node} successfully recovered after reboot")
                        
                    except Exception as node_check_error:
                        logging.error(f"Failed to check/recover node {node}: {node_check_error}")
                        continue
                        
                except Exception as node_error:
                    logging.error(f"Error during rollback for node {node}: {node_error}")
                    continue
            
            logging.info("Node action rollback completed")
            
        except json.JSONDecodeError as json_error:
            logging.error(f"Failed to parse rollback content: {json_error}")
        except Exception as e:
            logging.error(f"Node action rollback failed with exception: {e}")
            import traceback
            logging.error(traceback.format_exc())
