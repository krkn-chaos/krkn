import time

from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import log_exception

from krkn import utils
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


# Each plugin must extend the AbstractScenarioPlugin abstract class
# and implement its methods. Also the naming conventions must be respected
# you can refer to the documentation for the details:
# https://github.com/krkn-chaos/krkn/blob/main/docs/scenario_plugin_api.md
class ExampleScenarioPlugin(AbstractScenarioPlugin):

    # entrypoint method for each ScenarioPlugin invoked by the plugin loader
    def run(
        self,
        run_uuid: str,
        scenarios_list: list[str],
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
    ) -> tuple[list[str], list[ScenarioTelemetry]]:
        # return values
        scenario_telemetries = list[ScenarioTelemetry]()
        failed_post_scenarios = []

        # the duration in seconds that is usually waited between
        # each scenario to give time to cluster to recover
        wait_duration = krkn_config["tunings"]["wait_duration"]

        # game loop
        for scenario in scenarios_list:
            # the telemetry object for each scenario in the scenario
            # list

            scenario_telemetry = ScenarioTelemetry()
            scenario_telemetry.scenario = scenario
            scenario_telemetry.start_timestamp = time.time()

            # all the parameters set in the scenario config file are base64 serialized
            # in the ScenarioTelemetry object.
            parsed_scenario_config = lib_telemetry.set_parameters_base64(
                scenario_telemetry, scenario
            )
            try:
                # The scenario logic for each scenario must be placed
                # here. A try-except might be needed to catch exception
                # that may happen in this section and report failing scenarios
                # this pattern is not mandatory and could be done in several different
                # ways, the purpose is to outline the concept of the multiple scenarios
                # for each scenario type and how to populate the `failed_post_scenarios`
                # list returned by the run method.

                # krkn-lib KrknKubernetes object containing all the kubernetes primitives
                # can be retrieved by the KrknTelemetryOpenshift object
                krkn_kubernetes = lib_telemetry.get_lib_kubernetes()

                # krkn-lib KrknOpenshift object containing all the OCP primitives
                # can be retrieved by the KrknTelemetryOpenshift object
                krkn_openshift = lib_telemetry.get_lib_ocp()

                # wait between scenarios
                time.sleep(wait_duration)

                # if the scenario succeeds the telemetry exit status is 0
                scenario_telemetry.exit_status = 0
            except Exception as e:
                # if the scenario fails the telemetry exit status is 1
                scenario_telemetry.exit_status = 1
                self.fail_scenario_telemetry(scenario_telemetry)
                log_exception(scenario)

            scenario_telemetry.end_timestamp = time.time()

            # cluster log collection
            utils.collect_and_put_ocp_logs(
                lib_telemetry,
                parsed_scenario_config,
                lib_telemetry.get_telemetry_request_id(),
                int(scenario_telemetry.start_timestamp),
                int(scenario_telemetry.end_timestamp),
            )
            # cluster event collection
            utils.populate_cluster_events(
                scenario_telemetry,
                parsed_scenario_config,
                lib_telemetry.get_lib_kubernetes(),
                int(scenario_telemetry.start_timestamp),
                int(scenario_telemetry.end_timestamp),
            )
            # append the scenario to the scenario_telemetry list
            # returned by the run method
            scenario_telemetries.append(scenario_telemetry)

        return failed_post_scenarios, scenario_telemetries

    # Reflects the scenario type defined in the config.yaml
    # in the chaos_scenarios section and to which each class
    # responds.
    def get_scenario_type(self) -> str:
        return "example_scenarios"
