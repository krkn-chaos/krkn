import dataclasses
import json
import logging
from os.path import abspath
from typing import List, Any, Dict
from krkn.scenario_plugins.native.run_python_plugin import run_python_file
from krkn.scenario_plugins.native.network.ingress_shaping import network_chaos
from krkn.scenario_plugins.native.pod_network_outage.pod_network_outage_plugin import (
    pod_outage,
)
from krkn.scenario_plugins.native.pod_network_outage.pod_network_outage_plugin import (
    pod_egress_shaping,
)
from krkn.scenario_plugins.native.pod_network_outage.pod_network_outage_plugin import (
    pod_ingress_shaping,
)
from arcaflow_plugin_sdk import schema, serialization, jsonschema

@dataclasses.dataclass
class PluginStep:
    schema: schema.StepSchema
    error_output_ids: List[str]

    def render_output(self, output_id: str, output_data) -> str:
        return json.dumps(
            {
                "output_id": output_id,
                "output_data": self.schema.outputs[output_id].serialize(output_data),
            },
            indent="\t",
        )


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
                raise Exception("Duplicate step ID: {}".format(step.schema.id))
            self.steps_by_id[step.schema.id] = step

    def unserialize_scenario(self, file: str) -> Any:
        return serialization.load_from_file(abspath(file))

    def run(self, file: str, kubeconfig_path: str, run_uuid: str):
        """
        Run executes a series of steps
        """
        data = self.unserialize_scenario(abspath(file))
        if not isinstance(data, list):
            raise Exception(
                "Invalid scenario configuration file: {} expected list, found {}".format(
                    file, type(data).__name__
                )
            )
        i = 0
        for entry in data:
            if not isinstance(entry, dict):
                raise Exception(
                    "Invalid scenario configuration file: {} expected a list of dict's, found {} on step {}".format(
                        file, type(entry).__name__, i
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
                        i, file, entry["id"], ", ".join(self.steps_by_id.keys())
                    )
                )
            step = self.steps_by_id[entry["id"]]
            unserialized_input = step.schema.input.unserialize(entry["config"])
            if "kubeconfig_path" in step.schema.input.properties:
                unserialized_input.kubeconfig_path = kubeconfig_path
            output_id, output_data = step.schema(
                params=unserialized_input, run_id=run_uuid
            )

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
            "items": {"oneOf": []},
        }
        for step_id in self.steps_by_id.keys():
            step = self.steps_by_id[step_id]
            step_input = jsonschema.step_input(step.schema)
            del step_input["$id"]
            del step_input["$schema"]
            del step_input["title"]
            del step_input["description"]
            result["items"]["oneOf"].append(
                {
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
                    ],
                }
            )
        return json.dumps(result, indent="\t")


PLUGINS = Plugins(
    [
        PluginStep(run_python_file, ["error"]),
        PluginStep(network_chaos, ["error"]),
        PluginStep(pod_outage, ["error"]),
        PluginStep(pod_egress_shaping, ["error"]),
        PluginStep(pod_ingress_shaping, ["error"]),
    ]
)
