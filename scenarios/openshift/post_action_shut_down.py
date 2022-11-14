#!/usr/bin/env python3
import logging
import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException


# Get cluster operators
def list_cluster_operators(cli):
    config.load_kube_config()
    cli = client.CustomObjectsApi()
    try:
        res = cli.list_cluster_custom_object(
            group="config.openshift.io", version="v1", plural="clusteroperators")
    except Exception as e:
        logging.error(
            "Exception when calling CustomObjectsApi->list_cluster_operators: %s\n" % (e))
        exit(1)
    return res.get("items")


def list_not_ready_nodes(cli, node_type=''):
    try:
        if node_type == '':
            nodes = cli.list_node()
        else:
            nodes = cli.list_node(
                label_selector="node-role.kubernetes.io/{0}".format(node_type))
    except ApiException as e:
        logging.error(
            "Exception when calling CoreV1Api->get_nodes: %s\n" % (e))
        exit(1)
    not_ready_nodes = []
    for node in nodes.items:
        for condition in node.status.conditions:
            if condition.type == "Ready" and condition.status == "False":
                not_ready_nodes.append(node.metadata.name)
                break
    return not_ready_nodes


# Monitor cluster operators
def list_degraded_cluster_operator(cluster_operators):
    failed_operators = []
    for operator in cluster_operators:
        # loop through the conditions in the status section to find the dedgraded condition
        if "status" in operator.keys() and "conditions" in operator["status"].keys():
            for status_cond in operator["status"]["conditions"]:
                # if the degraded status is not false, add it to the failed operators to return
                if status_cond["type"] == "Degraded" and status_cond["status"] == "True":
                    failed_operators.append(operator["metadata"]["name"])
                    break
        else:
            logging.info("Can't find status of " +
                         operator["metadata"]["name"])
            failed_operators.append(operator["metadata"]["name"])
    # return False if there are failed operators else return True
    return failed_operators


def get_degraded_operators(custom_objects_cli):
    # degraded operators
    operators = list_cluster_operators(custom_objects_cli)
    failed_operators = list_degraded_cluster_operator(operators)
    counter = 0
    while len(failed_operators) > 0:
        time.sleep(wait_duration)
        co_yaml = list_cluster_operators(custom_objects_cli)
        failed_operators = list_degraded_cluster_operator(co_yaml)
        if counter >= timeout:
            logging.error(
                "Cluster operators are still degraded after %d seconds" % (timeout))
            logging.error("Degraded operators %s" % (str(failed_operators)))
            exit(1)
        counter += wait_duration


def get_not_ready_nodes(coreV1Api_cli):
    # not ready nodes
    not_ready_nodes = list_not_ready_nodes(coreV1Api_cli)
    for node in not_ready_nodes:
        print(node)
    not_ready_len = len(not_ready_nodes)
    counter = 0
    while int(not_ready_len) > 0:
        time.sleep(wait_duration)
        not_ready_len = len(list_not_ready_nodes(coreV1Api_cli))
        if counter >= timeout:
            logging.error(
                "Nodes are still not ready after %d seconds" % (counter))
            worker_nodes = list_not_ready_nodes(coreV1Api_cli, "worker")
            logging.error("Worker nodes list %s\n" % (str(worker_nodes)))
            master_nodes = list_not_ready_nodes(coreV1Api_cli, "master")
            logging.error("Master nodes list %s\n" % (str(master_nodes)))
            infra_nodes = list_not_ready_nodes(coreV1Api_cli, "infra")
            print("Infra nodes list %s\n" % (str(infra_nodes)))
            exit(1)
        counter += wait_duration


config.load_kube_config()
custom_objects_cli = client.CustomObjectsApi()
coreV1Api_cli = client.CoreV1Api()
wait_duration = 10
timeout = 900

get_degraded_operators(custom_objects_cli)
get_not_ready_nodes(coreV1Api_cli)
