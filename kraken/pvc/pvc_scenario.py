import sys
import random
import yaml
import re
import json
import logging
import time
import kraken.cerberus.setup as cerberus
import kraken.kubernetes.client as kubecli

# Reads the scenario config and creates a temp file to fill up the PVC


def run(scenarios_list, config):
    failed_post_scenarios = ""
    for app_config in scenarios_list:
        if len(app_config) > 1:
            with open(app_config, "r") as f:
                config_yaml = yaml.full_load(f)
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
                            "pod_name '%s' will be overridden with one of the pods mounted in the PVC" % (str(pod_name))
                        )
                    pvc = kubecli.get_pvc_info(pvc_name, namespace)
                    try:
                        pod_name = random.choice(pvc.podNames)
                        logging.info("Pod name: %s" % pod_name)
                    except Exception:
                        logging.error(
                            "Pod associated with %s PVC, on namespace %s, not found" % (str(pvc_name), str(namespace))
                        )
                        sys.exit(1)

                # Get volume name
                pod = kubecli.get_pod_info(name=pod_name, namespace=namespace)
                
                if pod is None:
                    sys.exit(1)
                
                for volume in pod.volumes:
                    if volume.pvcName is not None:
                        volume_name = volume.name
                        pvc_name = volume.pvcName
                        pvc = kubecli.get_pvc_info(pvc_name, namespace)
                        break
                if 'pvc' not in locals():
                    logging.error(
                        "Pod '%s' in namespace '%s' does not use a pvc" % (str(pod_name), str(namespace))
                    )
                    sys.exit(1)
                logging.info("Volume name: %s" % volume_name)
                logging.info("PVC name: %s" % pvc_name)

                # Get container name and mount path
                for container in  pod.containers:
                    for vol in container.volumeMounts:
                        if vol.name == volume_name:
                            mount_path = vol.mountPath
                            container_name = container.name
                            break
                logging.info("Container path: %s" % container_name)
                logging.info("Mount path: %s" % mount_path)

                # Get PVC capacity
                pvc_capacity = pvc.capacity
                pvc_capacity_kb = toKbytes(pvc_capacity)
                logging.info("PVC capacity: %s KB" % pvc_capacity_kb)

                # Get used bytes in PVC
                command = "df %s -B 1024 | sed 1d | awk -F' ' '{print $3}'" % (str(mount_path))
                logging.debug("Get used bytes in PVC command:\n %s" % command)
                pvc_used_kb = kubecli.exec_cmd_in_pod(command, pod_name, namespace, container_name, "sh")
                logging.info("PVC used: %s KB" % pvc_used_kb)

                # Check valid fill percentage
                current_fill_percentage = float(pvc_used_kb) / float(pvc_capacity_kb)
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
                file_size_kb = int((float(target_fill_percentage / 100) * float(pvc_capacity_kb)) - float(pvc_used_kb))
                logging.debug("File size: %s KB" % file_size_kb)

                file_name = "kraken.tmp"
                logging.info(
                    "Creating %s file, %s KB size, in pod %s at %s (ns %s)"
                    % (str(file_name), str(file_size_kb), str(pod_name), str(mount_path), str(namespace))
                )

                start_time = int(time.time())
                # Create temp file in the PVC
                full_path = "%s/%s" % (str(mount_path), str(file_name))
                command = "fallocate -l $((%s*1024)) %s" % (str(file_size_kb), str(full_path))
                logging.debug("Create temp file in the PVC command:\n %s" % command)
                kubecli.exec_cmd_in_pod(command, pod_name, namespace, container_name, "sh")

                # Check if file is created
                command = "ls -lh %s" % (str(mount_path))
                logging.debug("Check file is created command:\n %s" % command)
                response = kubecli.exec_cmd_in_pod(command, pod_name, namespace, container_name, "sh")
                logging.info("\n" + str(response))
                if str(file_name).lower() in str(response).lower():
                    logging.info("%s file successfully created" % (str(full_path)))
                else:
                    logging.error("Failed to create tmp file with %s size" % (str(file_size_kb)))
                    remove_temp_file(file_name, full_path, pod_name, namespace, container_name, mount_path, file_size_kb)
                    sys.exit(1)

                # Wait for the specified duration
                logging.info("Waiting for the specified duration in the config: %ss" % (duration))
                time.sleep(duration)
                logging.info("Finish waiting")

                remove_temp_file(file_name, full_path, pod_name, namespace, container_name, mount_path, file_size_kb)

                end_time = int(time.time())
                cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)


def remove_temp_file(file_name, full_path, pod_name, namespace, container_name, mount_path, file_size_kb):
    command = "rm -f %s" % (str(full_path))
    logging.debug("Remove temp file from the PVC command:\n %s" % command)
    kubecli.exec_cmd_in_pod(command, pod_name, namespace, container_name, "sh")
    command = "ls -lh %s" % (str(mount_path))
    logging.debug("Check temp file is removed command:\n %s" % command)
    response = kubecli.exec_cmd_in_pod(command, pod_name, namespace, container_name, "sh")
    logging.info("\n" + str(response))
    if not (str(file_name).lower() in str(response).lower()):
        logging.info("Temp file successfully removed")
    else:
        logging.error("Failed to delete tmp file with %s size" % (str(file_size_kb)))
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
