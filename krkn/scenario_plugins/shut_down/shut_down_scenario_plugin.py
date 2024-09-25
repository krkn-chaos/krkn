import logging
import time
from multiprocessing.pool import ThreadPool

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn import cerberus
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.node_actions.aws_node_scenarios import AWS
from krkn.scenario_plugins.node_actions.az_node_scenarios import Azure
from krkn.scenario_plugins.node_actions.gcp_node_scenarios import GCP
from krkn.scenario_plugins.node_actions.openstack_node_scenarios import OPENSTACKCLOUD


class ShutDownScenarioPlugin(AbstractScenarioPlugin):
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
                shut_down_config_yaml = yaml.full_load(f)
                shut_down_config_scenario = shut_down_config_yaml[
                    "cluster_shut_down_scenario"
                ]
                start_time = int(time.time())
                self.cluster_shut_down(
                    shut_down_config_scenario, lib_telemetry.get_lib_kubernetes()
                )
                end_time = int(time.time())
                cerberus.publish_kraken_status(krkn_config, [], start_time, end_time)
                return 0
        except Exception as e:
            logging.error(
                f"ShutDownScenarioPlugin scenario {scenario} failed with exception: {e}"
            )
            return 1

    def multiprocess_nodes(self, cloud_object_function, nodes, processes=0):
        try:
            # pool object with number of element

            if processes == 0:
                pool = ThreadPool(processes=len(nodes))
            else:
                pool = ThreadPool(processes=processes)
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
    def cluster_shut_down(self, shut_down_config, kubecli: KrknKubernetes):
        runs = shut_down_config["runs"]
        shut_down_duration = shut_down_config["shut_down_duration"]
        cloud_type = shut_down_config["cloud_type"]
        timeout = shut_down_config["timeout"]
        processes = 0
        if cloud_type.lower() == "aws":
            cloud_object = AWS()
        elif cloud_type.lower() == "gcp":
            cloud_object = GCP()
            processes = 1
        elif cloud_type.lower() == "openstack":
            cloud_object = OPENSTACKCLOUD()
        elif cloud_type.lower() in ["azure", "az"]:
            cloud_object = Azure()
        else:
            logging.error(
                "Cloud type %s is not currently supported for cluster shut down"
                % cloud_type
            )

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
            self.multiprocess_nodes(cloud_object.stop_instances, node_id, processes)
            stopped_nodes = stopping_nodes.copy()
            while len(stopping_nodes) > 0:
                for node in stopping_nodes:
                    if type(node) is tuple:
                        node_status = cloud_object.wait_until_stopped(
                            node[1], node[0], timeout
                        )
                    else:
                        node_status = cloud_object.wait_until_stopped(node, timeout)

                    # Only want to remove node from stopping list
                    # when fully stopped/no error
                    if node_status:
                        stopped_nodes.remove(node)

                stopping_nodes = stopped_nodes.copy()

            logging.info(
                "Shutting down the cluster for the specified duration: %s"
                % shut_down_duration
            )
            time.sleep(shut_down_duration)
            logging.info("Restarting the nodes")
            restarted_nodes = set(node_id)
            self.multiprocess_nodes(cloud_object.start_instances, node_id, processes)
            logging.info("Wait for each node to be running again")
            not_running_nodes = restarted_nodes.copy()
            while len(not_running_nodes) > 0:
                for node in not_running_nodes:
                    if type(node) is tuple:
                        node_status = cloud_object.wait_until_running(
                            node[1], node[0], timeout
                        )
                    else:
                        node_status = cloud_object.wait_until_running(node, timeout)
                    if node_status:
                        restarted_nodes.remove(node)
                not_running_nodes = restarted_nodes.copy()
            logging.info("Waiting for 150s to allow cluster component initialization")
            time.sleep(150)

            logging.info("Successfully injected cluster_shut_down scenario!")

    def get_scenario_type(self) -> str:
        return "cluster_shut_down_scenarios"
