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
import krkn_lib.utils
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from tzlocal.unix import get_localzone
import logging

def populate_cluster_events(
    krkn_config: dict,
    scenario_config: dict,
    kubecli: KrknKubernetes,
    start_timestamp: int,
    end_timestamp: int,
):
    events = []
    namespaces = __retrieve_namespaces(scenario_config, kubecli)

    if len(namespaces) == 0:
        events.extend(
            kubecli.collect_and_parse_cluster_events(
                start_timestamp, end_timestamp, str(get_localzone())
            )
        )
    else:
        for namespace in namespaces:
            events.extend(
                kubecli.collect_and_parse_cluster_events(
                    start_timestamp,
                    end_timestamp,
                    str(get_localzone()),
                    namespace=namespace,
                )
            )
    archive_path = krkn_config["telemetry"]["archive_path"]
    file_path = archive_path + "/events.json"
    with open(file_path, "w+") as f:
        f.write("\n".join(str(item) for item in events))
    logging.info(f'Find cluster events in file {file_path}' )
    


def collect_and_put_ocp_logs(
    telemetry_ocp: KrknTelemetryOpenshift,
    scenario_config: dict,
    request_id: str,
    start_timestamp: int,
    end_timestamp: int,
):
    if (
        telemetry_ocp.get_telemetry_config()
        and telemetry_ocp.get_telemetry_config()["enabled"]
        and telemetry_ocp.get_telemetry_config()["logs_backup"]
        and not telemetry_ocp.get_lib_kubernetes().is_kubernetes()
    ):
        namespaces = __retrieve_namespaces(
            scenario_config, telemetry_ocp.get_lib_kubernetes()
        )
        if len(namespaces) > 0:
            for namespace in namespaces:
                telemetry_ocp.put_ocp_logs(
                    request_id,
                    telemetry_ocp.get_telemetry_config(),
                    start_timestamp,
                    end_timestamp,
                    namespace,
                )
        else:
            telemetry_ocp.put_ocp_logs(
                request_id,
                telemetry_ocp.get_telemetry_config(),
                start_timestamp,
                end_timestamp,
            )


def __retrieve_namespaces(scenario_config: dict, kubecli: KrknKubernetes) -> set[str]:
    namespaces = list()
    namespaces.extend(krkn_lib.utils.deep_get_attribute("namespace", scenario_config))
    namespace_patterns = krkn_lib.utils.deep_get_attribute(
        "namespace_pattern", scenario_config
    )
    for pattern in namespace_patterns:
        namespaces.extend(kubecli.list_namespaces_by_regex(pattern))
    return set(namespaces)
