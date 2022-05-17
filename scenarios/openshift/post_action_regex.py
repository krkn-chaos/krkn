#!/usr/bin/env python3
import subprocess
import re
import sys
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import logging


# List all namespaces
def list_namespaces():
    namespaces = []
    try:
        config.load_kube_config()
        cli = client.CoreV1Api()
        ret = cli.list_namespace(pretty=True)
    except ApiException as e:
        logging.error(
            "Exception when calling \
                       CoreV1Api->list_namespaced_pod: %s\n"
            % e
        )
    for namespace in ret.items:
        namespaces.append(namespace.metadata.name)
    return namespaces


# Check if all the watch_namespaces are valid
def check_namespaces(namespaces):
    try:
        valid_namespaces = list_namespaces()
        regex_namespaces = set(namespaces) - set(valid_namespaces)
        final_namespaces = set(namespaces) - set(regex_namespaces)
        valid_regex = set()
        if regex_namespaces:
            for namespace in valid_namespaces:
                for regex_namespace in regex_namespaces:
                    if re.search(regex_namespace, namespace):
                        final_namespaces.add(namespace)
                        valid_regex.add(regex_namespace)
                        break
        invalid_namespaces = regex_namespaces - valid_regex
        if invalid_namespaces:
            raise Exception("There exists no namespaces matching: %s" % (invalid_namespaces))
        return list(final_namespaces)
    except Exception as e:
        logging.error("%s" % (e))
        sys.exit(1)


def run(cmd):
    try:
        output = subprocess.Popen(
            cmd, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        (out, err) = output.communicate()
    except Exception as e:
        logging.error("Failed to run %s, error: %s" % (cmd, e))
    return out


regex_namespace = ["openshift-.*"]
namespaces = check_namespaces(regex_namespace)
pods_running = 0
for namespace in namespaces:
    new_pods_running = run("oc get pods -n " + namespace + " | grep -c Running").rstrip()
    try:
        pods_running += int(new_pods_running)
    except Exception:
        continue
print(pods_running)
