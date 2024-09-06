import dataclasses
import json
import logging
from os.path import abspath
from typing import List, Dict, Any
import time

from arcaflow_plugin_sdk import schema, serialization, jsonschema
from arcaflow_plugin_kill_pod import kill_pods, wait_for_pods
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.k8s.pods_monitor_pool import PodsMonitorPool

import kraken.plugins.node_scenarios.vmware_plugin as vmware_plugin
import kraken.plugins.node_scenarios.ibmcloud_plugin as ibmcloud_plugin
from kraken import utils
from kraken.plugins.run_python_plugin import run_python_file
from kraken.plugins.network.ingress_shaping import network_chaos
from kraken.plugins.pod_network_outage.pod_network_outage_plugin import pod_outage
from kraken.plugins.pod_network_outage.pod_network_outage_plugin import pod_egress_shaping
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from kraken.plugins.pod_network_outage.pod_network_outage_plugin import pod_ingress_shaping
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.utils.functions import log_exception


@dataclasses.dataclass
class PluginStep:
    schema: schema.StepSchema
    error_output_ids: List[str]

    def render_output(self, output_id: str, output_data) -> str:
        return json.dumps({
            "output_id": output_id,
            "output_data": self.schema.outputs[output_id].serialize(output_data),
        }, indent='\t')


class Plugins:
    """
    Plugins is a class that can run plugins sequentially. The output is rendered to the standard output and the process
    is aborted if a step fails.
    """
    steps_by_id: Dict[str, PluginStep]

    def __init__(self, steps: List[PluginStep]):
        self.steps_by_id = dict()
        for step in steps:
            if step.schema.id in self.steps_by_id:
                raise Exception(
                    "Duplicate step ID: {}".format(step.schema.id)
                )
            self.steps_by_id[step.schema.id] = step

    def unserialize_scenario(self, file: str) -> Any:
        return serialization.load_from_file(abspath(file))

    def run(self, file: str, kubeconfig_path: str, kraken_config: str, run_uuid:str):
        """
        Run executes a series of steps
        """
        data = self.unserialize_scenario(abspath(file))
        if not isinstance(data, list):
            raise Exception(
                "Invalid scenario configuration file: {} expected list, found {}".format(file, type(data).__name__)
            )
        i = 0
        for entry in data:
            if not isinstance(entry, dict):
                raise Exception(
                    "Invalid scenario configuration file: {} expected a list of dict's, found {} on step {}".format(
                        file,
                        type(entry).__name__,
                        i
                    )
                )
            if "id" not in entry:
                raise Exception(
                    "Invalid scenario configuration file: {} missing 'id' field on step {}".format(
                        file,
                        i,
                    )
                )
            if "config" not in entry:
                raise Exception(
                    "Invalid scenario configuration file: {} missing 'config' field on step {}".format(
                        file,
                        i,
                    )
                )

            if entry["id"] not in self.steps_by_id:
                raise Exception(
                    "Invalid step {} in {} ID: {} expected one of: {}".format(
                        i,
                        file,
                        entry["id"],
                        ', '.join(self.steps_by_id.keys())
                    )
                )
            step = self.steps_by_id[entry["id"]]
            unserialized_input = step.schema.input.unserialize(entry["config"])
            if "kubeconfig_path" in step.schema.input.properties:
                unserialized_input.kubeconfig_path = kubeconfig_path
            if "kraken_config" in step.schema.input.properties:
                unserialized_input.kraken_config = kraken_config
            output_id, output_data = step.schema(params=unserialized_input, run_id=run_uuid)

            logging.info(step.render_output(output_id, output_data) + "\n")
            if output_id in step.error_output_ids:
                raise Exception(
                    "Step {} in {} ({}) failed".format(i, file, step.schema.id)
                )
            i = i + 1

    def json_schema(self):
        """
        This function generates a JSON schema document and renders it from the steps passed.
        """
        result = {
            "$id": "https://github.com/redhat-chaos/krkn/",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Kraken Arcaflow scenarios",
            "description": "Serial execution of Arcaflow Python plugins. See https://github.com/arcaflow for details.",
            "type": "array",
            "minContains": 1,
            "items": {
                "oneOf": [

                ]
            }
        }
        for step_id in self.steps_by_id.keys():
            step = self.steps_by_id[step_id]
            step_input = jsonschema.step_input(step.schema)
            del step_input["$id"]
            del step_input["$schema"]
            del step_input["title"]
            del step_input["description"]
            result["items"]["oneOf"].append({
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "const": step_id,
                    },
                    "config": step_input,
                },
                "required": [
                    "id",
                    "config",
                ]
            })
        return json.dumps(result, indent="\t")


