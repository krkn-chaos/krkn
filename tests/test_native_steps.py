"""Contract tests for native scenario inputs."""

import json
import tempfile
import unittest
from pathlib import Path

from krkn.scenario_plugins.native.plugins import PLUGINS


class NativeStepContractTest(unittest.TestCase):
    def test_pod_outage_defaults_and_independent_lists(self):
        input_schema = PLUGINS.steps_by_id["pod_network_outage"].schema.input
        first = input_schema.unserialize({"namespace": "demo", "pod_name": "pod-a"})
        second = input_schema.unserialize({"namespace": "demo", "label_selector": "app=a"})
        self.assertEqual(first.direction, ["ingress", "egress"])
        self.assertEqual(first.ingress_ports, [])
        first.ingress_ports.append(80)
        self.assertEqual(second.ingress_ports, [])

    def test_selector_and_namespace_validation(self):
        pod = PLUGINS.steps_by_id["pod_network_outage"].schema.input
        node = PLUGINS.steps_by_id["network_chaos"].schema.input
        for data in (
            {},
            {"namespace": ""},
            {"namespace": "demo"},
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                pod.unserialize(data)
        with self.assertRaises(ValueError):
            node.unserialize({})
        self.assertEqual(
            node.unserialize({"node_interface_name": {"node-a": ["eth0"]}}).node_interface_name,
            {"node-a": ["eth0"]},
        )
        self.assertEqual(node.unserialize({"label_selector": ""}).label_selector, "")
        self.assertEqual(node.unserialize({"node_interface_name": {}}).node_interface_name, {})
        self.assertIsNone(
            node.unserialize({"node_interface_name": None, "label_selector": "app=a"})
            .node_interface_name
        )
        self.assertEqual(pod.unserialize({"namespace": "demo", "pod_name": ""}).pod_name, "")

    def test_types_ranges_and_unknown_fields(self):
        schema = PLUGINS.steps_by_id["pod_network_outage"].schema.input
        base = {"namespace": "demo", "pod_name": "pod-a"}
        for extra in (
            {"test_duration": 0},
            {"instance_count": "two"},
            {"ingress_ports": ["eighty"]},
            {"unexpected": True},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                schema.unserialize({**base, **extra})
        self.assertEqual(schema.unserialize({**base, "image": None}).image,
                         schema.unserialize(base).image)

    def test_both_pod_shaping_steps_accept_existing_input_shape(self):
        for step_id in ("pod_egress_shaping", "pod_ingress_shaping"):
            with self.subTest(step_id=step_id):
                input_schema = PLUGINS.steps_by_id[step_id].schema.input
                params = input_schema.unserialize({
                    "namespace": "demo",
                    "label_selector": "app=a",
                    "network_params": {"latency": "50ms"},
                })
                self.assertEqual(params.network_params, {"latency": "50ms"})
                self.assertEqual(params.instance_count, 1)
                with self.assertRaises(ValueError):
                    input_schema.unserialize({"namespace": "demo", "network_params": {}})

    def test_yaml_input_and_json_output_contract(self):
        step = PLUGINS.steps_by_id["run_python"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.yaml"
            path.write_text("- id: run_python\n  config:\n    filename: /tmp/script.py\n", encoding="utf-8")
            data = PLUGINS.unserialize_scenario(str(path))
        self.assertEqual(data[0]["id"], "run_python")
        params = step.schema.input.unserialize(data[0]["config"])
        self.assertEqual(params.filename, "/tmp/script.py")
        rendered = step.render_output(
            "error",
            step.schema.outputs["error"].output_type(1, "", "failed"),
        )
        self.assertEqual(
            json.loads(rendered),
            {"output_id": "error", "output_data": {"exit_code": 1, "stdout": "", "stderr": "failed"}},
        )

    def test_json_schema_describes_required_fields_and_constraints(self):
        document = json.loads(PLUGINS.json_schema())
        steps = {item["properties"]["id"]["const"]: item["properties"]["config"]
                 for item in document["items"]["oneOf"]}
        self.assertEqual(len(steps), 5)
        self.assertIn("namespace", steps["pod_network_outage"]["required"])
        self.assertEqual(
            steps["pod_network_outage"]["properties"]["namespace"]["minLength"], 1
        )
        self.assertEqual(
            steps["network_chaos"]["properties"]["test_duration"]["minimum"], 1
        )
        self.assertIn("allOf", steps["network_chaos"])


if __name__ == "__main__":
    unittest.main()
