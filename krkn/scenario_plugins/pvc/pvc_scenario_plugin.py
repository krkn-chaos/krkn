import base64
import json
import logging
import random
import re
import time

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator


class PvcScenarioPlugin(AbstractScenarioPlugin):
    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario, "r") as f:
                config_yaml = yaml.full_load(f)
                scenario_config = config_yaml["pvc_scenario"]
                pvc_name = get_yaml_item_value(scenario_config, "pvc_name", "")
                pod_name = get_yaml_item_value(scenario_config, "pod_name", "")
                namespace = get_yaml_item_value(scenario_config, "namespace", "")
                block_size = get_yaml_item_value(
                    scenario_config, "block_size", "102400"
                )
                target_fill_percentage = get_yaml_item_value(
                    scenario_config, "fill_percentage", "50"
                )
                duration = get_yaml_item_value(scenario_config, "duration", 60)

                logging.info(
                    "Input params:\n"
                    "pvc_name: '%s'\n"
                    "pod_name: '%s'\n"
                    "namespace: '%s'\n"
                    "target_fill_percentage: '%s%%'\nduration: '%ss'"
                    % (
                        str(pvc_name),
                        str(pod_name),
                        str(namespace),
                        str(target_fill_percentage),
                        str(duration),
                    )
                )

                # Check input params
                if namespace is None:
                    logging.error(
                        "PvcScenarioPlugin You must specify the namespace where the PVC is"
                    )
                    return 1
                if pvc_name is None and pod_name is None:
                    logging.error(
                        "PvcScenarioPlugin You must specify the pvc_name or the pod_name"
                    )
                    return 1
                if pvc_name and pod_name:
                    logging.info(
                        "pod_name will be ignored, pod_name used will be "
                        "a retrieved from the pod used in the pvc_name"
                    )

                # Get pod name
                if pvc_name:
                    if pod_name:
                        logging.info(
                            "pod_name '%s' will be overridden with one of "
                            "the pods mounted in the PVC" % (str(pod_name))
                        )
                    pvc = lib_telemetry.get_lib_kubernetes().get_pvc_info(
                        pvc_name, namespace
                    )
                    try:
                        # random generator not used for
                        # security/cryptographic purposes.
                        pod_name = random.choice(pvc.podNames)  # nosec
                        logging.info("Pod name: %s" % pod_name)
                    except Exception:
                        logging.error(
                            "PvcScenarioPlugin Pod associated with %s PVC, on namespace %s, "
                            "not found" % (str(pvc_name), str(namespace))
                        )
                        return 1

                # Get volume name
                pod = lib_telemetry.get_lib_kubernetes().get_pod_info(
                    name=pod_name, namespace=namespace
                )

                if pod is None:
                    logging.error(
                        "PvcScenarioPlugin Exiting as pod '%s' doesn't exist "
                        "in namespace '%s'" % (str(pod_name), str(namespace))
                    )
                    return 1

                for volume in pod.volumes:
                    if volume.pvcName is not None:
                        volume_name = volume.name
                        pvc_name = volume.pvcName
                        pvc = lib_telemetry.get_lib_kubernetes().get_pvc_info(
                            pvc_name, namespace
                        )
                        break
                if "pvc" not in locals():
                    logging.error(
                        "PvcScenarioPlugin Pod '%s' in namespace '%s' does not use a pvc"
                        % (str(pod_name), str(namespace))
                    )
                    return 1
                logging.info("Volume name: %s" % volume_name)
                logging.info("PVC name: %s" % pvc_name)

                # Get container name and mount path
                for container in pod.containers:
                    for vol in container.volumeMounts:
                        if vol.name == volume_name:
                            mount_path = vol.mountPath
                            container_name = container.name
                            break
                logging.info("Container path: %s" % container_name)
                logging.info("Mount path: %s" % mount_path)

                # Get PVC capacity and used bytes
                command = "df %s -B 1024 | sed 1d" % (str(mount_path))
                command_output = (
                    lib_telemetry.get_lib_kubernetes().exec_cmd_in_pod(
                        [command], pod_name, namespace, container_name
                    )
                ).split()
                pvc_used_kb = int(command_output[2])
                pvc_capacity_kb = pvc_used_kb + int(command_output[3])
                logging.info("PVC used: %s KB" % pvc_used_kb)
                logging.info("PVC capacity: %s KB" % pvc_capacity_kb)

                # Check valid fill percentage
                current_fill_percentage = pvc_used_kb / pvc_capacity_kb
                if not (
                    current_fill_percentage * 100 < float(target_fill_percentage) <= 99
                ):
                    logging.error(
                        "PvcScenarioPlugin Target fill percentage (%.2f%%) is lower than "
                        "current fill percentage (%.2f%%) "
                        "or higher than 99%%"
                        % (
                            target_fill_percentage,
                            current_fill_percentage * 100,
                        )
                    )
                    return 1
                # Calculate file size
                file_size_kb = int(
                    (float(target_fill_percentage / 100) * float(pvc_capacity_kb))
                    - float(pvc_used_kb)
                )
                logging.debug("File size: %s KB" % file_size_kb)

                file_name = "kraken.tmp"
                logging.info(
                    "Creating %s file, %s KB size, in pod %s at %s (ns %s)"
                    % (
                        str(file_name),
                        str(file_size_kb),
                        str(pod_name),
                        str(mount_path),
                        str(namespace),
                    )
                )

                # Create temp file in the PVC
                full_path = "%s/%s" % (str(mount_path), str(file_name))

                fallocate = lib_telemetry.get_lib_kubernetes().exec_cmd_in_pod(
                    ["command -v fallocate"],
                    pod_name,
                    namespace,
                    container_name,
                )

                dd = lib_telemetry.get_lib_kubernetes().exec_cmd_in_pod(
                    ["command -v dd"],
                    pod_name,
                    namespace,
                    container_name,
                )

                if fallocate:
                    command = "fallocate -l $((%s*1024)) %s" % (
                        str(file_size_kb),
                        str(full_path),
                    )
                elif dd is not None:
                    block_size = int(block_size)
                    blocks = int(file_size_kb / int(block_size / 1024))
                    logging.warning(
                        "fallocate not found, using dd, it may take longer based on the amount of data, please wait..."
                    )
                    command = f"dd if=/dev/urandom of={str(full_path)} bs={str(block_size)} count={str(blocks)} oflag=direct"
                else:
                    logging.error(
                        "failed to locate required binaries fallocate or dd to execute the scenario"
                    )
                    return 1

                logging.debug("Create temp file in the PVC command:\n %s" % command)
                lib_telemetry.get_lib_kubernetes().exec_cmd_in_pod(
                    [command],
                    pod_name,
                    namespace,
                    container_name,
                )

                # Check if file is created
                command = "ls -lh %s" % (str(mount_path))
                logging.debug("Check file is created command:\n %s" % command)
                response = lib_telemetry.get_lib_kubernetes().exec_cmd_in_pod(
                    [command], pod_name, namespace, container_name
                )
                logging.info("\n" + str(response))
                if str(file_name).lower() in str(response).lower():
                    logging.info("%s file successfully created" % (str(full_path)))
                    
                    # Set rollback callable to ensure temp file cleanup on failure or interruption
                    rollback_data = {
                        "pod_name": pod_name,
                        "container_name": container_name,
                        "mount_path": mount_path,
                        "file_name": file_name,
                        "full_path": full_path,
                    }
                    json_str = json.dumps(rollback_data)
                    encoded_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                    self.rollback_handler.set_rollback_callable(
                        self.rollback_temp_file,
                        RollbackContent(
                            namespace=namespace,
                            resource_identifier=encoded_data,
                        ),
                    )
                else:
                    logging.error(
                        "PvcScenarioPlugin Failed to create tmp file with %s size"
                        % (str(file_size_kb))
                    )
                    self.remove_temp_file(
                        file_name,
                        full_path,
                        pod_name,
                        namespace,
                        container_name,
                        mount_path,
                        file_size_kb,
                        lib_telemetry.get_lib_kubernetes(),
                    )
                    return 1

                logging.info(
                    "Waiting for the specified duration in the config: %ss" % duration
                )
                time.sleep(duration)
                logging.info("Finish waiting")

                self.remove_temp_file(
                    file_name,
                    full_path,
                    pod_name,
                    namespace,
                    container_name,
                    mount_path,
                    file_size_kb,
                    lib_telemetry.get_lib_kubernetes(),
                )
        except (RuntimeError, Exception) as e:
            logging.error("PvcScenarioPlugin exiting due to Exception %s" % e)
            return 1
        else:
            return 0

    # krkn_lib
    def remove_temp_file(
        self,
        file_name,
        full_path,
        pod_name,
        namespace,
        container_name,
        mount_path,
        file_size_kb,
        kubecli: KrknKubernetes,
    ):
        command = "rm -f %s" % (str(full_path))
        logging.debug("Remove temp file from the PVC command:\n %s" % command)
        kubecli.exec_cmd_in_pod([command], pod_name, namespace, container_name)
        command = "ls -lh %s" % (str(mount_path))
        logging.debug("Check temp file is removed command:\n %s" % command)
        response = kubecli.exec_cmd_in_pod(
            [command], pod_name, namespace, container_name
        )
        logging.info("\n" + str(response))
        if not (str(file_name).lower() in str(response).lower()):
            logging.info("Temp file successfully removed")
        else:
            logging.error(
                "PvcScenarioPlugin Failed to delete tmp file with %s size"
                % (str(file_size_kb))
            )
            raise RuntimeError()

    def to_kbytes(self, value):
        if not re.match("^[0-9]+[K|M|G|T]i$", value):
            logging.error(
                "PvcScenarioPlugin PVC capacity %s does not match expression "
                "regexp '^[0-9]+[K|M|G|T]i$'"
            )
            raise RuntimeError()
        unit = {"K": 0, "M": 1, "G": 2, "T": 3}
        base = 1024 if ("i" in value) else 1000
        exp = unit[value[-2:-1]]
        res = int(value[:-2]) * (base**exp)
        return res

    @staticmethod
    def rollback_temp_file(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        """Rollback function to remove temporary file created during the PVC scenario.

        :param rollback_content: Rollback content containing namespace and encoded rollback data in resource_identifier.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations.
        """
        try:
            namespace = rollback_content.namespace
            import base64 # noqa
            import json # noqa
            decoded_data = base64.b64decode(rollback_content.resource_identifier.encode('utf-8')).decode('utf-8')
            rollback_data = json.loads(decoded_data)
            pod_name = rollback_data["pod_name"]
            container_name = rollback_data["container_name"]
            full_path = rollback_data["full_path"]
            file_name = rollback_data["file_name"]
            mount_path = rollback_data["mount_path"]
            
            logging.info(
                f"Rolling back PVC scenario: removing temp file {full_path} from pod {pod_name} in namespace {namespace}"
            )
            
            # Remove the temp file
            command = "rm -f %s" % (str(full_path))
            logging.info("Remove temp file from the PVC command:\n %s" % command)
            response = lib_telemetry.get_lib_kubernetes().exec_cmd_in_pod(
                [command], pod_name, namespace, container_name
            )
            logging.info("\n" + str(response))
            # Verify removal
            command = "ls -lh %s" % (str(mount_path))
            logging.info("Check temp file is removed command:\n %s" % command)
            response = lib_telemetry.get_lib_kubernetes().exec_cmd_in_pod(
                [command], pod_name, namespace, container_name
            )
            logging.info("\n" + str(response))
            
            if not (str(file_name).lower() in str(response).lower()):
                logging.info("Temp file successfully removed during rollback")
            else:
                logging.warning(
                    f"Temp file {file_name} may still exist after rollback attempt"
                )
            
            logging.info("PVC scenario rollback completed successfully.")
        except Exception as e:
            logging.error(f"Failed to rollback PVC scenario temp file: {e}")

    def get_scenario_types(self) -> list[str]:
        return ["pvc_scenarios"]
