#!/usr/bin/env python3
import logging
import re
import subprocess
import sys

from kubernetes import client, config
from kubernetes.client.rest import ApiException


def list_namespaces():
    """
    List all namespaces
    """
    spaces_list = []
    try:
        config.load_kube_config()
        cli = client.CoreV1Api()
        ret = cli.list_namespace(pretty=True)
    except ApiException as e:
        logging.error(
            "Exception when calling CoreV1Api->list_namespace: %s\n",
            e
        )
    for current_namespace in ret.items:
        spaces_list.append(current_namespace.metadata.name)
    return spaces_list


def check_namespaces(namespaces):
    """
    Check if all the watch_namespaces are valid
    """
    try:
        valid_namespaces = list_namespaces()
        regex_namespaces = set(namespaces) - set(valid_namespaces)
        final_namespaces = set(namespaces) - set(regex_namespaces)
        valid_regex = set()
        if regex_namespaces:
            for current_ns in valid_namespaces:
                for regex_namespace in regex_namespaces:
                    if re.search(regex_namespace, current_ns):
                        final_namespaces.add(current_ns)
                        valid_regex.add(regex_namespace)
                        break
        invalid_namespaces = regex_namespaces - valid_regex
        if invalid_namespaces:
            raise Exception(
                "There exists no namespaces matching: %s" % (
                    invalid_namespaces
                )
            )
        return list(final_namespaces)
    except Exception as e:
        logging.error(str(e))
        sys.exit(1)


def run(cmd):
    try:
        output = subprocess.Popen(
            cmd,
            shell=True,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        (out, err) = output.communicate()
    except Exception as e:
        logging.error("Failed to run %s, error: %s", cmd, e)
    return out


def print_running_pods():
    regex_namespace_list = ["openshift-.*"]
    checked_namespaces = check_namespaces(regex_namespace_list)
    pods_running = 0
    for namespace in checked_namespaces:
        new_pods_running = run(
            "oc get pods -n " + namespace + " | grep -c Running"
        ).rstrip()
        try:
            pods_running += int(new_pods_running)
        except Exception:
            continue
    print(pods_running)


if __name__ == '__main__':
    print_running_pods()
