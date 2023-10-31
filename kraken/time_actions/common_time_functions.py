import datetime
import time
import logging
import re
import yaml
import random
from ..cerberus import setup as cerberus
from ..invoke import command as runcommand
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.utils.functions import get_yaml_item_value, log_exception


# krkn_lib
def pod_exec(pod_name, command, namespace, container_name, kubecli:KrknKubernetes):
    for i in range(5):
        response = kubecli.exec_cmd_in_pod(
            command,
            pod_name,
            namespace,
            container_name
        )
        if not response:
            time.sleep(2)
            continue
        elif (
            "unauthorized" in response.lower() or
            "authorization" in response.lower()
        ):
            time.sleep(2)
            continue
        else:
            break
    return response


def node_debug(node_name, command):
    response = runcommand.invoke(
        "oc debug node/" + node_name + " -- chroot /host " + command
    )
    return response


# krkn_lib
def get_container_name(pod_name, namespace, kubecli:KrknKubernetes, container_name=""):

    container_names = kubecli.get_containers_in_pod(pod_name, namespace)
    if container_name != "":
        if container_name in container_names:
            return container_name
        else:
            logging.error(
                "Container name %s not an existing container in pod %s" % (
                    container_name,
                    pod_name
                )
            )
    else:
        container_name = container_names[
            # random module here is not used for security/cryptographic
            # purposes
            random.randint(0, len(container_names) - 1)  # nosec
        ]
        return container_name


# krkn_lib
def skew_time(scenario, kubecli:KrknKubernetes):
    skew_command = "date --date "
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
        elif (
            "label_selector" in scenario.keys() and
            scenario["label_selector"]
        ):
            node_names = kubecli.list_nodes(scenario["label_selector"])

        for node in node_names:
            node_debug(node, skew_command)
            logging.info("Reset date/time on node " + str(node))
        return "node", node_names

    elif "pod" in scenario["object_type"]:
        container_name = get_yaml_item_value(scenario, "container_name", "")
        pod_names = []
        if "object_name" in scenario.keys() and scenario["object_name"]:
            for name in scenario["object_name"]:
                if "namespace" not in scenario.keys():
                    logging.error("Need to set namespace when using pod name")
                    # removed_exit
                    # sys.exit(1)
                    raise RuntimeError()
                pod_names.append([name, scenario["namespace"]])
        elif "namespace" in scenario.keys() and scenario["namespace"]:
            if "label_selector" not in scenario.keys():
                logging.info(
                    "label_selector key not found, querying for all the pods "
                    "in namespace: %s" % (scenario["namespace"])
                )
                pod_names = kubecli.list_pods(scenario["namespace"])
            else:
                logging.info(
                    "Querying for the pods matching the %s label_selector "
                    "in namespace %s"
                    % (scenario["label_selector"], scenario["namespace"])
                )
                pod_names = kubecli.list_pods(
                    scenario["namespace"],
                    scenario["label_selector"]
                )
            counter = 0
            for pod_name in pod_names:
                pod_names[counter] = [pod_name, scenario["namespace"]]
                counter += 1
        elif (
            "label_selector" in scenario.keys() and
            scenario["label_selector"]
        ):
            pod_names = kubecli.get_all_pods(scenario["label_selector"])

        if len(pod_names) == 0:
            logging.info(
                "Cannot find pods matching the namespace/label_selector, "
                "please check"
            )
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()
        pod_counter = 0
        for pod in pod_names:
            if len(pod) > 1:
                selected_container_name = get_container_name(
                    pod[0],
                    pod[1],
                    kubecli,
                    container_name,

                )
                pod_exec_response = pod_exec(
                    pod[0],
                    skew_command,
                    pod[1],
                    selected_container_name,
                    kubecli,

                )
                if pod_exec_response is False:
                    logging.error(
                        "Couldn't reset time on container %s "
                        "in pod %s in namespace %s"
                        % (selected_container_name, pod[0], pod[1])
                    )
                    # removed_exit
                    # sys.exit(1)
                    raise RuntimeError()
                pod_names[pod_counter].append(selected_container_name)
            else:
                selected_container_name = get_container_name(
                    pod,
                    scenario["namespace"],
                    kubecli,
                    container_name
                )
                pod_exec_response = pod_exec(
                    pod,
                    skew_command,
                    scenario["namespace"],
                    selected_container_name,
                    kubecli
                )
                if pod_exec_response is False:
                    logging.error(
                        "Couldn't reset time on container "
                        "%s in pod %s in namespace %s"
                        % (
                            selected_container_name,
                            pod,
                            scenario["namespace"]
                        )
                    )
                    # removed_exit
                    # sys.exit(1)
                    raise RuntimeError()
                pod_names[pod_counter].append(selected_container_name)
            logging.info("Reset date/time on pod " + str(pod[0]))
            pod_counter += 1
        return "pod", pod_names


