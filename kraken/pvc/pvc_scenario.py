import sys
import yaml
import re
import json
import logging
import time
import kraken.cerberus.setup as cerberus
import kraken.kubernetes.client as kubecli
import kraken.invoke.command as runcommand
import os
import requests

# Reads the scenario config and creates a temp file to fill up the PVC


def run(scenarios_list, config):
    failed_post_scenarios = ""
    for app_config in scenarios_list:
        if len(app_config) > 1:
            # Parse and read the config
            try:
                # For config as local file
                if os.path.isfile(app_config):
                    with open(app_config, "r") as f:
                        config_yaml = yaml.full_load(f)

                # For config as remote file
                else:
                    content = requests.get(app_config)
                    # Checking the status code if it is OK and the request is successful
                    if content.status_code == 200:
                        texts = content.text
                        config_yaml = yaml.full_load(texts)

                    else:
                        # Raising the exception since config file can't be loaded as a yaml
                        raise Exception

            except Exception:
                logging.error("Cannot find a yaml file at %s, please check" % (app_config))
                sys.exit(1)

            scenario_config = config_yaml["pvc_scenario"]
            pvc_name = scenario_config.get("pvc_name", "")
            pod_name = scenario_config.get("pod_name", "")
            namespace = scenario_config.get("namespace", "")
            target_fill_percentage = scenario_config.get("fill_percentage", "50")
            duration = scenario_config.get("duration", 60)

            logging.info(
                """Input params:
pvc_name: '%s'\npod_name: '%s'\nnamespace: '%s'\ntarget_fill_percentage: '%s%%'\nduration: '%ss'"""
                % (str(pvc_name), str(pod_name), str(namespace), str(target_fill_percentage), str(duration))
            )

            # Check input params
            if namespace is None:
                logging.error("You must specify the namespace where the PVC is")
                sys.exit(1)
            if pvc_name is None and pod_name is None:
                logging.error("You must specify the pvc_name or the pod_name")
                sys.exit(1)
            if pvc_name and pod_name:
                logging.info(
                    "pod_name will be ignored, pod_name used will be a retrieved from the pod used in the pvc_name"
                )

            # Get pod name
            if pvc_name:
                if pod_name:
                    logging.info(
                        "pod_name '%s' will be overridden from the pod mounted in the PVC" % (str(pod_name))
                    )
                command = "kubectl describe pvc %s -n %s | grep -E 'Mounted By:|Used By:' | grep -Eo '[^: ]*$'" % (
                    str(pvc_name),
                    str(namespace),
                )
                logging.debug("Get pod name command:\n %s" % command)
                pod_name = runcommand.invoke(command, 60).rstrip()
                logging.info("Pod name: %s" % pod_name)
                if pod_name == "<none>":
                    logging.error(
                        "Pod associated with %s PVC, on namespace %s, not found" % (str(pvc_name), str(namespace))
                    )
                    sys.exit(1)

            # Get volume name
            command = 'kubectl get pods %s -n %s -o json | jq -r ".spec.volumes"' % (
                str(pod_name),
                str(namespace),
            )
            logging.debug("Get mount path command:\n %s" % command)
            volumes_list = runcommand.invoke(command, 60).rstrip()
            volumes_list_json = json.loads(volumes_list)
            for entry in volumes_list_json:
                if len(entry["persistentVolumeClaim"]["claimName"]) > 0:
                    volume_name = entry["name"]
                    pvc_name = entry["persistentVolumeClaim"]["claimName"]
                    break
            logging.info("Volume name: %s" % volume_name)
            logging.info("PVC name: %s" % pvc_name)

            # Get container name and mount path
            command = 'kubectl get pods %s -n %s -o json | jq -r ".spec.containers"' % (
                str(pod_name),
                str(namespace),
            )
            logging.debug("Get mount path command:\n %s" % command)
            volume_mounts_list = runcommand.invoke(command, 60).rstrip().replace("\n]\n[\n", ",\n")
            volume_mounts_list_json = json.loads(volume_mounts_list)
            for entry in volume_mounts_list_json:
                for vol in entry["volumeMounts"]:
                    if vol["name"] == volume_name:
                        mount_path = vol["mountPath"]
                        container_name = entry["name"]
                        break
            logging.info("Container path: %s" % container_name)
            logging.info("Mount path: %s" % mount_path)

            # Get PVC capacity
            command = "kubectl describe pvc %s -n %s | grep \"Capacity:\" | grep -Eo '[^: ]*$'" % (
                str(pvc_name),
                str(namespace),
            )
            pvc_capacity = runcommand.invoke(
                command,
                60,
            ).rstrip()
            logging.debug("Get PVC capacity command:\n %s" % command)
            pvc_capacity_bytes = toKbytes(pvc_capacity)
            logging.info("PVC capacity: %s KB" % pvc_capacity_bytes)

            # Get used bytes in PVC
            command = "du -sk %s | grep -Eo '^[0-9]*'" % (str(mount_path))
            logging.debug("Get used bytes in PVC command:\n %s" % command)
            pvc_used = kubecli.exec_cmd_in_pod(command, pod_name, namespace, container_name, "sh")
            logging.info("PVC used: %s KB" % pvc_used)

            # Check valid fill percentage
            current_fill_percentage = float(pvc_used) / float(pvc_capacity_bytes)
            if not (current_fill_percentage * 100 < float(target_fill_percentage) <= 99):
                logging.error(
                    """
                    Target fill percentage (%.2f%%) is lower than current fill percentage (%.2f%%)
                     or higher than 99%%
                    """
                    % (target_fill_percentage, current_fill_percentage * 100)
                )
                sys.exit(1)

            # Calculate file size
            file_size = int((float(target_fill_percentage / 100) * float(pvc_capacity_bytes)) - float(pvc_used))
            logging.debug("File size: %s KB" % file_size)

            file_name = "kraken.tmp"
            logging.info(
                "Creating %s file, %s KB size, in pod %s at %s (ns %s)"
                % (str(file_name), str(file_size), str(pod_name), str(mount_path), str(namespace))
            )

            start_time = int(time.time())
            # Create temp file in the PVC
            full_path = "%s/%s" % (str(mount_path), str(file_name))
            command = "dd bs=1024 count=%s </dev/urandom >%s" % (str(file_size), str(full_path))
            logging.debug("Create temp file in the PVC command:\n %s" % command)
            response = kubecli.exec_cmd_in_pod(command, pod_name, namespace, container_name, "sh")
            logging.info("\n" + str(response))

            # Check if file is created
            command = "ls %s" % (str(mount_path))
            logging.debug("Check file is created command:\n %s" % command)
            response = kubecli.exec_cmd_in_pod(command, pod_name, namespace, container_name, "sh")
            logging.info("\n" + str(response))
            if str(file_name).lower() in str(response).lower():
                logging.info("%s file successfully created" % (str(full_path)))
            else:
                logging.error("Failed to create tmp file with %s size" % (str(file_size)))
                remove_temp_file(file_name, full_path, pod_name, namespace, container_name, mount_path, file_size)
                sys.exit(1)

            # Wait for the specified duration
            logging.info("Waiting for the specified duration in the config: %ss" % (duration))
            time.sleep(duration)
            logging.info("Finish waiting")

            remove_temp_file(file_name, full_path, pod_name, namespace, container_name, mount_path, file_size)

            end_time = int(time.time())
            cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)


def remove_temp_file(file_name, full_path, pod_name, namespace, container_name, mount_path, file_size):
    command = "rm %s" % (str(full_path))
    logging.debug("Remove temp file from the PVC command:\n %s" % command)
    kubecli.exec_cmd_in_pod(command, pod_name, namespace, container_name, "sh")
    command = "ls %s" % (str(mount_path))
    logging.debug("Check temp file is removed command:\n %s" % command)
    response = kubecli.exec_cmd_in_pod(command, pod_name, namespace, container_name, "sh")
    logging.info("\n" + str(response))
    if not (str(file_name).lower() in str(response).lower()):
        logging.info("Temp file successfully removed")
    else:
        logging.error("Failed to delete tmp file with %s size" % (str(file_size)))
        sys.exit(1)


def toKbytes(value):
    if not re.match("^[0-9]+[K|M|G|T]i$", value):
        logging.error("PVC capacity %s does not match expression regexp '^[0-9]+[K|M|G|T]i$'")
        sys.exit(1)
    unit = {"K": 0, "M": 1, "G": 2, "T": 3}
    base = 1024 if ("i" in value) else 1000
    exp = unit[value[-2:-1]]
    res = int(value[:-2]) * (base**exp)
    return res
