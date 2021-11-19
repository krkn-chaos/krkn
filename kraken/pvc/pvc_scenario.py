import sys
import yaml
import re
import json
import logging
import time
import kraken.cerberus.setup as cerberus
import kraken.kubernetes.client as kubecli
import kraken.invoke.command as runcommand

# Reads the scenario config and creates a temp file to fill up the PVC


def run(scenarios_list, config):
    failed_post_scenarios = ""
    for app_config in scenarios_list:
        if len(app_config) > 1:
            with open(app_config, "r") as f:
                config_yaml = yaml.full_load(f)
                scenario_config = config_yaml["pvc_scenario"]
                pvc_name = scenario_config.get("pvc_name", "")
                namespace = scenario_config.get("namespace", "")
                target_fill_percentage = scenario_config.get("fill_percentage", "50")
                duration = scenario_config.get("duration", 60)

                # Check input params
                if len(pvc_name) == 0:
                    logging.error("You must specify the pvc_name")
                    sys.exit(1)
                if len(namespace) == 0:
                    logging.error("You must specify the namespace where the PVC is")
                    sys.exit(1)

                # Get pod name
                command = "oc describe pvc %s -n %s | grep \"Used By:\" | grep -Eo '[^: ]*$'" % (
                    str(pvc_name),
                    str(namespace),
                )
                logging.debug("Get pod name command:\n %s" % command)
                pod_name = runcommand.invoke(command, 60).rstrip()
                logging.debug("Pod name: %s" % pod_name)
                if pod_name == "<none>":
                    logging.error(
                        "Pod associated with %s PVC, on namespace %s, not found" % (str(pvc_name), str(namespace))
                    )
                    sys.exit(1)

                # Get mount path
                command = 'oc get pods %s -n %s -o json | jq -r ".spec.containers[].volumeMounts"' % (
                    str(pod_name),
                    str(namespace),
                )
                logging.debug("Get mount path command:\n %s" % command)
                volume_mounts_list = runcommand.invoke(command, 60).rstrip()
                volume_mounts_list_json = json.loads(volume_mounts_list)
                for entry in volume_mounts_list_json:
                    if entry["name"] == pvc_name:
                        mount_path = entry["mountPath"]
                        break
                logging.debug("Mount path: %s" % mount_path)

                # Get PVC capacity
                pvc_capacity = runcommand.invoke(
                    "oc describe pvc %s -n %s | grep \"Capacity:\" | grep -Eo '[^: ]*$'"
                    % (str(pvc_name), str(namespace)),
                    60,
                ).rstrip()
                pvc_capacity_bytes = toKbytes(pvc_capacity)
                logging.debug("PVC capacity: %s KB" % pvc_capacity_bytes)

                # Get used bytes in pvc
                command = "du -sk %s | grep -Eo '[0-9]*'" % (str(mount_path))
                pvc_used = kubecli.exec_cmd_in_pod(command, pod_name, namespace)
                logging.debug("PVC used: %s KB" % pvc_used)

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
                # Create temp file in the pvc
                full_path = "%s/%s" % (str(mount_path), str(file_name))
                command = "dd bs=1024 count=%s </dev/urandom >%s" % (str(file_size), str(full_path))
                response = kubecli.exec_cmd_in_pod(command, pod_name, namespace)
                logging.info("\n" + str(response))
                if "copied" in response.lower():
                    logging.info("%s file successfully created" % (str(full_path)))
                else:
                    logging.error("Failed to create tmp file with %s size" % (str(file_size)))
                    sys.exit(1)

                # Wait for the specified duration
                logging.info("Waiting for the specified duration in the config: %ss" % (duration))
                time.sleep(duration)
                logging.info("Finish waiting")

                # Remove the temp file from the pvc
                command = "rm %s" % (str(full_path))
                kubecli.exec_cmd_in_pod(command, pod_name, namespace)
                command = "ls %s" % (str(mount_path))
                response = kubecli.exec_cmd_in_pod(command, pod_name, namespace)
                logging.info("\n" + str(response))
                if not (file_name in response.lower()):
                    logging.info("Temp file successfully removed")
                else:
                    logging.error("Failed to delete tmp file with %s size" % (str(file_size)))
                    sys.exit(1)

                end_time = int(time.time())
                cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)


def toKbytes(value):
    if not re.match("^[0-9]+[K|M|G|T]i$", value):
        logging.error("PVC capacity %s does not match expression regexp '^[0-9]+[K|M|G|T]i$'")
        sys.exit(1)
    unit = {"K": 0, "M": 1, "G": 2, "T": 3}
    base = 1024 if ("i" in value) else 1000
    exp = unit[value[-2:-1]]
    res = int(value[:-2]) * (base ** exp)
    return res
