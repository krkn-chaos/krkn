"""
Kubernetes functions for pod_network_outage scenario plugin.

This module provides setup functions specific to the pod_network_outage scenario
and imports common functions from the shared module.
"""

from kubernetes import config, client

# Import common functions from shared module
from krkn.scenario_plugins.native.common.kubernetes_utils import (
    create_job,
    delete_pod,
    create_pod,
    exec_cmd_in_pod,
    get_job_status,
    get_pod_log,
    read_pod,
    delete_job,
    list_ready_nodes,
    get_node,
    list_pods,
)


def setup_kubernetes(kubeconfig_path) -> client.ApiClient:
    """
    Sets up the Kubernetes client.
    
    Returns an ApiClient instance.
    """
    if kubeconfig_path is None:
        kubeconfig_path = config.KUBE_CONFIG_DEFAULT_LOCATION
    client_config = config.load_kube_config(kubeconfig_path)
    return client.ApiClient(client_config)
