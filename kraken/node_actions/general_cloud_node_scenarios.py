import logging
from kraken.node_actions.abstract_node_scenarios import abstract_node_scenarios


class GENERAL:
    def __init__(self):
        pass


class general_node_scenarios(abstract_node_scenarios):
    def __init__(self):
        self.general = GENERAL()

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout):
        logging.info("Node start is not set up yet for this cloud type, " "no action is going to be taken")

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout):
        logging.info("Node stop is not set up yet for this cloud type," " no action is going to be taken")

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout):
        logging.info("Node termination is not set up yet for this cloud type, " "no action is going to be taken")

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout):
        logging.info("Node reboot is not set up yet for this cloud type," " no action is going to be taken")
