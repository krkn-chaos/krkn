#!/usr/bin/env python
import yaml
import logging
import time
from multiprocessing.pool import ThreadPool
from ..cerberus import setup as cerberus
from ..post_actions import actions as post_actions
from ..node_actions.aws_node_scenarios import AWS
from ..node_actions.openstack_node_scenarios import OPENSTACKCLOUD
from ..node_actions.az_node_scenarios import Azure
from ..node_actions.gcp_node_scenarios import GCP
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.utils.functions import log_exception

def multiprocess_nodes(cloud_object_function, nodes):
    try:
        # pool object with number of element

        pool = ThreadPool(processes=len(nodes))
        logging.info("nodes type " + str(type(nodes[0])))
        if type(nodes[0]) is tuple:
            node_id = []
            node_info = []
            for node in nodes:
                node_id.append(node[0])
                node_info.append(node[1])
            logging.info("node id " + str(node_id))
            logging.info("node info" + str(node_info))
            pool.starmap(cloud_object_function, zip(node_info, node_id))

        else:
            logging.info("pool type" + str(type(nodes)))
            pool.map(cloud_object_function, nodes)
        pool.close()
    except Exception as e:
        logging.info("Error on pool multiprocessing: " + str(e))


# Inject the cluster shut down scenario
# krkn_lib
def cluster_shut_down(shut_down_config, kubecli: KrknKubernetes):
    runs = shut_down_config["runs"]
    shut_down_duration = shut_down_config["shut_down_duration"]
    cloud_type = shut_down_config["cloud_type"]
    timeout = shut_down_config["timeout"]
    if cloud_type.lower() == "aws":
        cloud_object = AWS()
    elif cloud_type.lower() == "gcp":
        cloud_object = GCP()
    elif cloud_type.lower() == "openstack":
        cloud_object = OPENSTACKCLOUD()
    elif cloud_type.lower() in ["azure", "az"]:
        cloud_object = Azure()
    else:
        logging.error(
            "Cloud type %s is not currently supported for cluster shut down" %
            cloud_type
        )
        # removed_exit
        # sys.exit(1)
        raise RuntimeError()

    nodes = kubecli.list_nodes()
    node_id = []
    for node in nodes:
        instance_id = cloud_object.get_instance_id(node)
        node_id.append(instance_id)
    logging.info("node id list " + str(node_id))
    for _ in range(runs):
        logging.info("Starting cluster_shut_down scenario injection")
        stopping_nodes = set(node_id)
        multiprocess_nodes(cloud_object.stop_instances, node_id)
        stopped_nodes = stopping_nodes.copy()
        while len(stopping_nodes) > 0:
            for node in stopping_nodes:
                if type(node) is tuple:
                    node_status = cloud_object.wait_until_stopped(
                        node[1],
                        node[0],
                        timeout
                    )
                else:
                    node_status = cloud_object.wait_until_stopped(
                        node,
                        timeout
                    )

                # Only want to remove node from stopping list
                # when fully stopped/no error
                if node_status:
                    stopped_nodes.remove(node)

            stopping_nodes = stopped_nodes.copy()

        logging.info(
            "Shutting down the cluster for the specified duration: %s" %
            (shut_down_duration)
        )
        time.sleep(shut_down_duration)
        logging.info("Restarting the nodes")
        restarted_nodes = set(node_id)
        multiprocess_nodes(cloud_object.start_instances, node_id)
        logging.info("Wait for each node to be running again")
        not_running_nodes = restarted_nodes.copy()
        while len(not_running_nodes) > 0:
            for node in not_running_nodes:
                if type(node) is tuple:
                    node_status = cloud_object.wait_until_running(
                        node[1],
                        node[0],
                        timeout
                    )
                else:
                    node_status = cloud_object.wait_until_running(
                        node,
                        timeout
                    )
                if node_status:
                    restarted_nodes.remove(node)
            not_running_nodes = restarted_nodes.copy()
        logging.info(
            "Waiting for 150s to allow cluster component initialization"
        )
        time.sleep(150)

        logging.info("Successfully injected cluster_shut_down scenario!")

# krkn_lib

def run(scenarios_list, config, wait_duration, kubecli: KrknKubernetes, telemetry: KrknTelemetryKubernetes) -> (list[str], list[ScenarioTelemetry]):
    failed_post_scenarios = []
    failed_scenarios = []
    scenario_telemetries: list[ScenarioTelemetry] = []

    for shut_down_config in scenarios_list:
        config_path = shut_down_config
        pre_action_output = ""
        if isinstance(shut_down_config, list) :
            if len(shut_down_config) == 0:
                raise Exception("bad config file format for shutdown scenario")

            config_path = shut_down_config[0]
            if len(shut_down_config) > 1:
                pre_action_output = post_actions.run("", shut_down_config[1])

        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = config_path
        scenario_telemetry.startTimeStamp = time.time()
        telemetry.set_parameters_base64(scenario_telemetry, config_path)

        with open(config_path, "r") as f:
            shut_down_config_yaml = yaml.full_load(f)
            shut_down_config_scenario = \
                shut_down_config_yaml["cluster_shut_down_scenario"]
            start_time = int(time.time())
            try:
                cluster_shut_down(shut_down_config_scenario, kubecli)
                logging.info(
                    "Waiting for the specified duration: %s" % (wait_duration)
                )
                time.sleep(wait_duration)
                failed_post_scenarios = post_actions.check_recovery(
                    "", shut_down_config, failed_post_scenarios, pre_action_output
                )
                end_time = int(time.time())
                cerberus.publish_kraken_status(
                    config,
                    failed_post_scenarios,
                    start_time,
                    end_time
                )

            except (RuntimeError, Exception):
                log_exception(config_path)
                failed_scenarios.append(config_path)
                scenario_telemetry.exitStatus = 1
            else:
                scenario_telemetry.exitStatus = 0

            scenario_telemetry.endTimeStamp = time.time()
            scenario_telemetries.append(scenario_telemetry)

    return failed_scenarios, scenario_telemetries

