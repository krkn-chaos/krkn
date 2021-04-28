import datetime
import time
import logging
import kraken.invoke.command as runcommand
import kraken.kubernetes.client as kubecli
import re
import sys


def pod_exec(pod_name, command, namespace):
    i = 0
    for i in range(5):
        response = kubecli.exec_cmd_in_pod(command, pod_name, namespace)
        if not response:
            time.sleep(2)
            continue
        elif "unauthorized" in response.lower() or "authorization" in response.lower():
            time.sleep(2)
            continue
        else:
            break
    return response


def node_debug(node_name, command):
    response = runcommand.invoke("oc debug node/" + node_name + " -- chroot /host " + command)
    return response


def skew_time(scenario):
    skew_command = "date --set "
    if scenario["action"] == "skew_date":
        skewed_date = "00-01-01"
        skew_command += skewed_date
    elif scenario["action"] == "skew_time":
        skewed_time = "01:01:01"
        skew_command += skewed_time
    if "node" in scenario["object_type"]:
        node_names = []
        if "object_name" in scenario.keys() and scenario["object_name"]:
            node_names = scenario["object_name"]
        elif "label_selector" in scenario.keys() and scenario["label_selector"]:
            node_names = kubecli.list_nodes(scenario["label_selector"])

        for node in node_names:
            node_debug(node, skew_command)
            logging.info("Reset date/time on node " + str(node))
        return "node", node_names

    elif "pod" in scenario["object_type"]:
        pod_names = []
        if "object_name" in scenario.keys() and scenario["object_name"]:
            for name in scenario["object_name"]:
                if "namespace" not in scenario.keys():
                    logging.error("Need to set namespace when using pod name")
                    sys.exit(1)
                pod_names.append([name, scenario["namespace"]])
        elif "label_selector" in scenario.keys() and scenario["label_selector"]:
            pod_names = kubecli.get_all_pods(scenario["label_selector"])
        elif "namespace" in scenario.keys() and scenario["namespace"]:
            pod_names = kubecli.list_pods(scenario["namespace"])
            counter = 0
            for pod_name in pod_names:
                pod_names[counter] = [pod_name, scenario["namespace"]]
                counter += 1

        for pod in pod_names:
            if len(pod) > 1:
                pod_exec(pod[0], skew_command, pod[1])
            else:
                pod_exec(pod, skew_command, scenario["namespace"])
            logging.info("Reset date/time on pod " + str(pod[0]))
        return "pod", pod_names


# From kubectl/oc command get time output
def parse_string_date(obj_datetime):
    try:
        date_line = re.search(r"[a-zA-Z0-9_() .]*\w{3} \w{3} \d{2} \d{2}:\d{2}:\d{2} \w{3} " r"\d{4}\W*", obj_datetime)
        return date_line.group().strip()
    except Exception:
        return ""


# Get date and time from string returned from OC
def string_to_date(obj_datetime):
    obj_datetime = parse_string_date(obj_datetime)
    try:
        date_time_obj = datetime.datetime.strptime(obj_datetime, "%a %b %d %H:%M:%S %Z %Y")
        return date_time_obj
    except Exception:
        return datetime.datetime(datetime.MINYEAR, 1, 1)


def check_date_time(object_type, names):
    skew_command = "date"
    not_reset = []
    max_retries = 30
    if object_type == "node":
        for node_name in names:
            first_date_time = datetime.datetime.utcnow()
            node_datetime_string = node_debug(node_name, skew_command)
            node_datetime = string_to_date(node_datetime_string)
            counter = 0
            while not first_date_time < node_datetime < datetime.datetime.utcnow():
                time.sleep(10)
                logging.info("Date/time on node %s still not reset, waiting 10 seconds and retrying" % node_name)
                node_datetime_string = node_debug(node_name, skew_command)
                node_datetime = string_to_date(node_datetime_string)
                counter += 1
                if counter > max_retries:
                    logging.error("Date and time in node %s didn't reset properly" % node_name)
                    not_reset.append(node_name)
                    break
            if counter < max_retries:
                logging.info("Date in node " + str(node_name) + " reset properly")
    elif object_type == "pod":
        for pod_name in names:
            first_date_time = datetime.datetime.utcnow()
            counter = 0
            pod_datetime_string = pod_exec(pod_name[0], skew_command, pod_name[1])
            pod_datetime = string_to_date(pod_datetime_string)
            while not first_date_time < pod_datetime < datetime.datetime.utcnow():
                time.sleep(10)
                logging.info("Date/time on pod %s still not reset, waiting 10 seconds and retrying" % pod_name[0])
                first_date_time = datetime.datetime.utcnow()
                pod_datetime = pod_exec(pod_name[0], skew_command, pod_name[1])
                pod_datetime = string_to_date(pod_datetime)
                counter += 1
                if counter > max_retries:
                    logging.error("Date and time in pod %s didn't reset properly" % pod_name[0])
                    not_reset.append(pod_name[0])
                    break
            if counter < max_retries:
                logging.info("Date in pod " + str(pod_name[0]) + " reset properly")
    return not_reset
