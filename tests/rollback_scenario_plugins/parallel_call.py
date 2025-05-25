import time
from multiprocessing.pool import ThreadPool

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.rollback_scenario_plugin.rollback_callable_tracer import RollbackCallableTracer

from tests.rollback_scenario_plugins_config import TEST_ROLLBACK_VERSIONS_OUTPUT


class ParallelCallRollbackScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
        rollback_callable_tracer: RollbackCallableTracer = RollbackCallableTracer(
            f"{TEST_ROLLBACK_VERSIONS_OUTPUT}/parallel_call"
        ),
    ) -> int:
        # Using ThreadPool to call set_rollback_callable in parallel 4 times
        with ThreadPool(processes=4) as pool:
            # Prepare arguments for each parallel call
            args_list = [
                (
                    i + 1,
                    run_uuid,
                    lib_telemetry,
                    scenario_telemetry,
                    scenario,
                    krkn_config,
                    rollback_callable_tracer,
                )
                for i in range(4)
            ]
            # Execute in parallel
            pool.map(self._execute_parallel_call, args_list)

        return 0

    def _execute_parallel_call(self, args):
        # Unpack arguments
        (
            index,
            run_uuid,
            lib_telemetry,
            scenario_telemetry,
            scenario,
            krkn_config,
            rollback_callable_tracer,
        ) = args

        # Set rollback callable with unique run_uuid for each thread
        rollback_callable_tracer.set_rollback_callable(
            self.rollback_callable,
            arguments=(lib_telemetry, scenario_telemetry, f"{run_uuid}_parallel_{index}"),
            kwargs={"scenario": scenario, "krkn_config": krkn_config},
        )

    def get_scenario_types(self) -> list[str]:
        """
        Returns the scenario types that this plugin supports.

        :return: a list of scenario types
        """
        return ["parallel_call_rollback_scenario"]

    @staticmethod
    def rollback_callable(
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
    ):
        """
        Rollback callable that needs krkn library and will be called in parallel.
        This should generate multiple version files concurrently.
        """
        print(f"Parallel rollback called for run {run_uuid} with scenario {scenario}.")
        print(f"lib_telemetry: {lib_telemetry}")
        print(f"scenario_telemetry: {scenario_telemetry}")
        print(f"Krkn config: {krkn_config}")
        # Simulate a rollback operation
        # In a real scenario, this would contain logic to revert changes made during the scenario execution.
        print(f"Parallel rollback operation for {run_uuid} completed successfully.")
