import time
import logging
import google.auth
import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
from google.cloud import compute_v1
from krkn_lib.k8s import KrknKubernetes


class GCP:
    def __init__(self):
        try:
            _, self.project_id = google.auth.default()
            self.instance_client = compute_v1.InstancesClient()
        except Exception as e:
            logging.error("Error on setting up GCP connection: " + str(e))

            raise e

    # Get the instance and zone name of the node
    def get_instance_id(self, node):
        request = compute_v1.AggregatedListInstancesRequest(
            project = self.project_id
        )
        agg_list = self.instance_client.aggregated_list(request=request)
        for zone, response in agg_list:
            if response.instances:
                for instance in response.instances:
                    if instance.name in node:
                        zone_name = zone.split("/")[-1]
                        return instance.name, zone_name
        logging.info("no instances ")

    # Start the node instance
    def start_instances(self, zone, instance_name):
        try:
            request = compute_v1.StartInstanceRequest(
                instance=instance_name,
                project=self.project_id,
                zone=zone,
            )
            self.instance_client.start(request=request)
            logging.info("vm name " + str(instance_name) + " started")
        except Exception as e:
            logging.error(
                "Failed to start node instance %s. Encountered following "
                "exception: %s." % (instance_name, e)
            )

            raise RuntimeError()

    # Stop the node instance
    def stop_instances(self, zone, instance_name):
        try:
            request = compute_v1.StopInstanceRequest(
                instance=instance_name,
                project=self.project_id,
                zone=zone,
            )
            self.instance_client.stop(request=request)
            logging.info("vm name " + str(instance_name) + " stopped")
        except Exception as e:
            logging.error(
                "Failed to stop node instance %s. Encountered following "
                "exception: %s." % (instance_name, e)
            )

            raise RuntimeError()

    # Suspend the node instance
    def suspend_instances(self, zone, instance_name):
        try:
            request = compute_v1.SuspendInstanceRequest(
                instance=instance_name,
                project=self.project_id,
                zone=zone,
            )
            self.instance_client.suspend(request=request)
            logging.info("vm name " + str(instance_name) + " suspended")
        except Exception as e:
            logging.error(
                "Failed to suspend node instance %s. Encountered following "
                "exception: %s." % (instance_name, e)
            )

            raise RuntimeError()

    # Terminate the node instance
    def terminate_instances(self, zone, instance_name):
        try:
            request = compute_v1.DeleteInstanceRequest(
                instance=instance_name,
                project=self.project_id,
                zone=zone,
            )
            self.instance_client.delete(request=request)
            logging.info("vm name " + str(instance_name) + " terminated")
        except Exception as e:
            logging.error(
                "Failed to terminate node instance %s. Encountered following "
                "exception: %s." % (instance_name, e)
            )

            raise RuntimeError()

    # Reboot the node instance
    def reboot_instances(self, zone, instance_name):
        try:
            request = compute_v1.ResetInstanceRequest(
                instance=instance_name,
                project=self.project_id,
                zone=zone,
            )
            self.instance_client.reset(request=request)
            logging.info("vm name " + str(instance_name) + " rebooted")
        except Exception as e:
            logging.error(
                "Failed to reboot node instance %s. Encountered following "
                "exception: %s." % (instance_name, e)
            )

            raise RuntimeError()

    # Get instance status
    def get_instance_status(self, zone, instance_name, expected_status, timeout):
        # states: PROVISIONING, STAGING, RUNNING, STOPPING, SUSPENDING, SUSPENDED, REPAIRING,
        # and TERMINATED.
        i = 0
        sleeper = 5
        while i <= timeout:
            try:
                request = compute_v1.GetInstanceRequest(
                    instance=instance_name,
                    project=self.project_id,
                    zone=zone,
                )
                instance_status = self.instance_client.get(request=request).status
                logging.info("Status of vm " + instance_status)
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance %s. Encountered following "
                    "exception: %s." % (instance_name, e)
                )

                raise RuntimeError()

            if instance_status == expected_status:
                return True
            time.sleep(sleeper)
            i += sleeper
        logging.error(
            "Status of %s was not %s in %s seconds"
            % (instance_name, expected_status, timeout)
        )
        return False

    # Wait until the node instance is suspended
    def wait_until_suspended(self, zone, instance_name, timeout):
        return self.get_instance_status(zone, instance_name, "SUSPENDED", timeout)

    # Wait until the node instance is running
    def wait_until_running(self, zone, instance_name, timeout):
        return self.get_instance_status(zone, instance_name, "RUNNING", timeout)

    # Wait until the node instance is stopped
    def wait_until_stopped(self, zone, instance_name, timeout):
        # In GCP, the next state after STOPPING is TERMINATED
        return self.get_instance_status(zone, instance_name, "TERMINATED", timeout)

    # Wait until the node instance is terminated
    def wait_until_terminated(self, zone, instance_name, timeout):
        return self.get_instance_status(zone, instance_name, "TERMINATED", timeout)