PLUGINS = Plugins(
    [
        PluginStep(
            kill_pods,
            [
                "error",
            ]
        ),
        PluginStep(
            wait_for_pods,
            [
                "error"
            ]
        ),
        PluginStep(
            run_python_file,
            [
                "error"
            ]
        ),
        PluginStep(
            vmware_plugin.node_start,
            [
                "error"
            ]
        ),
        PluginStep(
            vmware_plugin.node_stop,
            [
                "error"
            ]
        ),
        PluginStep(
            vmware_plugin.node_reboot,
            [
                "error"
            ]
        ),
        PluginStep(
            vmware_plugin.node_terminate,
            [
                "error"
            ]
        ),
        PluginStep(
            ibmcloud_plugin.node_start,
            [
                "error"
            ]
        ),
        PluginStep(
            ibmcloud_plugin.node_stop,
            [
                "error"
            ]
        ),
        PluginStep(
            ibmcloud_plugin.node_reboot,
            [
                "error"
            ]
        ),
        PluginStep(
            ibmcloud_plugin.node_terminate,
            [
                "error"
            ]
        ),
        PluginStep(
            network_chaos,
            [
                "error"
            ]
        ),        
        PluginStep(
            pod_outage,
            [
                "error"
            ]
        ),
         PluginStep(
            pod_egress_shaping,
            [
                "error"
            ]
        ),
         PluginStep(
            pod_ingress_shaping,
            [
                "error"
            ]
        )                  
    ]
)


def run(scenarios: List[str],
        kubeconfig_path: str,
        kraken_config: str,
        failed_post_scenarios: List[str],
        wait_duration: int,
        telemetry: KrknTelemetryKubernetes,
        kubecli: KrknKubernetes,
        run_uuid: str
        ) -> (List[str], list[ScenarioTelemetry]):

    scenario_telemetries: list[ScenarioTelemetry] = []
    for scenario in scenarios:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = scenario
        scenario_telemetry.start_timestamp = time.time()
        parsed_scenario_config = telemetry.set_parameters_base64(scenario_telemetry, scenario)
        logging.info('scenario ' + str(scenario))
        pool = PodsMonitorPool(kubecli)
        kill_scenarios = [kill_scenario for kill_scenario in PLUGINS.unserialize_scenario(scenario) if kill_scenario["id"] == "kill-pods"]

        try:
            start_monitoring(pool, kill_scenarios)
            PLUGINS.run(scenario, kubeconfig_path, kraken_config, run_uuid)
            result = pool.join()
            scenario_telemetry.affected_pods = result
            if result.error:
                raise Exception(f"unrecovered pods: {result.error}")

        except Exception as e:
            logging.error(f"scenario exception: {str(e)}")
            scenario_telemetry.exit_status = 1
            pool.cancel()
            failed_post_scenarios.append(scenario)
            log_exception(scenario)
        else:
            scenario_telemetry.exit_status = 0
            logging.info("Waiting for the specified duration: %s" % (wait_duration))
            time.sleep(wait_duration)
        scenario_telemetry.end_timestamp = time.time()
        utils.populate_cluster_events(scenario_telemetry,
                                      parsed_scenario_config,
                                      telemetry.kubecli,
                                      int(scenario_telemetry.start_timestamp),
                                      int(scenario_telemetry.end_timestamp))
        scenario_telemetries.append(scenario_telemetry)

    return failed_post_scenarios, scenario_telemetries


def start_monitoring(pool: PodsMonitorPool, scenarios: list[Any]):
    for kill_scenario in scenarios:
        recovery_time = kill_scenario["config"]["krkn_pod_recovery_time"]
        if ("namespace_pattern" in kill_scenario["config"] and
                "label_selector" in kill_scenario["config"]):
            namespace_pattern = kill_scenario["config"]["namespace_pattern"]
            label_selector = kill_scenario["config"]["label_selector"]
            pool.select_and_monitor_by_namespace_pattern_and_label(
                namespace_pattern=namespace_pattern,
                label_selector=label_selector,
                max_timeout=recovery_time)
            logging.info(
                f"waiting {recovery_time} seconds for pod recovery, "
                f"pod label selector: {label_selector} namespace pattern: {namespace_pattern}")

        elif ("namespace_pattern" in kill_scenario["config"] and
              "name_pattern" in kill_scenario["config"]):
            namespace_pattern = kill_scenario["config"]["namespace_pattern"]
            name_pattern = kill_scenario["config"]["name_pattern"]
            pool.select_and_monitor_by_name_pattern_and_namespace_pattern(pod_name_pattern=name_pattern,
                                                                          namespace_pattern=namespace_pattern,
                                                                          max_timeout=recovery_time)
            logging.info(f"waiting {recovery_time} seconds for pod recovery, "
                         f"pod name pattern: {name_pattern} namespace pattern: {namespace_pattern}")
        else:
            raise Exception(f"impossible to determine monitor parameters, check {kill_scenario} configuration")
