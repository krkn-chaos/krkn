import base64
import json
import logging
import os
import time

import yaml
from krkn_lib import utils as krkn_lib_utils
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator


class SynFloodScenarioPlugin(AbstractScenarioPlugin):
    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            pod_names = []
            config = self.parse_config(scenario)
            if config["target-service-label"]:
                target_services = (
                    lib_telemetry.get_lib_kubernetes().select_service_by_label(
                        config["namespace"], config["target-service-label"]
                    )
                )
            else:
                target_services = [config["target-service"]]

            for target in target_services:
                if not lib_telemetry.get_lib_kubernetes().service_exists(
                    target, config["namespace"]
                ):
                    logging.error(f"SynFloodScenarioPlugin {target} service not found")
                    return 1
                for i in range(config["number-of-pods"]):
                    pod_name = "syn-flood-" + krkn_lib_utils.get_random_string(10)
                    lib_telemetry.get_lib_kubernetes().deploy_syn_flood(
                        pod_name,
                        config["namespace"],
                        config["image"],
                        target,
                        config["target-port"],
                        config["packet-size"],
                        config["window-size"],
                        config["duration"],
                        config["attacker-nodes"],
                    )
                    pod_names.append(pod_name)
                
                # Set rollback callable to ensure pod cleanup on failure or interruption
                rollback_data = base64.b64encode(json.dumps(pod_names).encode('utf-8')).decode('utf-8')
                self.rollback_handler.set_rollback_callable(
                    self.rollback_syn_flood_pods,
                    RollbackContent(
                        namespace=config["namespace"],
                        resource_identifier=rollback_data,
                    ),
                )

            logging.info("waiting all the attackers to finish:")
            did_finish = False
            finished_pods = []
            while not did_finish:
                for pod_name in pod_names:
                    if not lib_telemetry.get_lib_kubernetes().is_pod_running(
                        pod_name, config["namespace"]
                    ):
                        finished_pods.append(pod_name)
                    if set(pod_names) == set(finished_pods):
                        did_finish = True
                time.sleep(1)

        except Exception as e:
            logging.error(
                f"SynFloodScenarioPlugin scenario {scenario} failed with exception: {e}"
            )
            return 1
        else:
            return 0

    def parse_config(self, scenario_file: str) -> dict[str, any]:
        if not os.path.exists(scenario_file):
            raise Exception(f"failed to load scenario file {scenario_file}")

        try:
            with open(scenario_file) as stream:
                config = yaml.safe_load(stream)
        except Exception:
            raise Exception(f"{scenario_file} is not a valid yaml file")

        missing = []
        if not self.check_key_value(config, "packet-size"):
            missing.append("packet-size")
        if not self.check_key_value(config, "window-size"):
            missing.append("window-size")
        if not self.check_key_value(config, "duration"):
            missing.append("duration")
        if not self.check_key_value(config, "namespace"):
            missing.append("namespace")
        if not self.check_key_value(config, "number-of-pods"):
            missing.append("number-of-pods")
        if not self.check_key_value(config, "target-port"):
            missing.append("target-port")
        if not self.check_key_value(config, "image"):
            missing.append("image")
        if "target-service" not in config.keys():
            missing.append("target-service")
        if "target-service-label" not in config.keys():
            missing.append("target-service-label")

        if len(missing) > 0:
            raise Exception(f"{(',').join(missing)} parameter(s) are missing")

        if not config["target-service"] and not config["target-service-label"]:
            raise Exception("you have either to set a target service or a label")
        if config["target-service"] and config["target-service-label"]:
            raise Exception(
                "you cannot select both target-service and target-service-label"
            )

        if "attacker-nodes" and not self.is_node_affinity_correct(
            config["attacker-nodes"]
        ):
            raise Exception("attacker-nodes format is not correct")
        return config

    def check_key_value(self, dictionary, key):
        if key in dictionary:
            value = dictionary[key]
            if value is not None and value != "":
                return True
        return False

    def is_node_affinity_correct(self, obj) -> bool:
        if not isinstance(obj, dict):
            return False
        for key in obj.keys():
            if not isinstance(key, str):
                return False
            if not isinstance(obj[key], list):
                return False
        return True

    def get_scenario_types(self) -> list[str]:
        return ["syn_flood_scenarios"]

    @staticmethod
    def rollback_syn_flood_pods(rollback_content: RollbackContent, lib_telemetry: KrknTelemetryOpenshift):
        """
        Rollback function to delete syn flood pods.

        :param rollback_content: Rollback content containing namespace and resource_identifier.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations
        """
        try:
            namespace = rollback_content.namespace
            import base64 # noqa
            import json # noqa
            pod_names = json.loads(base64.b64decode(rollback_content.resource_identifier.encode('utf-8')).decode('utf-8'))
            logging.info(f"Rolling back syn flood pods: {pod_names} in namespace: {namespace}")
            for pod_name in pod_names:
                lib_telemetry.get_lib_kubernetes().delete_pod(pod_name, namespace)
            logging.info("Rollback of syn flood pods completed successfully.")
        except Exception as e:
            logging.error(f"Failed to rollback syn flood pods: {e}")