# From kubectl/oc command get time output
def parse_string_date(obj_datetime):
    try:
        logging.info("Obj_date time " + str(obj_datetime))
        obj_datetime = re.sub(r"\s\s+", " ", obj_datetime).strip()
        logging.info("Obj_date sub time " + str(obj_datetime))
        date_line = re.match(
            r"[\s\S\n]*\w{3} \w{3} \d{1,} \d{2}:\d{2}:\d{2} \w{3} \d{4}[\s\S\n]*",  # noqa
            obj_datetime
        )
        if date_line is not None:
            search_response = date_line.group().strip()
            logging.info("Search response: " + str(search_response))
            return search_response
        else:
            return ""
    except Exception as e:
        logging.info(
            "Exception %s when trying to parse string to date" % str(e)
        )
        return ""


# Get date and time from string returned from OC
def string_to_date(obj_datetime):
    obj_datetime = parse_string_date(obj_datetime)
    try:
        date_time_obj = datetime.datetime.strptime(
            obj_datetime,
            "%a %b %d %H:%M:%S %Z %Y"
        )
        return date_time_obj
    except Exception:
        logging.info("Couldn't parse string to datetime object")
        return datetime.datetime(datetime.MINYEAR, 1, 1)


# krkn_lib
def check_date_time(object_type, names, kubecli:KrknKubernetes):
    skew_command = "date"
    not_reset = []
    max_retries = 30
    if object_type == "node":
        for node_name in names:
            first_date_time = datetime.datetime.utcnow()
            node_datetime_string = node_debug(node_name, skew_command)
            node_datetime = string_to_date(node_datetime_string)
            counter = 0
            while not (
                first_date_time < node_datetime < datetime.datetime.utcnow()
            ):
                time.sleep(10)
                logging.info(
                    "Date/time on node %s still not reset, "
                    "waiting 10 seconds and retrying" % node_name
                )
                node_datetime_string = node_debug(node_name, skew_command)
                node_datetime = string_to_date(node_datetime_string)
                counter += 1
                if counter > max_retries:
                    logging.error(
                        "Date and time in node %s didn't reset properly" %
                        node_name
                    )
                    not_reset.append(node_name)
                    break
            if counter < max_retries:
                logging.info(
                    "Date in node " + str(node_name) + " reset properly"
                )
    elif object_type == "pod":
        for pod_name in names:
            first_date_time = datetime.datetime.utcnow()
            counter = 0
            pod_datetime_string = pod_exec(
                pod_name[0],
                skew_command,
                pod_name[1],
                pod_name[2],
                kubecli
            )
            pod_datetime = string_to_date(pod_datetime_string)
            while not (
                first_date_time < pod_datetime < datetime.datetime.utcnow()
            ):
                time.sleep(10)
                logging.info(
                    "Date/time on pod %s still not reset, "
                    "waiting 10 seconds and retrying" % pod_name[0]
                )
                pod_datetime = pod_exec(
                    pod_name[0],
                    skew_command,
                    pod_name[1],
                    pod_name[2],
                    kubecli
                )
                pod_datetime = string_to_date(pod_datetime)
                counter += 1
                if counter > max_retries:
                    logging.error(
                        "Date and time in pod %s didn't reset properly" %
                        pod_name[0]
                    )
                    not_reset.append(pod_name[0])
                    break
            if counter < max_retries:
                logging.info(
                    "Date in pod " + str(pod_name[0]) + " reset properly"
                )
    return not_reset


# krkn_lib
def run(scenarios_list, config, wait_duration, kubecli:KrknKubernetes, telemetry: KrknTelemetryKubernetes) -> (list[str], list[ScenarioTelemetry]):
    failed_scenarios = []
    scenario_telemetries: list[ScenarioTelemetry] = []
    for time_scenario_config in scenarios_list:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = time_scenario_config
        scenario_telemetry.startTimeStamp = time.time()
        telemetry.set_parameters_base64(scenario_telemetry, time_scenario_config)
        try:
            with open(time_scenario_config, "r") as f:
                scenario_config = yaml.full_load(f)
                for time_scenario in scenario_config["time_scenarios"]:
                    start_time = int(time.time())
                    object_type, object_names = skew_time(time_scenario, kubecli)
                    not_reset = check_date_time(object_type, object_names, kubecli)
                    if len(not_reset) > 0:
                        logging.info("Object times were not reset")
                    logging.info(
                        "Waiting for the specified duration: %s" % (wait_duration)
                    )
                    time.sleep(wait_duration)
                    end_time = int(time.time())
                    cerberus.publish_kraken_status(
                        config,
                        not_reset,
                        start_time,
                        end_time
                    )
        except (RuntimeError, Exception):
            scenario_telemetry.exitStatus = 1
            log_exception(time_scenario_config)
            failed_scenarios.append(time_scenario_config)
        else:
            scenario_telemetry.exitStatus = 0
        scenario_telemetry.endTimeStamp = time.time()
        scenario_telemetries.append(scenario_telemetry)

    return failed_scenarios, scenario_telemetries
