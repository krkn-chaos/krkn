from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.native.plugins import PLUGINS
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from typing import Any
import logging


class NativeScenarioPlugin(AbstractScenarioPlugin):

    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:

        try:
            PLUGINS.run(
                scenario,
                lib_telemetry.get_lib_kubernetes().get_kubeconfig_path(),
                run_uuid,
            )

        except Exception as e:
            logging.error("NativeScenarioPlugin exiting due to Exception %s" % e)
            return 1
        else:
            return 0

    def get_scenario_types(self) -> list[str]:
        return [
            "pod_network_scenarios",
            "ingress_node_scenarios"
        ]
