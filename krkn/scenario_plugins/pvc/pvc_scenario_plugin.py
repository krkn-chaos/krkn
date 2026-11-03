# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import random

import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator
from krkn.utils.filesystem_pvc import (encode_rollback_data, fill_filesystem_pvc)
from krkn.utils.pod_volumes import resolve_pvc_volume


def _parse_fill_percentage(value) -> float:
    """Return a numeric fill target, using 50% for missing or blank values."""
    if value is None or (isinstance(value, str) and not value.strip()):
        value = 50
    return float(value)


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
                config_yaml = yaml.safe_load(f)
                scenario_config = config_yaml["pvc_scenario"]
                pvc_name = get_yaml_item_value(scenario_config, "pvc_name", "")
                pod_name = get_yaml_item_value(scenario_config, "pod_name", "")
                namespace = get_yaml_item_value(scenario_config, "namespace", "")
                block_size = get_yaml_item_value(
                    scenario_config, "block_size", "102400"
                )
                target_fill_percentage = _parse_fill_percentage(
                    get_yaml_item_value(scenario_config, "fill_percentage", 50)
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
                if not pvc_name and not pod_name:
                    logging.error(
                        "PvcScenarioPlugin You must specify the pvc_name or the pod_name"
                    )
                    return 1
                if pvc_name and pod_name:
                    logging.info(
                        "pod_name will be ignored, pod_name used will be "
                        "a retrieved from the pod used in the pvc_name"
                    )
                    
                kubecli = lib_telemetry.get_lib_kubernetes()
                # Get pod name
                if pvc_name:
                    pvc = kubecli.get_pvc_info(pvc_name, namespace)
                    if pvc is None or not pvc.podNames:
                        logging.error(
                            "PvcScenarioPlugin: PVC '%s' in namespace '%s' was not found "
                            "or is not mounted by any pod" % (str(pvc_name), str(namespace))
                        )
                        return 1

                    # Create a shuffled copy to maintain the random attempt distribution
                    pods_to_try = list(pvc.podNames)
                    random.shuffle(pods_to_try)
                    
                    if pod_name:
                        logging.info("pod_name '%s' will be overridden with one of the pods mounted in the PVC" % (str(pod_name)))
                else:
                    if not pod_name:
                        logging.error("Either 'pvc_name' or 'pod_name' must be specified in the configuration")
                        return 1
                    # Fallback if only pod_name was provided in the configuration
                    pods_to_try = [pod_name]

                selected_pod = None
                selected_pod_name = None
                selected_target = None
                selected_shell = None
                
                for candidate_pod_name in pods_to_try:
                    shell = None
                    logging.info("Attempting to use pod '%s'",candidate_pod_name)

                    pod = kubecli.get_pod_info(name=candidate_pod_name, namespace=namespace)
                    if pod is None:
                        logging.warning("Pod '%s' was not found; trying the next pod",candidate_pod_name)
                        continue
                    
                    volume_target = resolve_pvc_volume(kubecli, pod, pvc_name)
                    if volume_target is None:
                        logging.warning("Pod '%s' does not expose PVC '%s'; trying the next pod",candidate_pod_name,pvc_name,)
                        continue
                    
                    # Filesystem volumes require a usable shell.
                    if volume_target.mode == "filesystem":
                        shell = kubecli.get_pod_shell(candidate_pod_name,namespace,volume_target.container_name)
                        if shell is None:
                            logging.warning("Container '%s' in pod '%s' has no usable shell; trying the next pod",volume_target.container_name,candidate_pod_name)
                            continue

                    selected_pod = pod
                    selected_pod_name = candidate_pod_name
                    selected_target = volume_target
                    selected_shell = shell
                    break
                
                if selected_pod is None:
                    resource = f"PVC '{pvc_name}'" if pvc_name else f"pod '{pod_name}'"
                    logging.error("No usable pod found for %s in namespace '%s'",resource,namespace,)
                    return 1
            
                pvc_name = selected_target.pvc_name
                logging.info("Selected pod '%s' for PVC '%s' (mode=%s, container=%s, path=%s)",selected_pod_name, pvc_name, selected_target.mode,selected_target.container_name, selected_target.path,)
                
                def register_rollback(data):
                    encoded_data = encode_rollback_data(data)
                    success = self.rollback_handler.set_rollback_callable(
                        self.rollback_temp_file,
                        RollbackContent(namespace=namespace, resource_identifier=encoded_data),
                    )
                    if not success:
                        raise RuntimeError(
                            "PvcScenarioPlugin Failed to register rollback context. Aborting scenario."
                        )
                
                result, _ = fill_filesystem_pvc(
                    kubecli=kubecli,
                    pod_name=selected_pod_name,
                    namespace=namespace,
                    pvc_name=pvc_name,
                    target_fill_percentage=target_fill_percentage,
                    duration=duration,
                    block_size=block_size,
                    volume_target=selected_target,
                    on_file_created=register_rollback,
                    pod=selected_pod,
                    shell=selected_shell
                )
                return result
        except Exception as e:
            logging.error("PvcScenarioPlugin exiting due to Exception %s" % e)
            return 1
        else:
            return 0

    @staticmethod
    def rollback_temp_file(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        from krkn.utils.filesystem_pvc import rollback_filesystem_fill
        rollback_filesystem_fill(
            rollback_content.resource_identifier,
            lib_telemetry,
        )

    def get_scenario_types(self) -> list[str]:
        return ["pvc_scenarios"]
