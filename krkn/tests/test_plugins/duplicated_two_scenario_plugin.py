from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class DuplicatedTwoScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenarios_list: list[str],
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
    ) -> tuple[list[str], list[ScenarioTelemetry]]:
        pass

    def get_scenario_type(self) -> str:
        return "duplicated_scenario"
