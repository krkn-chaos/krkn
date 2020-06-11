import yaml
import logging


def read_file_return_json(node_scenario_files):
    node_scenarios = []
    for scenario_file in node_scenario_files:
        with open(scenario_file, 'r') as f:
            scenario_config = yaml.full_load(f)
            # could do checking of yaml here
            node_scenarios.append(scenario_config)
    logging.info('node scenarios ' + str(node_scenarios))
    return node_scenarios
