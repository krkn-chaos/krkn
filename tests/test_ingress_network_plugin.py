import unittest
import logging
from arcaflow_plugin_sdk import plugin

from krkn.scenario_plugins.native.network import ingress_shaping
from krkn.scenario_plugins.types import ExecutionType


class NetworkScenariosTest(unittest.TestCase):

    def test_serialization(self):
        plugin.test_object_serialization(
            ingress_shaping.NetworkScenarioConfig(
                node_interface_name={"foo": ["bar"]},
                network_params={
                    "latency": "50ms",
                    "loss": "0.02",
                    "bandwidth": "100mbit",
                },
            ),
            self.fail,
        )
        plugin.test_object_serialization(
            ingress_shaping.NetworkScenarioSuccessOutput(
                filter_direction="ingress",
                test_interfaces={"foo": ["bar"]},
                network_parameters={
                    "latency": "50ms",
                    "loss": "0.02",
                    "bandwidth": "100mbit",
                },
                execution_type=ExecutionType.PARALLEL.value,
            ),
            self.fail,
        )
        plugin.test_object_serialization(
            ingress_shaping.NetworkScenarioErrorOutput(
                error="Hello World",
            ),
            self.fail,
        )

    def test_network_chaos(self):
        output_id, output_data = ingress_shaping.network_chaos(
            params=ingress_shaping.NetworkScenarioConfig(
                label_selector="node-role.kubernetes.io/control-plane",
                instance_count=1,
                network_params={
                    "latency": "50ms",
                    "loss": "0.02",
                    "bandwidth": "100mbit",
                },
            ),
            run_id="network-shaping-test",
        )
        if output_id == "error":
            logging.error(output_data.error)
            self.fail(
                "The network chaos scenario did not complete successfully "
                "because an error/exception occurred"
            )


if __name__ == "__main__":
    unittest.main()
