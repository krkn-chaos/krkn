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
from krkn.scenario_plugins.node_actions.ibmcloud_node_scenarios import IbmCloud
from krkn.rollback.handler import set_rollback_context_decorator
from krkn.rollback.config import RollbackContent

import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction

from krkn_lib.models.k8s import AffectedNodeStatus, AffectedNode

class ShutDownScenarioPlugin(AbstractScenarioPlugin):
    @set_rollback_context_decorator
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
                affected_nodes_status = AffectedNodeStatus()
                self.cluster_shut_down(
                    shut_down_config_scenario, lib_telemetry.get_lib_kubernetes(), affected_nodes_status
                )

                scenario_telemetry.affected_nodes = affected_nodes_status.affected_nodes
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
    def cluster_shut_down(self, shut_down_config, kubecli: KrknKubernetes, affected_nodes_status: AffectedNodeStatus):
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
        elif cloud_type.lower() in ["ibm", "ibmcloud"]:
            cloud_object = IbmCloud()
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
            affected_nodes_status.affected_nodes.append(AffectedNode(node, node_id=instance_id))
            node_id.append(instance_id)
        for _ in range(runs):
            logging.info("Starting cluster_shut_down scenario injection")
            stopping_nodes = set(node_id)
            
            # Register rollback callable before shutting down nodes
            node_ids_str = ",".join(node_id)
            rollback_content = RollbackContent(
                resource_identifier=f"{cloud_type}:{node_ids_str}"
            )
            self.rollback_handler.set_rollback_callable(
                self.rollback_shutdown_nodes,
                rollback_content
            )
            logging.info(f"Registered rollback callable for {len(node_id)} nodes on {cloud_type}")
            
            self.multiprocess_nodes(cloud_object.stop_instances, node_id, processes)
            stopped_nodes = stopping_nodes.copy()
            start_time = time.time()
            while len(stopping_nodes) > 0:
                for node in stopping_nodes:
                    affected_node = affected_nodes_status.get_affected_node_index(node)

                    if type(node) is tuple:
                        node_status = cloud_object.wait_until_stopped(
                            node[1], node[0], timeout, affected_node
                        )
                    else:
                        node_status = cloud_object.wait_until_stopped(node, timeout, affected_node)

                    # Only want to remove node from stopping list
                    # when fully stopped/no error
                    if node_status:
                        # need to add in time that is passing while waiting for other nodes to be stopped
                        affected_node.set_cloud_stopping_time(time.time() - start_time)
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
            start_time = time.time()
            logging.info("Wait for each node to be running again")
            not_running_nodes = restarted_nodes.copy()
            while len(not_running_nodes) > 0:
                for node in not_running_nodes:
                    affected_node = affected_nodes_status.get_affected_node_index(node)
                    # need to add in time that is passing while waiting for other nodes to be running

                    if type(node) is tuple:
                        node_status = cloud_object.wait_until_running(
                            node[1], node[0], timeout, affected_node
                        )
                    else:
                        node_status = cloud_object.wait_until_running(node, timeout, affected_node)
                    if node_status:
                        affected_node.set_cloud_running_time(time.time() - start_time)
                        restarted_nodes.remove(node)
                not_running_nodes = restarted_nodes.copy()

            logging.info("Waiting for 150s to allow cluster component initialization")
            time.sleep(150)

            logging.info("Successfully injected cluster_shut_down scenario!")

    def get_scenario_types(self) -> list[str]:
        return ["cluster_shut_down_scenarios"]

    @staticmethod
    def rollback_shutdown_nodes(rollback_content: RollbackContent, lib_telemetry: KrknTelemetryOpenshift):
        """
        Rollback function to restore powered-off nodes back to running state.
        
        :param rollback_content: Rollback content containing node information and cloud provider details.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations.
        """
        try:
            # Parse the rollback content to extract node and cloud information
            # Format: "cloud_type:node_id1,node_id2,node_id3"
            content_parts = rollback_content.resource_identifier.split(":", 1)
            if len(content_parts) != 2:
                logging.error(f"Invalid rollback content format: {rollback_content.resource_identifier}")
                return
            
            cloud_type = content_parts[0]
            node_ids_str = content_parts[1]
            node_ids = [node_id.strip() for node_id in node_ids_str.split(",") if node_id.strip()]
            
            if not node_ids:
                logging.warning("No node IDs found in rollback content")
                return
            
            logging.info(f"Rolling back shutdown for {len(node_ids)} nodes on {cloud_type}")
            logging.info(f"Node IDs: {node_ids}")
            
            # Initialize cloud provider
            if cloud_type.lower() == "aws":
                cloud_object = AWS()
            elif cloud_type.lower() == "gcp":
                cloud_object = GCP()
            elif cloud_type.lower() == "openstack":
                cloud_object = OPENSTACKCLOUD()
            elif cloud_type.lower() in ["azure", "az"]:
                cloud_object = Azure()
            elif cloud_type.lower() in ["ibm", "ibmcloud"]:
                cloud_object = IbmCloud()
            else:
                logging.error(f"Unsupported cloud type for rollback: {cloud_type}")
                return
            
            # Start the instances
            logging.info("Starting instances for rollback...")
            try:
                cloud_object.start_instances(node_ids)
                logging.info("Successfully initiated start for all instances")
            except Exception as e:
                logging.error(f"Failed to start instances: {e}")
                raise
            
            # Wait for instances to be running with improved error handling
            logging.info("Waiting for instances to be running...")
            timeout = 300  # 5 minutes timeout for rollback
            successful_restores = 0
            failed_restores = []
            
            for node_id in node_ids:
                try:
                    logging.info(f"Waiting for node {node_id} to be running...")
                    node_status = cloud_object.wait_until_running(node_id, timeout)
                    if node_status:
                        logging.info(f"Successfully restored node: {node_id}")
                        successful_restores += 1
                    else:
                        logging.warning(f"Timeout waiting for node {node_id} to be running")
                        failed_restores.append(node_id)
                except Exception as e:
                    logging.error(f"Error waiting for node {node_id} to be running: {e}")
                    failed_restores.append(node_id)
            
            # Log rollback summary
            if successful_restores == len(node_ids):
                logging.info(f"Rollback completed successfully for all {len(node_ids)} nodes")
            else:
                logging.warning(f"Rollback completed with issues: {successful_restores}/{len(node_ids)} nodes restored successfully")
                if failed_restores:
                    logging.warning(f"Failed to restore nodes: {failed_restores}")
            
            # Wait for cluster components to initialize after rollback
            if successful_restores > 0:
                logging.info("Waiting for cluster components to initialize after rollback...")
                time.sleep(60)  # Shorter wait for rollback scenario
            
            logging.info("Rollback of shutdown nodes completed.")
            
        except Exception as e:
            logging.error(f"Failed to rollback shutdown nodes: {e}")
            raise
