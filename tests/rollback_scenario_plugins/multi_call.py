import time

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.rollback_scenario_plugin.rollback_callable_tracer import RollbackCallableTracer

from tests.rollback_scenario_plugins_config import TEST_ROLLBACK_VERSIONS_OUTPUT


class MultiCallRollbackScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
        rollback_callable_tracer: RollbackCallableTracer = RollbackCallableTracer(
            f"{TEST_ROLLBACK_VERSIONS_OUTPUT}/multi_call"
        ),
    ) -> int:
        for i in range(3):
            rollback_callable_tracer.set_rollback_callable(
                self.rollback_callable,
                arguments=(lib_telemetry, scenario_telemetry, f"{run_uuid}_{i + 1}"),
                kwargs={"scenario": scenario, "krkn_config": krkn_config},
            )
            time.sleep(1)  # Simulate some delay between calls
        return 0

    def get_scenario_types(self) -> list[str]:
        """
        Returns the scenario types that this plugin supports.

        :return: a list of scenario types
        """
        return ["multi_call_rollback_scenario"]

    @staticmethod
    def rollback_callable(
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
    ):
        """
        Rollback callable that needs krkn library and will be called multiple times.
        This should generate multiple version files.
        """
        print(f"Rollback called for run {run_uuid} with scenario {scenario}.")
        print(f"lib_telemetry: {lib_telemetry}")
        print(f"scenario_telemetry: {scenario_telemetry}")
        print(f"Krkn config: {krkn_config}")
        # Simulate a rollback operation
        # In a real scenario, this would contain logic to revert changes made during the scenario execution.
        print("Rollback operation completed successfully.")
