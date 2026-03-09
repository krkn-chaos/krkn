import krkn.scenario_plugins.node_actions.common_node_functions as nodeaction
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
import os
import platform
import logging
import docker
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

class Docker:
    """
    Container runtime client wrapper supporting both Docker and Podman.

    This class automatically detects and connects to either Docker or Podman
    container runtimes using the Docker-compatible API. It tries multiple
    connection methods in order of preference:

    1. Docker Unix socket (unix:///var/run/docker.sock)
    2. Platform-specific Podman sockets:
       - macOS: ~/.local/share/containers/podman/machine/podman.sock
       - Linux rootful: unix:///run/podman/podman.sock
       - Linux rootless: unix:///run/user/<uid>/podman/podman.sock
    3. Environment variables (DOCKER_HOST or CONTAINER_HOST)

    The runtime type (docker/podman) is auto-detected and logged for debugging.
    Supports Kind clusters running on Podman.

    Assisted By: Claude Code
    """
    def __init__(self):
        self.client = None
        self.runtime = 'unknown'
        

        # Try multiple connection methods in order of preference
        # Supports both Docker and Podman
        connection_methods = [
            ('unix:///var/run/docker.sock', 'Docker Unix socket'),
        ]

        # Add platform-specific Podman sockets
        if platform.system() == 'Darwin':  # macOS
            # On macOS, Podman uses podman-machine with socket typically at:
            # ~/.local/share/containers/podman/machine/podman.sock
            # This is often symlinked to /var/run/docker.sock
            podman_machine_sock = os.path.expanduser('~/.local/share/containers/podman/machine/podman.sock')
            if os.path.exists(podman_machine_sock):
                connection_methods.append((f'unix://{podman_machine_sock}', 'Podman machine socket (macOS)'))
        else:  # Linux
            connection_methods.extend([
                ('unix:///run/podman/podman.sock', 'Podman Unix socket (rootful)'),
                ('unix:///run/user/{uid}/podman/podman.sock', 'Podman Unix socket (rootless)'),
            ])

        # Always try from_env as last resort
        connection_methods.append(('from_env', 'Environment variables (DOCKER_HOST/CONTAINER_HOST)'))

        for method, description in connection_methods:
            try:
                # Handle rootless Podman socket path with {uid} placeholder
                if '{uid}' in method:
                    uid = os.getuid()
                    method = method.format(uid=uid)
                    logging.info(f'Attempting to connect using {description}: {method}')

                if method == 'from_env':
                    logging.info(f'Attempting to connect using {description}')
                    self.client = docker.from_env()
                else:
                    logging.info(f'Attempting to connect using {description}: {method}')
                    self.client = docker.DockerClient(base_url=method)

                # Test the connection
                self.client.ping()

                # Detect runtime type
                try:
                    version_info = self.client.version()
                    version_str = version_info.get('Version', '')
                    if 'podman' in version_str.lower():
                        self.runtime = 'podman'
                    else:
                        self.runtime = 'docker'
                    logging.debug(f'Runtime version info: {version_str}')
                except Exception as version_err:
                    logging.warning(f'Could not detect runtime version: {version_err}')
                    self.runtime = 'unknown'

                logging.info(f'Successfully connected to {self.runtime} using {description}')

                # Log available containers for debugging
                try:
                    containers = self.client.containers.list(all=True)
                    logging.info(f'Found {len(containers)} total containers')
                    for container in containers[:5]:  # Log first 5
                        logging.debug(f'  Container: {container.name} ({container.status})')
                except Exception as list_err:
                    logging.warning(f'Could not list containers: {list_err}')

                break

            except Exception as e:
                logging.warning(f'Failed to connect using {description}: {e}')
                continue

        if self.client is None:
            error_msg = 'Failed to initialize container runtime client (Docker/Podman) with any connection method'
            logging.error(error_msg)
            logging.error('Attempted connection methods:')
            for method, desc in connection_methods:
                logging.error(f'  - {desc}: {method}')
            raise RuntimeError(error_msg)

        logging.info(f'Container runtime client initialized successfully: {self.runtime}')

    def get_container_id(self, node_name):
        """Get the container ID for a given node name."""
        container = self.client.containers.get(node_name)
        logging.info(f'Found {self.runtime} container for node {node_name}: {container.id}')
        return container.id

    # Start the node instance
    def start_instances(self, node_name):
        """Start a container instance (works with both Docker and Podman)."""
        logging.info(f'Starting {self.runtime} container for node: {node_name}')
        container = self.client.containers.get(node_name)
        container.start()
        logging.info(f'Container {container.id} started successfully')

    # Stop the node instance
    def stop_instances(self, node_name):
        """Stop a container instance (works with both Docker and Podman)."""
        logging.info(f'Stopping {self.runtime} container for node: {node_name}')
        container = self.client.containers.get(node_name)
        container.stop()
        logging.info(f'Container {container.id} stopped successfully')

    # Reboot the node instance
    def reboot_instances(self, node_name):
        """Restart a container instance (works with both Docker and Podman)."""
        logging.info(f'Restarting {self.runtime} container for node: {node_name}')
        container = self.client.containers.get(node_name)
        container.restart()
        logging.info(f'Container {container.id} restarted successfully')

    # Terminate the node instance
    def terminate_instances(self, node_name):
        """Stop and remove a container instance (works with both Docker and Podman)."""
        logging.info(f'Terminating {self.runtime} container for node: {node_name}')
        container = self.client.containers.get(node_name)
        container.stop()
        container.remove()
        logging.info(f'Container {container.id} terminated and removed successfully')


