from typing import List, Tuple

from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class WrongModuleScenarioPlugin(AbstractScenarioPlugin):
    def get_scenario_type(self) -> str:
        pass

    def run(
        self,
        scenarios_list: List[str],
        config: str,
        failed_post_scenarios: List[str],
        wait_duration: int,
        lib_telemetry: KrknTelemetryOpenshift,
        run_uuid: str,
        telemetry_request_id: str,
    ) -> Tuple[List[str], ScenarioTelemetry]:
        pass
