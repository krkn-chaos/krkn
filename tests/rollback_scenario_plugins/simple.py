import logging

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.rollback_scenario_plugin.rollback_callable_tracer import RollbackCallableTracer

from tests.rollback_scenario_plugins_config import TEST_ROLLBACK_VERSIONS_OUTPUT


class SimpleRollbackScenarioPlugin(AbstractScenarioPlugin):
    """
    Mock implementation of RollbackScenarioPlugin for testing purposes.
    This plugin does not perform any actual rollback operations.
    """

    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
        rollback_callable_tracer: RollbackCallableTracer = RollbackCallableTracer(
            f"{TEST_ROLLBACK_VERSIONS_OUTPUT}/simple"
        ),
    ) -> int:
        logging.info(f"Setting rollback callable for run {run_uuid} with scenario {scenario}.")
        rollback_callable_tracer.set_rollback_callable(
            self.rollback_callable,
            arguments=(run_uuid),
            kwargs={"scenario": scenario, "krkn_config": krkn_config},
        )
        return 0

    def get_scenario_types(self) -> list[str]:
        """
        Returns the scenario types that this plugin supports.

        :return: a list of scenario types
        """
        return ["simple_rollback_scenario"]

    @staticmethod
    def rollback_callable(run_uuid: str, scenario: str, krkn_config: dict[str, any]):
        """
        Simple rollback callable that simulates a rollback operation.
        """
        print(f"Rollback called for run {run_uuid} with scenario {scenario}.")
        print(f"Krkn config: {krkn_config}")
        # Simulate a rollback operation
        # In a real scenario, this would contain logic to revert changes made during the scenario execution.
        print("Rollback operation completed successfully.")
