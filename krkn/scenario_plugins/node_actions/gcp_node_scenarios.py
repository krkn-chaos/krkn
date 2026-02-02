import time
import logging
import google.auth
import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
from google.cloud import compute_v1
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

class GCP:
    def __init__(self):
        try:
            _, self.project_id = google.auth.default()
            self.instance_client = compute_v1.InstancesClient()
        except Exception as e:
            logging.error("Error on setting up GCP connection: " + str(e))

            raise e

    # Get the instance of the node
    def get_node_instance(self, node):
        try:
            request = compute_v1.AggregatedListInstancesRequest(
                project = self.project_id
            )
            agg_list = self.instance_client.aggregated_list(request=request)
            for _, response in agg_list:
                if response.instances:
                    for instance in response.instances:
                        if instance.name in node:
                            return instance
            logging.info("no instances ")
        except Exception as e:
            logging.error("Error getting the instance of the node: " + str(e))

            raise e

    # Get the instance name
    def get_instance_name(self, instance):
        if instance.name:
            return instance.name

    # Get the instance zone
    def get_instance_zone(self, instance):
        if instance.zone:
            return instance.zone.split("/")[-1]

    # Get the instance zone of the node
    def get_node_instance_zone(self, node):
        instance = self.get_node_instance(node)
        if instance:
            return self.get_instance_zone(instance)

    # Get the instance name of the node
    def get_node_instance_name(self, node):
        instance = self.get_node_instance(node)
        if instance:
            return self.get_instance_name(instance)

    # Get the instance name of the node
    def get_instance_id(self, node):
        return self.get_node_instance_name(node)

    # Start the node instance
    def start_instances(self, instance_id):
        try:
            request = compute_v1.StartInstanceRequest(
                instance=instance_id,
                project=self.project_id,
                zone=self.get_node_instance_zone(instance_id),
            )
            self.instance_client.start(request=request)
            logging.info("Instance: " + str(instance_id) + " started")
        except Exception as e:
            logging.error(
                "Failed to start node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )

            raise RuntimeError()

    # Stop the node instance
    def stop_instances(self, instance_id):
        try:
            request = compute_v1.StopInstanceRequest(
                instance=instance_id,
                project=self.project_id,
                zone=self.get_node_instance_zone(instance_id),
            )
            self.instance_client.stop(request=request)
            logging.info("Instance: " + str(instance_id) + " stopped")
        except Exception as e:
            logging.error(
                "Failed to stop node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )

            raise RuntimeError()

    # Suspend the node instance
    def suspend_instances(self, instance_id):
        try:
            request = compute_v1.SuspendInstanceRequest(
                instance=instance_id,
                project=self.project_id,
                zone=self.get_node_instance_zone(instance_id),
            )
            self.instance_client.suspend(request=request)
            logging.info("Instance: " + str(instance_id) + " suspended")
        except Exception as e:
            logging.error(
                "Failed to suspend node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )

            raise RuntimeError()

    # Terminate the node instance
    def terminate_instances(self, instance_id):
        try:
            request = compute_v1.DeleteInstanceRequest(
                instance=instance_id,
                project=self.project_id,
                zone=self.get_node_instance_zone(instance_id),
            )
            self.instance_client.delete(request=request)
            logging.info("Instance: " + str(instance_id) + " terminated")
        except Exception as e:
            logging.error(
                "Failed to terminate node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )

            raise RuntimeError()

    # Reboot the node instance
    def reboot_instances(self, instance_id):
        try:
            request = compute_v1.ResetInstanceRequest(
                instance=instance_id,
                project=self.project_id,
                zone=self.get_node_instance_zone(instance_id),
            )
            self.instance_client.reset(request=request)
            logging.info("Instance: " + str(instance_id) + " rebooted")
        except Exception as e:
            logging.error(
                "Failed to reboot node instance %s. Encountered following "
                "exception: %s." % (instance_id, e)
            )

            raise RuntimeError()

    # Get instance status
    def get_instance_status(self, instance_id, expected_status, timeout):
        # states: PROVISIONING, STAGING, RUNNING, STOPPING, SUSPENDING, SUSPENDED, REPAIRING,
        # and TERMINATED.
        i = 0
        sleeper = 5
        while i <= timeout:
            try:
                request = compute_v1.GetInstanceRequest(
                    instance=instance_id,
                    project=self.project_id,
                    zone=self.get_node_instance_zone(instance_id),
                )
                instance_status = self.instance_client.get(request=request).status
                logging.info("Status of instance " + str(instance_id) + ": " + instance_status)
            except Exception as e:
                logging.error(
                    "Failed to get status of instance %s. Encountered following "
                    "exception: %s." % (instance_id, e)
                )
                raise RuntimeError()

            if instance_status == expected_status:
                logging.info('status matches, end' + str(expected_status) + str(instance_status))                
                return True
            time.sleep(sleeper)
            i += sleeper
        logging.error(
            "Status of %s was not %s in %s seconds"
            % (instance_id, expected_status, timeout)
        )
        return False

    # Wait until the node instance is suspended
    def wait_until_suspended(self, instance_id, timeout):
        return self.get_instance_status(instance_id, "SUSPENDED", timeout)

    # Wait until the node instance is running
    def wait_until_running(self, instance_id, timeout, affected_node):
        start_time = time.time()
        instance_status = self.get_instance_status(instance_id, "RUNNING", timeout)
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("running", end_time - start_time)
        return instance_status

    # Wait until the node instance is stopped
    def wait_until_stopped(self, instance_id, timeout, affected_node):
        # In GCP, the next state after STOPPING is TERMINATED
        start_time = time.time()
        instance_status = self.get_instance_status(instance_id, "TERMINATED", timeout)
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("stopped", end_time - start_time)
        return instance_status

    # Wait until the node instance is terminated
    def wait_until_terminated(self, instance_id, timeout, affected_node):
        start_time = time.time()
        instance_status =  self.get_instance_status(instance_id, "TERMINATED", timeout)
        end_time = time.time()
        if affected_node:
            affected_node.set_affected_node_status("terminated", end_time - start_time)
        return instance_status


# krkn_lib
class gcp_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes, node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.gcp = GCP()
        self.node_action_kube_check = node_action_kube_check

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_start_scenario injection")
                instance = self.gcp.get_node_instance(node)
                instance_id = self.gcp.get_instance_name(instance)
                affected_node.node_id = instance_id
                logging.info(
                    "Starting the node %s with instance ID: %s " % (node, instance_id)
                )
                self.gcp.start_instances(instance_id)
                self.gcp.wait_until_running(instance_id, timeout, affected_node)
                if self.node_action_kube_check:
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(
                    "Node with instance ID: %s is in running state" % instance_id
                )
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following "
                    "exception: %s. Test Failed" % (e)
                )
                logging.error("node_start_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_stop_scenario injection")
                instance = self.gcp.get_node_instance(node)
                instance_id = self.gcp.get_instance_name(instance)
                affected_node.node_id = instance_id
                logging.info(
                    "Stopping the node %s with instance ID: %s " % (node, instance_id)
                )
                self.gcp.stop_instances(instance_id)
                self.gcp.wait_until_stopped(instance_id, timeout, affected_node=affected_node)
                logging.info(
                    "Node with instance ID: %s is in stopped state" % instance_id
                )
                if self.node_action_kube_check:
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed" % (e)
                )
                logging.error("node_stop_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_termination_scenario injection")
                instance = self.gcp.get_node_instance(node)
                instance_id = self.gcp.get_instance_name(instance)
                affected_node.node_id = instance_id
                logging.info(
                    "Terminating the node %s with instance ID: %s "
                    % (node, instance_id)
                )
                self.gcp.terminate_instances(instance_id)
                self.gcp.wait_until_terminated(instance_id, timeout, affected_node=affected_node)
                for _ in range(timeout):
                    if node not in self.kubecli.list_nodes():
                        break
                    time.sleep(1)
                if node in self.kubecli.list_nodes():
                    raise RuntimeError("Node could not be terminated")
                logging.info(
                    "Node with instance ID: %s has been terminated" % instance_id
                )
                logging.info("node_termination_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to terminate node instance. Encountered following exception:"
                    " %s. Test Failed" % e
                )
                logging.error("node_termination_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout, soft_reboot=False):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_reboot_scenario injection")
                instance = self.gcp.get_node_instance(node)
                instance_id = self.gcp.get_instance_name(instance)
                affected_node.node_id = instance_id
                logging.info(
                    "Rebooting the node %s with instance ID: %s " % (node, instance_id)
                )
                self.gcp.reboot_instances(instance_id)
                if self.node_action_kube_check:
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
                self.gcp.wait_until_running(instance_id, timeout, affected_node)
                if self.node_action_kube_check:
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(
                    "Node with instance ID: %s has been rebooted" % instance_id
                )
                logging.info("node_reboot_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")

                raise RuntimeError()
            self.affected_nodes_status.affected_nodes.append(affected_node)
