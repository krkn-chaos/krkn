# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging

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
                    logging.error(
                        "ManagedClusterScenarioPlugin: 'actions' must be defined and non-empty in the scenario config"
                    )
                    return 1
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
