import logging

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())


class SimpleRollbackScenarioPlugin(AbstractScenarioPlugin):
    """
    Mock implementation of RollbackScenarioPlugin for testing purposes.
    This plugin does not perform any actual rollback operations.
    """

    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        logger.info(
            f"Setting rollback callable for run {run_uuid} with scenario {scenario}."
        )
        logger.debug(f"Krkn config: {krkn_config}")
        self.rollback_handler.set_rollback_callable(
            self.rollback_callable,
            RollbackContent(
                resource_identifier=run_uuid,
            ),
        )
        logger.info("Rollback callable set successfully.")
        print("Rollback callable has been set for the scenario.")
        return 0

    def get_scenario_types(self) -> list[str]:
        """
        Returns the scenario types that this plugin supports.
        :return: a list of scenario types
        """
        return ["simple_rollback_scenario"]

    @staticmethod
    def rollback_callable(
        rollback_context: RollbackContent, lib_telemetry: KrknTelemetryOpenshift
    ):
        """
        Simple rollback callable that simulates a rollback operation.
        """
        run_uuid = rollback_context.resource_identifier

        print(f"Rollback called for run {run_uuid}.")
        # Simulate a rollback operation
        # In a real scenario, this would contain logic to revert changes made during the scenario execution.
        print("Rollback operation completed successfully.")
