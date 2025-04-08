import logging
import queue
import random
import threading
import time

import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosScenarioType,
    BaseNetworkChaosConfig,
)
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.network_chaos_factory import (
    NetworkChaosFactory,
)


class NetworkChaosNgScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario, "r") as file:
                scenario_config = yaml.safe_load(file)
                if not isinstance(scenario_config, list):
                    logging.error(
                        "network chaos scenario config must be a list of objects"
                    )
                    return 1
                for config in scenario_config:
                    network_chaos = NetworkChaosFactory.get_instance(config)
                    network_chaos_config = network_chaos.get_config()
                    logging.info(
                        f"running network_chaos scenario: {network_chaos_config[1].id}"
                    )
                    if network_chaos_config[0] == NetworkChaosScenarioType.Node:
                        targets = lib_telemetry.get_lib_kubernetes().list_nodes(
                            network_chaos_config[1].label_selector
                        )
                    else:
                        targets = lib_telemetry.get_lib_kubernetes().list_pods(
                            network_chaos_config[1].namespace,
                            network_chaos_config[1].label_selector,
                        )
                    if len(targets) == 0:
                        logging.warning(
                            f"no targets found for {network_chaos_config[1].id} "
                            f"network chaos scenario with selector {network_chaos_config[1].label_selector} "
                            f"with target type {network_chaos_config[0]}"
                        )

                    if network_chaos_config[1].instance_count != 0 and network_chaos_config[1].instance_count > len(targets):
                        targets = random.sample(targets, network_chaos_config[1].instance_count)

                    if network_chaos_config[1].execution == "parallel":
                        self.run_parallel(targets, network_chaos, lib_telemetry)
                    else:
                        self.run_serial(targets, network_chaos, lib_telemetry)
                    if len(config) > 1:
                        logging.info(f"waiting {network_chaos_config[1].wait_duration} seconds before running the next "
                                     f"Network Chaos NG Module")
                        time.sleep(network_chaos_config[1].wait_duration)
        except Exception as e:
            logging.error(str(e))
            return 1
        return 0

    def run_parallel(
        self,
        targets: list[str],
        module: AbstractNetworkChaosModule,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        error_queue = queue.Queue()
        threads = []
        errors = []
        for target in targets:
            thread = threading.Thread(
                target=module.run, args=[target, lib_telemetry, error_queue]
            )
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join()
        while True:
            try:
                errors.append(error_queue.get_nowait())
            except queue.Empty:
                break
        if len(errors) > 0:
            raise Exception(
                f"module {module.get_config()[1].id} execution failed: [{';'.join(errors)}]"
            )

    def run_serial(
        self,
        targets: list[str],
        module: AbstractNetworkChaosModule,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        for target in targets:
            module.run(target, lib_telemetry)

    def get_scenario_types(self) -> list[str]:
        return ["network_chaos_ng_scenarios"]
