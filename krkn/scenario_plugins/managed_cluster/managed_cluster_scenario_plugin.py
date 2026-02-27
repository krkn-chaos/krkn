import logging
import time

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.managed_cluster.common_functions import get_managedcluster
from krkn.scenario_plugins.managed_cluster.scenarios import Scenarios


class ManagedClusterScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        with open(scenario, "r") as f:
            scenario = yaml.full_load(f)
            for managedcluster_scenario in scenario["managedcluster_scenarios"]:
                managedcluster_scenario_object = Scenarios(
                    lib_telemetry.get_lib_kubernetes()
                )
                if managedcluster_scenario["actions"]:
                    for action in managedcluster_scenario["actions"]:
                        start_time = int(time.time())
                        try:
                            self.inject_managedcluster_scenario(
                                action,
                                managedcluster_scenario,
                                managedcluster_scenario_object,
                                lib_telemetry.get_lib_kubernetes(),
                            )
                        except Exception as e:
                            logging.error(
                                "ManagedClusterScenarioPlugin exiting due to Exception %s"
                                % e
                            )
                            return 1
                        else:
                            return 0

    def inject_managedcluster_scenario(
        self,
        action,
        managedcluster_scenario,
        managedcluster_scenario_object,
        kubecli: KrknKubernetes,
    ):
        # Get the managedcluster scenario configurations
        run_kill_count = get_yaml_item_value(managedcluster_scenario, "runs", 1)
        instance_kill_count = get_yaml_item_value(
            managedcluster_scenario, "instance_count", 1
        )
        managedcluster_name = get_yaml_item_value(
            managedcluster_scenario, "managedcluster_name", ""
        )
        label_selector = get_yaml_item_value(
            managedcluster_scenario, "label_selector", ""
        )
        timeout = get_yaml_item_value(managedcluster_scenario, "timeout", 120)
        # Get the managedcluster to apply the scenario
        if managedcluster_name:
            managedcluster_name_list = managedcluster_name.split(",")
        else:
            managedcluster_name_list = [managedcluster_name]
        for single_managedcluster_name in managedcluster_name_list:
            managedclusters = get_managedcluster(
                single_managedcluster_name, label_selector, instance_kill_count, kubecli
            )
            for single_managedcluster in managedclusters:
                if action == "managedcluster_start_scenario":
                    managedcluster_scenario_object.managedcluster_start_scenario(
                        run_kill_count, single_managedcluster, timeout
                    )
                elif action == "managedcluster_stop_scenario":
                    managedcluster_scenario_object.managedcluster_stop_scenario(
                        run_kill_count, single_managedcluster, timeout
                    )
                elif action == "managedcluster_stop_start_scenario":
                    managedcluster_scenario_object.managedcluster_stop_start_scenario(
                        run_kill_count, single_managedcluster, timeout
                    )
                elif action == "managedcluster_termination_scenario":
                    managedcluster_scenario_object.managedcluster_termination_scenario(
                        run_kill_count, single_managedcluster, timeout
                    )
                elif action == "managedcluster_reboot_scenario":
                    managedcluster_scenario_object.managedcluster_reboot_scenario(
                        run_kill_count, single_managedcluster, timeout
                    )
                elif action == "stop_start_klusterlet_scenario":
                    managedcluster_scenario_object.stop_start_klusterlet_scenario(
                        run_kill_count, single_managedcluster, timeout
                    )
                elif action == "start_klusterlet_scenario":
                    managedcluster_scenario_object.stop_klusterlet_scenario(
                        run_kill_count, single_managedcluster, timeout
                    )
                elif action == "stop_klusterlet_scenario":
                    managedcluster_scenario_object.stop_klusterlet_scenario(
                        run_kill_count, single_managedcluster, timeout
                    )
                elif action == "managedcluster_crash_scenario":
                    managedcluster_scenario_object.managedcluster_crash_scenario(
                        run_kill_count, single_managedcluster, timeout
                    )
                else:
                    logging.info(
                        "There is no managedcluster action that matches %s, skipping scenario"
                        % action
                    )

    def get_managedcluster_scenario_object(self, kubecli: KrknKubernetes):
        return Scenarios(kubecli)

    def get_scenario_types(self) -> list[str]:
        return ["managedcluster_scenarios"]