class docker_node_scenarios(abstract_node_scenarios):
    """
    Node chaos scenarios for containerized Kubernetes nodes.

    Supports both Docker and Podman container runtimes. This class provides
    methods to inject chaos into Kubernetes nodes running as containers
    (e.g., Kind clusters, Podman-based clusters).
    """
    def __init__(self, kubecli: KrknKubernetes, node_action_kube_check: bool, affected_nodes_status: AffectedNodeStatus):
        logging.info('Initializing docker_node_scenarios (supports Docker and Podman)')
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.docker = Docker()
        self.node_action_kube_check = node_action_kube_check
        logging.info(f'Node scenarios initialized successfully using {self.docker.runtime} runtime')

    # Node scenario to start the node
    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_start_scenario injection")
                container_id = self.docker.get_container_id(node)
                affected_node.node_id = container_id
                logging.info(
                    "Starting the node %s with container ID: %s " % (node, container_id)
                )
                self.docker.start_instances(node)
                if self.node_action_kube_check:
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(
                    "Node with container ID: %s is in running state" % (container_id)
                )
                logging.info("node_start_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to start node instance. Encountered following "
                    "exception: %s. Test Failed" % (e)
                )
                logging.error("node_start_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to stop the node
    def node_stop_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_stop_scenario injection")
                container_id = self.docker.get_container_id(node)
                affected_node.node_id = container_id
                logging.info(
                    "Stopping the node %s with container ID: %s " % (node, container_id)
                )
                self.docker.stop_instances(node)
                logging.info(
                    "Node with container ID: %s is in stopped state" % (container_id)
                )
                if self.node_action_kube_check:
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
            except Exception as e:
                logging.error(
                    "Failed to stop node instance. Encountered following exception: %s. "
                    "Test Failed" % (e)
                )
                logging.error("node_stop_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    # Node scenario to terminate the node
    def node_termination_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting node_termination_scenario injection")
                container_id = self.docker.get_container_id(node)
                logging.info(
                    "Terminating the node %s with container ID: %s "
                    % (node, container_id)
                )
                self.docker.terminate_instances(node)
                logging.info(
                    "Node with container ID: %s has been terminated" % (container_id)
                )
                logging.info("node_termination_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to terminate node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_termination_scenario injection failed!")
                raise e

    # Node scenario to reboot the node
    def node_reboot_scenario(self, instance_kill_count, node, timeout, soft_reboot=False):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting node_reboot_scenario injection")
                container_id = self.docker.get_container_id(node)
                logging.info(
                    "Rebooting the node %s with container ID: %s "
                    % (node, container_id)
                )
                self.docker.reboot_instances(node)
                if self.node_action_kube_check:
                    nodeaction.wait_for_unknown_status(node, timeout, self.kubecli, affected_node)
                    nodeaction.wait_for_ready_status(node, timeout, self.kubecli, affected_node)
                logging.info(
                    "Node with container ID: %s has been rebooted" % (container_id)
                )
                logging.info("node_reboot_scenario has been successfully injected!")
            except Exception as e:
                logging.error(
                    "Failed to reboot node instance. Encountered following exception:"
                    " %s. Test Failed" % (e)
                )
                logging.error("node_reboot_scenario injection failed!")
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)
