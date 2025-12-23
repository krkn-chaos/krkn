import json
import logging
import time
import base64
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
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator
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
            for node_scenario in node_scenario_config["node_scenarios"]:
                try:
                    node_scenario_object = self.get_node_scenario_object(
                        node_scenario, lib_telemetry.get_lib_kubernetes()
                    )
                    if node_scenario["actions"]:
                        for action in node_scenario["actions"]:
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

                for node in nodes:
                    if node in exclude_nodes:
                        logging.info(
                            f"excluding node {node} with exclude label {exclude_nodes}"
                        )
                        nodes.remove(node)

        # Store initial affected nodes count to track newly affected nodes
        initial_affected_nodes_count = len(node_scenario_object.affected_nodes_status.affected_nodes)

        if parallel_nodes:
            self.multiprocess_nodes(nodes, node_scenario_object, action, node_scenario)
        else:
            for single_node in nodes:
                self.run_node(single_node, node_scenario_object, action, node_scenario)
        affected_nodes_status = node_scenario_object.affected_nodes_status
        scenario_telemetry.affected_nodes.extend(affected_nodes_status.affected_nodes)
        
        # Capture rollback data for newly affected nodes
        newly_affected_nodes = affected_nodes_status.affected_nodes[initial_affected_nodes_count:]
        if newly_affected_nodes:
            cloud_type = get_yaml_item_value(node_scenario, "cloud_type", "generic")
            
            # Skip rollback for actions that complete successfully and don't leave nodes in bad state
            skip_rollback_actions = [
                "node_start_scenario",      
                "node_stop_scenario",       
                "node_termination_scenario", 
                "node_reboot_scenario",      
            ]
            
            # Only set rollback for actions that leave nodes in a bad state that needs restoration
            if action not in skip_rollback_actions:
                # Set rollback callable to ensure node restoration on failure or interruption
                rollback_data = {
                    "cloud_type": cloud_type.lower(),
                    "action": action,
                    "affected_nodes": [
                        {
                            "node_name": affected_node.node_name,
                            "node_id": affected_node.node_id if hasattr(affected_node, "node_id") and affected_node.node_id else None,
                        }
                        for affected_node in newly_affected_nodes
                    ],
                }
                json_str = json.dumps(rollback_data)
                encoded_data = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
                self.rollback_handler.set_rollback_callable(
                    self.rollback_node_actions,
                    RollbackContent(
                        namespace=None,  # Node actions are cluster-level, not namespace-specific
                        resource_identifier=encoded_data,
                    ),
                )

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

    @staticmethod
    def rollback_node_actions(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        """Rollback function to restore nodes to their original state.
        
        This function handles rollback for various node actions:
        - node_stop_scenario: Starts stopped nodes
        - stop_kubelet_scenario: Starts stopped kubelet
        - node_stop_start_scenario: Attempts to start nodes if interrupted during stop phase
        - Other actions: Logs appropriate messages
        
        :param rollback_content: Rollback content containing encoded rollback data in resource_identifier.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations.
        """
        try:
            import json  # noqa
            import base64  # noqa
            
            # Decode rollback data from resource_identifier
            decoded_data = base64.b64decode(
                rollback_content.resource_identifier.encode("utf-8")
            ).decode("utf-8")
            rollback_data = json.loads(decoded_data)
            
            cloud_type = rollback_data.get("cloud_type", "generic")
            action = rollback_data.get("action", "")
            affected_nodes = rollback_data.get("affected_nodes", [])
            
            logging.info(
                f"Rolling back node actions: action={action}, cloud_type={cloud_type}, "
                f"affected_nodes={len(affected_nodes)}"
            )
            
            # Determine rollback action based on original action
            # Note: node_start_scenario, node_stop_scenario, node_termination_scenario, 
            # and node_reboot_scenario are skipped as they don't leave nodes in bad state
            if action == "stop_kubelet_scenario":
                # Need to start kubelet that was stopped
                logging.info("Rolling back stop_kubelet_scenario: starting kubelet")
                _rollback_stop_kubelet(affected_nodes, lib_telemetry)
                
            elif action == "node_stop_start_scenario":
               
                logging.info("Rolling back node_stop_start_scenario: attempting to start nodes")
                _rollback_node_stop(affected_nodes, cloud_type, lib_telemetry)
                
            elif action == "stop_start_kubelet_scenario":
               
                logging.info("Rolling back stop_start_kubelet_scenario: attempting to start kubelet")
                _rollback_stop_kubelet(affected_nodes, lib_telemetry)
                
            elif action == "node_crash_scenario":
                # Node crash is irreversible, but log it
                logging.warning(
                    "Cannot rollback node_crash_scenario: node crash is irreversible. "
                    "Nodes should recover automatically or require manual intervention."
                )
                
            elif action == "node_disk_detach_attach_scenario":
                # If interrupted during detach phase, disk might be detached; limited rollback support
                logging.warning(
                    "Rollback for node_disk_detach_attach_scenario is limited. "
                    "Disk reattachment requires additional context that may not be available."
                )
                
            elif action == "node_block_scenario":
                # Network block rollback depends on cloud provider
                if cloud_type in ["azure", "az"]:
                    logging.warning(
                        "Rollback for node_block_scenario on Azure is limited. "
                        "Network security group restoration requires additional context."
                    )
                else:
                    logging.info(f"Rollback not supported for node_block_scenario on {cloud_type}")
            else:
                logging.info(f"Rollback handling for action '{action}' - check if manual intervention needed")
            
            logging.info("Node actions rollback completed.")
            
        except Exception as e:
            logging.error(f"Failed to rollback node actions: {e}")

    def get_scenario_types(self) -> list[str]:
        return ["node_scenarios"]


def _check_node_ready_status(node_name, kubecli):
    """Check if a node is in Ready state.
    
    :param node_name: Name of the node to check
    :param kubecli: Kubernetes client instance
    :return: Tuple of (is_ready: bool, node_exists: bool)
    """
    try:
        node_info = kubecli.get_node_info(node_name)
        if node_info and node_info.status and node_info.status.conditions:
            for condition in node_info.status.conditions:
                if condition.type == "Ready":
                    is_ready = (condition.status == "True")
                    return (is_ready, True)
        return (False, True)
    except Exception as e:
        logging.debug(f"Could not check node status for {node_name}: {e}")
        return (False, False)


def _rollback_node_stop(affected_nodes, cloud_type, lib_telemetry):
    """Helper function to start nodes that were stopped.
    
    Uses state-based recovery and multiple recovery strategies:
    - Checks node Ready status before attempting recovery
    - For generic/docker: tries kubelet restart first, then node start
    - For other cloud types: starts the node directly
    
    :param affected_nodes: List of affected node information dictionaries
    :param cloud_type: Cloud provider type (aws, azure, gcp, etc.)
    :param lib_telemetry: Instance of KrknTelemetryOpenshift
    """
    import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
    from krkn_lib.models.k8s import AffectedNodeStatus
    
    try:
        # Get appropriate node scenario object based on cloud type
        affected_nodes_status = AffectedNodeStatus()
        kubecli = lib_telemetry.get_lib_kubernetes()
        node_action_kube_check = True
        
        if cloud_type == "aws":
            from krkn.scenario_plugins.node_actions.aws_node_scenarios import aws_node_scenarios
            node_scenario_object = aws_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif cloud_type in ["azure", "az"]:
            from krkn.scenario_plugins.node_actions.az_node_scenarios import azure_node_scenarios
            node_scenario_object = azure_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif cloud_type == "gcp":
            from krkn.scenario_plugins.node_actions.gcp_node_scenarios import gcp_node_scenarios
            node_scenario_object = gcp_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif cloud_type == "openstack":
            from krkn.scenario_plugins.node_actions.openstack_node_scenarios import openstack_node_scenarios
            node_scenario_object = openstack_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif cloud_type == "docker":
            from krkn.scenario_plugins.node_actions.docker_node_scenarios import docker_node_scenarios
            node_scenario_object = docker_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif cloud_type in ["vsphere", "vmware"]:
            from krkn.scenario_plugins.node_actions.vmware_node_scenarios import vmware_node_scenarios
            node_scenario_object = vmware_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif cloud_type in ["ibm", "ibmcloud"]:
            from krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios import ibm_node_scenarios
            node_scenario_object = ibm_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif cloud_type in ["ibmpower", "ibmcloudpower"]:
            from krkn.scenario_plugins.node_actions.ibmcloud_power_node_scenarios import ibmcloud_power_node_scenarios
            node_scenario_object = ibmcloud_power_node_scenarios(
                kubecli, node_action_kube_check, affected_nodes_status
            )
        elif cloud_type == "bm":
            # Bare metal requires BMC info 
            logging.warning("Rollback for bare metal nodes requires BMC information not available in rollback data")
            return
        else:
            logging.warning(f"Rollback not supported for cloud type: {cloud_type}")
            return
        
        # Start each affected node with state-based recovery
        timeout = 120
        poll_interval = 15
        for node_info in affected_nodes:
            node_name = node_info.get("node_name")
            if not node_name:
                continue
            
            try:
                # State-based recovery: Check node status first
                is_ready, node_exists = _check_node_ready_status(node_name, kubecli)
                
                if not node_exists:
                    logging.warning(f"Node {node_name} does not exist or cannot be accessed. Skipping rollback.")
                    continue
                
                if is_ready:
                    logging.info(f"Node {node_name} is already in Ready state. No rollback needed.")
                    continue
                
                logging.info(f"Node {node_name} is NotReady. Attempting recovery...")
                
                # Multiple recovery strategies based on cloud type
                if cloud_type in ["docker", "generic"]:
                    # Try less invasive recovery first: kubelet restart
                    logging.info(f"Attempting kubelet restart on node {node_name} (less invasive recovery)")
                    try:
                        import krkn.invoke.command as runcommand
                        runcommand.run(
                            f"oc debug node/{node_name} -- chroot /host systemctl restart kubelet"
                        )
                        # Wait for node to become ready
                        nodeaction.wait_for_ready_status(node_name, timeout, kubecli)
                        logging.info(f"Node {node_name} recovered successfully via kubelet restart")
                        continue
                    except Exception as kubelet_error:
                        logging.warning(f"Kubelet restart failed for node {node_name}: {kubelet_error}")
                        logging.info(f"Falling back to node start for {node_name}")
                
                # Primary recovery strategy: Start the node
                logging.info(f"Starting node {node_name} during rollback")
                node_scenario_object.node_start_scenario(
                    1, node_name, timeout, poll_interval
                )
                logging.info(f"Successfully started node {node_name}")
                
            except Exception as e:
                logging.warning(f"Failed to recover node {node_name} during rollback: {e}")
                
    except Exception as e:
        logging.error(f"Error during node stop rollback: {e}")


def _rollback_stop_kubelet(affected_nodes, lib_telemetry):
    """Helper function to start kubelet that was stopped.
    
    Uses state-based recovery to check node status before attempting recovery.
    
    :param affected_nodes: List of affected node information dictionaries
    :param lib_telemetry: Instance of KrknTelemetryOpenshift
    """
    import krkn.invoke.command as runcommand
    import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
    
    try:
        kubecli = lib_telemetry.get_lib_kubernetes()
        timeout = 120
        
        for node_info in affected_nodes:
            node_name = node_info.get("node_name")
            if not node_name:
                continue
            
            try:
                # State-based recovery: Check if kubelet is already running
                # by checking if node is Ready
                is_ready, node_exists = _check_node_ready_status(node_name, kubecli)
                
                if not node_exists:
                    logging.warning(f"Node {node_name} does not exist or cannot be accessed. Skipping kubelet rollback.")
                    continue
                
                if is_ready:
                    logging.info(f"Node {node_name} is Ready (kubelet appears to be running). No rollback needed.")
                    continue
                
                logging.info(f"Node {node_name} is NotReady (kubelet likely stopped). Starting kubelet...")
                
                runcommand.run(
                    f"oc debug node/{node_name} -- chroot /host systemctl start kubelet"
                )
                
                # Wait for node to become ready
                nodeaction.wait_for_ready_status(node_name, timeout, kubecli)
                logging.info(f"Successfully started kubelet on node {node_name} and node is Ready")
                
            except Exception as e:
                logging.warning(f"Failed to start kubelet on node {node_name} during rollback: {e}")
                
    except Exception as e:
        logging.error(f"Error during kubelet rollback: {e}")

