import sys
import time
import logging
import kraken.kubernetes.client as kubecli
import kraken.node_actions.common_node_functions as nodeaction
from kraken.node_actions.abstract_node_scenarios import abstract_node_scenarios
from googleapiclient import discovery
from oauth2client.client import GoogleCredentials
import kraken.invoke.command as runcommand


class GCP:
    def __init__(self):

        self.project = runcommand.invoke("gcloud config get-value project").split("/n")[0].strip()
        logging.info("project " + str(self.project) + "!")
        credentials = GoogleCredentials.get_application_default()
        self.client = discovery.build("compute", "v1", credentials=credentials, cache_discovery=False)

    # Get the instance ID of the node
    def get_instance_id(self, node):
        zone_request = self.client.zones().list(project=self.project)
        while zone_request is not None:
            zone_response = zone_request.execute()
            for zone in zone_response["items"]:
                instances_request = self.client.instances().list(project=self.project, zone=zone["name"])
                while instances_request is not None:
                    instance_response = instances_request.execute()
                    if "items" in instance_response.keys():
                        for instance in instance_response["items"]:
                            if instance["name"] in node:
                                return instance["name"], zone["name"]
                    instances_request = self.client.zones().list_next(
                        previous_request=instances_request, previous_response=instance_response
                    )
            zone_request = self.client.zones().list_next(previous_request=zone_request, previous_response=zone_response)
        logging.info("no instances ")

    # Start the node instance
    def start_instances(self, zone, instance_id):
        self.client.instances().start(project=self.project, zone=zone, instance=instance_id).execute()

    # Stop the node instance
    def stop_instances(self, zone, instance_id):
        self.client.instances().stop(project=self.project, zone=zone, instance=instance_id).execute()

    # Start the node instance
    def suspend_instances(self, zone, instance_id):
        self.client.instances().suspend(project=self.project, zone=zone, instance=instance_id).execute()

    # Terminate the node instance
    def terminate_instances(self, zone, instance_id):
        self.client.instances().delete(project=self.project, zone=zone, instance=instance_id).execute()

    # Reboot the node instance
    def reboot_instances(self, zone, instance_id):
        response = self.client.instances().reset(project=self.project, zone=zone, instance=instance_id).execute()
        logging.info("response reboot " + str(response))

    # Get instance status
    def get_instance_status(self, zone, instance_id, expected_status, timeout):
        # statuses: PROVISIONING, STAGING, RUNNING, STOPPING, SUSPENDING, SUSPENDED, REPAIRING,
        # and TERMINATED.
        i = 0
        sleeper = 5
        while i <= timeout:
            instStatus = self.client.instances().get(project=self.project, zone=zone, instance=instance_id).execute()
            logging.info("Status of vm " + str(instStatus["status"]))
            if instStatus["status"] == expected_status:
                return True
            time.sleep(sleeper)
            i += sleeper
        logging.error("Status of %s was not %s in a")

    # Wait until the node instance is suspended
    def wait_until_suspended(self, zone, instance_id, timeout):
        self.get_instance_status(zone, instance_id, "SUSPENDED", timeout)

    # Wait until the node instance is running
    def wait_until_running(self, zone, instance_id, timeout):
        self.get_instance_status(zone, instance_id, "RUNNING", timeout)

    # Wait until the node instance is stopped
    def wait_until_stopped(self, zone, instance_id, timeout):
        self.get_instance_status(zone, instance_id, "TERMINATED", timeout)

    # Wait until the node instance is terminated
    def wait_until_terminated(self, zone, instance_id, timeout):
        try:
            i = 0
            sleeper = 5
            while i <= timeout:
                instStatus = (
                    self.client.instances().get(project=self.project, zone=zone, instance=instance_id).execute()
                )
                logging.info("Status of vm " + str(instStatus["status"]))
                time.sleep(sleeper)
        except Exception as e:
            logging.info("here " + str(e))
            return True


class gcp_node_scenarios(abstract_node_scenarios):
    def __init__(self):
        self.gcp = GCP()

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_start_scenario injection")
                instance_id, zone = self.gcp.get_instance_id(node)
                logging.info("Starting the node %s with instance ID: %s " % (node, instance_id))
                self.gcp.start_instances(zone, instance_id)
                self.gcp.wait_until_running(zone, instance_id, timeout)
                nodeaction.wait_for_ready_status(node, timeout)
                logging.info("Node with instance ID: %s is in running state" % instance_id)
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following " "exception: %s. Test Failed" % (e)
                )
                logging.error("node_start_scenario injection failed!")
                sys.exit(1)

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout):
        logging.info("stop scenario")
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_stop_scenario injection")
                instance_id, zone = self.gcp.get_instance_id(node)
                logging.info("Stopping the node %s with instance ID: %s " % (node, instance_id))
                self.gcp.stop_instances(zone, instance_id)
                self.gcp.wait_until_stopped(zone, instance_id, timeout)
                logging.info("Node with instance ID: %s is in stopped state" % instance_id)
                nodeaction.wait_for_unknown_status(node, timeout)
            except Exception as e:
                logging.error("Failed to stop node instance. Encountered following exception: %s. " "Test Failed" % (e))
                logging.error("node_stop_scenario injection failed!")
                sys.exit(1)

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_termination_scenario injection")
                instance_id, zone = self.gcp.get_instance_id(node)
                logging.info("Terminating the node %s with instance ID: %s " % (node, instance_id))
                self.gcp.terminate_instances(zone, instance_id)
                self.gcp.wait_until_terminated(zone, instance_id, timeout)
                for _ in range(timeout):
                    if node not in kubecli.list_nodes():
                        break
                    time.sleep(1)
                if node in kubecli.list_nodes():
                    raise Exception("Node could not be terminated")
                logging.info("Node with instance ID: %s has been terminated" % instance_id)
                logging.info("node_termination_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to terminate node instance. Encountered following exception:" " %s. Test Failed" % e
                )
                logging.error("node_termination_scenario injection failed!")
                sys.exit(1)

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_reboot_scenario injection")
                instance_id, zone = self.gcp.get_instance_id(node)
                logging.info("Rebooting the node %s with instance ID: %s " % (node, instance_id))
                self.gcp.reboot_instances(zone, instance_id)
                nodeaction.wait_for_ready_status(node, timeout)
                logging.info("Node with instance ID: %s has been rebooted" % instance_id)
                logging.info("node_reboot_scenario has been successfuly injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:" " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")
                sys.exit(1)
