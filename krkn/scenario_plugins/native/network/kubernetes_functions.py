"""
Kubernetes functions for network scenario plugin.

This module provides setup functions specific to the network scenario
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


def setup_kubernetes(kubeconfig_path):
    """
    Sets up the Kubernetes client.
    
    Returns a tuple of (CoreV1Api, BatchV1Api) clients.
    """

    if kubeconfig_path is None:
        kubeconfig_path = config.KUBE_CONFIG_DEFAULT_LOCATION
    config.load_kube_config(kubeconfig_path)
    cli = client.CoreV1Api()
    batch_cli = client.BatchV1Api()

    return cli, batch_cli


def create_ifb(cli, number, pod_name):
    """
    Function that creates virtual interfaces in a pod. Makes use of modprobe commands
    """

    exec_command = ['chroot', '/host', 'modprobe', 'ifb','numifbs=' + str(number)]
    resp = exec_cmd_in_pod(cli, exec_command, pod_name, 'default')

    for i in range(0, number):
        exec_command = ['chroot', '/host','ip','link','set','dev']   
        exec_command+= ['ifb' + str(i), 'up']
        resp = exec_cmd_in_pod(cli, exec_command, pod_name, 'default')


def delete_ifb(cli, pod_name):
    """
    Function that deletes all virtual interfaces in a pod. Makes use of modprobe command
    """

    exec_command = ['chroot', '/host', 'modprobe', '-r', 'ifb']
    resp = exec_cmd_in_pod(cli, exec_command, pod_name, 'default')
