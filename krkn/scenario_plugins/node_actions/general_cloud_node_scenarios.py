import logging
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNodeStatus

class GENERAL:
    def __init__(self):
        pass


# krkn_lib
class general_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes, node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.general = GENERAL()
        self.node_action_kube_check = node_action_kube_check

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        logging.info(
            "Node start is not set up yet for this cloud type, "
            "no action is going to be taken"
        )

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout, poll_interval):
        logging.info(
            "Node stop is not set up yet for this cloud type,"
            " no action is going to be taken"
        )

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout, poll_interval):
        logging.info(
            "Node termination is not set up yet for this cloud type, "
            "no action is going to be taken"
        )

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout, soft_reboot=False):
        logging.info(
            "Node reboot is not set up yet for this cloud type,"
            " no action is going to be taken"
        )