# krkn_lib
class gcp_node_scenarios(abstract_node_scenarios):
    def __init__(self, kubecli: KrknKubernetes):
        super().__init__(kubecli)
        self.gcp = GCP()

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_start_scenario injection")
                instance_name, zone = self.gcp.get_instance_id(node)
                logging.info(
                    "Starting the node %s with instance ID: %s " % (node, instance_name)
                )
                self.gcp.start_instances(zone, instance_name)
                self.gcp.wait_until_running(zone, instance_name, timeout)
                nodeaction.wait_for_ready_status(node, timeout, self.kubecli)
                logging.info(
                    "Node with instance ID: %s is in running state" % instance_name
                )
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following "
                    "exception: %s. Test Failed" % (e)
                )
                logging.error("node_start_scenario injection failed!")

                raise RuntimeError()

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout):
        logging.info("stop scenario")
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_stop_scenario injection")
                instance_name, zone = self.gcp.get_instance_id(node)
                logging.info(
                    "Stopping the node %s with instance ID: %s " % (node, instance_name)
                )
                self.gcp.stop_instances(zone, instance_name)
                self.gcp.wait_until_stopped(zone, instance_name, timeout)
                logging.info(
                    "Node with instance ID: %s is in stopped state" % instance_name
                )
                nodeaction.wait_for_unknown_status(node, timeout, self.kubecli)
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed" % (e)
                )
                logging.error("node_stop_scenario injection failed!")

                raise RuntimeError()

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_termination_scenario injection")
                instance_name, zone = self.gcp.get_instance_id(node)
                logging.info(
                    "Terminating the node %s with instance ID: %s "
                    % (node, instance_name)
                )
                self.gcp.terminate_instances(zone, instance_name)
                self.gcp.wait_until_terminated(zone, instance_name, timeout)
                for _ in range(timeout):
                    if node not in self.kubecli.list_nodes():
                        break
                    time.sleep(1)
                if node in self.kubecli.list_nodes():
                    raise RuntimeError("Node could not be terminated")
                logging.info(
                    "Node with instance ID: %s has been terminated" % instance_name
                )
                logging.info("node_termination_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to terminate node instance. Encountered following exception:"
                    " %s. Test Failed" % e
                )
                logging.error("node_termination_scenario injection failed!")

                raise RuntimeError()

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_reboot_scenario injection")
                instance_name, zone = self.gcp.get_instance_id(node)
                logging.info(
                    "Rebooting the node %s with instance ID: %s " % (node, instance_name)
                )
                self.gcp.reboot_instances(zone, instance_name)
                nodeaction.wait_for_ready_status(node, timeout, self.kubecli)
                logging.info(
                    "Node with instance ID: %s has been rebooted" % instance_name
                )
                logging.info("node_reboot_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")

                raise RuntimeError()
