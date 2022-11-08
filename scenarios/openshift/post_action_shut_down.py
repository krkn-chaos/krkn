#!/usr/bin/env python3
import subprocess
import logging
import time
import yaml


def run(cmd):
    out = ""
    try:
        output = subprocess.Popen(
            cmd, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        (out, err) = output.communicate()
    except Exception as e:
        logging.info("Failed to run %s, error: %s" % (cmd, e))
    return out


# Get cluster operators and return yaml
def get_cluster_operators():
    operators_status = run("kubectl get co -o yaml")
    status_yaml = yaml.safe_load(operators_status, Loader=yaml.FullLoader)
    return status_yaml


# Monitor cluster operators
def monitor_cluster_operator(cluster_operators):
    failed_operators = []
    for operator in cluster_operators["items"]:
        # loop through the conditions in the status section to find the dedgraded condition
        if "status" in operator.keys() and "conditions" in operator["status"].keys():
            for status_cond in operator["status"]["conditions"]:
                # if the degraded status is not false, add it to the failed operators to return
                if status_cond["type"] == "Degraded" and status_cond["status"] != "False":
                    failed_operators.append(operator["metadata"]["name"])
                    break
        else:
            logging.info("Can't find status of " + operator["metadata"]["name"])
            failed_operators.append(operator["metadata"]["name"])
    # return False if there are failed operators else return True
    return failed_operators


wait_duration = 10
timeout = 900
counter = 0

counter = 0
co_yaml = get_cluster_operators()
failed_operators = monitor_cluster_operator(co_yaml)
while len(failed_operators) > 0:
    time.sleep(wait_duration)
    co_yaml = get_cluster_operators()
    failed_operators = monitor_cluster_operator(co_yaml)
    if counter >= timeout:
        print("Cluster operators are still degraded after " + str(timeout) + "seconds")
        print("Degraded operators " + str(failed_operators))
        exit(1)
    counter += wait_duration

not_ready = run("oc get nodes --no-headers | grep 'NotReady' | wc -l").rstrip()
while int(not_ready) > 0:
    time.sleep(wait_duration)
    not_ready = run("oc get nodes --no-headers | grep 'NotReady' | wc -l").rstrip()
    if counter >= timeout:
        print("Nodes are still not ready after " + str(timeout) + "seconds")
        exit(1)
    counter += wait_duration

worker_nodes = run("oc get nodes --no-headers | grep worker | egrep -v NotReady | awk '{print $1}'").rstrip()
print("Worker nodes list \n" + str(worker_nodes))
master_nodes = run("oc get nodes --no-headers | grep master | egrep -v NotReady | awk '{print $1}'").rstrip()
print("Master nodes list \n" + str(master_nodes))
infra_nodes = run("oc get nodes --no-headers | grep infra | egrep -v NotReady | awk '{print $1}'").rstrip()
print("Infra nodes list \n" + str(infra_nodes))
