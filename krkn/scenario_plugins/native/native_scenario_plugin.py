from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.native.plugins import PLUGINS
from krkn_lib.k8s.pods_monitor_pool import PodsMonitorPool
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from typing import Any
import logging


class NativeScenarioPlugin(AbstractScenarioPlugin):

    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        pool = PodsMonitorPool(lib_telemetry.get_lib_kubernetes())
        kill_scenarios = [
            kill_scenario
            for kill_scenario in PLUGINS.unserialize_scenario(scenario)
            if kill_scenario["id"] == "kill-pods"
        ]

        try:
            self.start_monitoring(pool, kill_scenarios)
            PLUGINS.run(
                scenario,
                lib_telemetry.get_lib_kubernetes().get_kubeconfig_path(),
                krkn_config,
                run_uuid,
            )
            result = pool.join()
            scenario_telemetry.affected_pods = result
            if result.error:
                logging.error(f"NativeScenarioPlugin unrecovered pods: {result.error}")
                return 1

        except Exception as e:
            logging.error("NativeScenarioPlugin exiting due to Exception %s" % e)
            pool.cancel()
            return 1
        else:
            return 0

    def get_scenario_types(self) -> list[str]:
        return [
            "pod_disruption_scenarios",
            "vmware_node_scenarios",
            "ibmcloud_node_scenarios",
            "plugin_scenarios",
        ]

    def start_monitoring(self, pool: PodsMonitorPool, scenarios: list[Any]):
        for kill_scenario in scenarios:
            recovery_time = kill_scenario["config"]["krkn_pod_recovery_time"]
            if (
                "namespace_pattern" in kill_scenario["config"]
                and "label_selector" in kill_scenario["config"]
            ):
                namespace_pattern = kill_scenario["config"]["namespace_pattern"]
                label_selector = kill_scenario["config"]["label_selector"]
                pool.select_and_monitor_by_namespace_pattern_and_label(
                    namespace_pattern=namespace_pattern,
                    label_selector=label_selector,
                    max_timeout=recovery_time,
                )
                logging.info(
                    f"waiting {recovery_time} seconds for pod recovery, "
                    f"pod label selector: {label_selector} namespace pattern: {namespace_pattern}"
                )

            elif (
                "namespace_pattern" in kill_scenario["config"]
                and "name_pattern" in kill_scenario["config"]
            ):
                namespace_pattern = kill_scenario["config"]["namespace_pattern"]
                name_pattern = kill_scenario["config"]["name_pattern"]
                pool.select_and_monitor_by_name_pattern_and_namespace_pattern(
                    pod_name_pattern=name_pattern,
                    namespace_pattern=namespace_pattern,
                    max_timeout=recovery_time,
                )
                logging.info(
                    f"waiting {recovery_time} seconds for pod recovery, "
                    f"pod name pattern: {name_pattern} namespace pattern: {namespace_pattern}"
                )
            else:
                raise Exception(
                    f"impossible to determine monitor parameters, check {kill_scenario} configuration"
                )
