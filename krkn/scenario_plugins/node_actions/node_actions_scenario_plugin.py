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
from krkn.scenario_plugins.node_actions.vmware_node_scenarios import vmware_node_scenarios
from krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios import ibm_node_scenarios
node_general = False


class NodeActionsScenarioPlugin(AbstractScenarioPlugin):
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
                else:
                    return 0

    def get_node_scenario_object(self, node_scenario, kubecli: KrknKubernetes):
        affected_nodes_status = AffectedNodeStatus()
        if (
            "cloud_type" not in node_scenario.keys()
            or node_scenario["cloud_type"] == "generic"
        ):
            global node_general
            node_general = True
            return general_node_scenarios(kubecli, affected_nodes_status)
        if node_scenario["cloud_type"].lower() == "aws":
            return aws_node_scenarios(kubecli, affected_nodes_status)
        elif node_scenario["cloud_type"].lower() == "gcp":
            return gcp_node_scenarios(kubecli, affected_nodes_status)
        elif node_scenario["cloud_type"].lower() == "openstack":
            from krkn.scenario_plugins.node_actions.openstack_node_scenarios import (
                openstack_node_scenarios,
            )

            return openstack_node_scenarios(kubecli, affected_nodes_status)
        elif (
            node_scenario["cloud_type"].lower() == "azure"
            or node_scenario["cloud_type"].lower() == "az"
        ):
            return azure_node_scenarios(kubecli, affected_nodes_status)
        elif (
            node_scenario["cloud_type"].lower() == "alibaba"
            or node_scenario["cloud_type"].lower() == "alicloud"
        ):
            from krkn.scenario_plugins.node_actions.alibaba_node_scenarios import (
                alibaba_node_scenarios,
            )

            return alibaba_node_scenarios(kubecli, affected_nodes_status)
        elif node_scenario["cloud_type"].lower() == "bm":
            from krkn.scenario_plugins.node_actions.bm_node_scenarios import (
                bm_node_scenarios,
            )

            return bm_node_scenarios(
                node_scenario.get("bmc_info"),
                node_scenario.get("bmc_user", None),
                node_scenario.get("bmc_password", None),
                kubecli,
                affected_nodes_status
            )
        elif node_scenario["cloud_type"].lower() == "docker":
            return docker_node_scenarios(kubecli)
        elif (
            node_scenario["cloud_type"].lower() == "vsphere"
            or node_scenario["cloud_type"].lower() == "vmware"
        ):
            return vmware_node_scenarios(kubecli, affected_nodes_status)
        elif (
            node_scenario["cloud_type"].lower() == "ibm"
            or node_scenario["cloud_type"].lower() == "ibmcloud"
        ):
            return ibm_node_scenarios(kubecli, affected_nodes_status)
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
        self, action, node_scenario, node_scenario_object, kubecli: KrknKubernetes, scenario_telemetry: ScenarioTelemetry
    ):
        
        # Get the node scenario configurations for setting nodes
       
        instance_kill_count = get_yaml_item_value(node_scenario, "instance_count", 1)
        node_name = get_yaml_item_value(node_scenario, "node_name", "")
        label_selector = get_yaml_item_value(node_scenario, "label_selector", "")
        parallel_nodes = get_yaml_item_value(node_scenario, "parallel", False)
        
        # Get the node to apply the scenario
        if node_name:
            node_name_list = node_name.split(",")
            nodes = common_node_functions.get_node_by_name(node_name_list, kubecli)
        else:
            nodes = common_node_functions.get_node(
                label_selector, instance_kill_count, kubecli
            )
        
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
    
            pool.starmap(self.run_node,zip(nodes, repeat(node_scenario_object), repeat(action), repeat(node_scenario)))

            pool.close()
        except Exception as e:
            logging.info("Error on pool multiprocessing: " + str(e))


    def run_node(self, single_node, node_scenario_object, action, node_scenario):
        # Get the scenario specifics for running action nodes
        run_kill_count = get_yaml_item_value(node_scenario, "runs", 1)
        if action in ("node_stop_start_scenario", "node_disk_detach_attach_scenario"):
            duration = get_yaml_item_value(node_scenario, "duration", 120)

        timeout = get_yaml_item_value(node_scenario, "timeout", 120)
        service = get_yaml_item_value(node_scenario, "service", "")
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
                    run_kill_count, single_node, timeout
                )
            elif action == "node_stop_scenario":
                node_scenario_object.node_stop_scenario(
                    run_kill_count, single_node, timeout
                )
            elif action == "node_stop_start_scenario":
                node_scenario_object.node_stop_start_scenario(
                    run_kill_count, single_node, timeout, duration
                )
            elif action == "node_termination_scenario":
                node_scenario_object.node_termination_scenario(
                    run_kill_count, single_node, timeout
                )
            elif action == "node_reboot_scenario":
                node_scenario_object.node_reboot_scenario(
                    run_kill_count, single_node, timeout
                )
            elif action == "node_disk_detach_attach_scenario":
                node_scenario_object.node_disk_detach_attach_scenario(
                    run_kill_count, single_node, timeout, duration)
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
                        raise Exception(
                            "Helper node IP address is not provided"
                        )
                    node_scenario_object.helper_node_stop_start_scenario(
                        run_kill_count, node_scenario["helper_node_ip"], timeout
                    )
                    node_scenario_object.helper_node_service_status(
                        node_scenario["helper_node_ip"],
                        service,
                        ssh_private_key,
                        timeout,
                    )
            else:
                logging.info(
                    "There is no node action that matches %s, skipping scenario"
                    % action
                )


    def get_scenario_types(self) -> list[str]:
        return ["node_scenarios"]
