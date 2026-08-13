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
import traceback

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.k8s.pod_monitor import (
    select_and_monitor_by_namespace_pattern_and_label,
)
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.abstract_scenario_plugin import (
    AbstractScenarioPlugin,
)
from krkn.scenario_plugins.gpu_device.models.models import InputParams
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator
from krkn.utils.gpu import (
    discover_gpu_nodes,
    find_gpu_operator_pods,
    get_node_gpu_allocatable,
    validate_gpu_health_on_node,
    validate_gpu_operator_present,
    wait_for_gpu_allocatable,
)


class GpuDeviceScenarioPlugin(AbstractScenarioPlugin):

    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            kubecli = lib_telemetry.get_lib_kubernetes()

            with open(scenario, "r") as f:
                scenario_config = yaml.safe_load(f)

            for item in scenario_config:
                config = InputParams(item["config"])
                result = self._run_disruption(
                    config, kubecli, scenario_telemetry
                )
                if result != 0:
                    return 1

        except Exception as e:
            logging.error("Stack trace:\n%s", traceback.format_exc())
            logging.error(
                "GpuDeviceScenarioPlugin exiting due to exception: %s", e
            )
            return 1

        return 0

    def get_scenario_types(self) -> list[str]:
        return ["gpu_device_plugin_scenarios"]

    def _run_disruption(
        self,
        config: InputParams,
        kubecli: KrknKubernetes,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        # Pre-flight
        if not validate_gpu_operator_present(kubecli, config.namespace):
            logging.error("GPU Operator not found, aborting scenario")
            return 1

        device_plugin_pods = find_gpu_operator_pods(
            kubecli, config.namespace, config.pod_label_selector
        )
        if not device_plugin_pods:
            logging.error(
                f"no device plugin pods found with label "
                f"'{config.pod_label_selector}' in namespace "
                f"'{config.namespace}'"
            )
            return 1

        logging.info(
            f"found {len(device_plugin_pods)} device plugin pod(s): "
            f"{[p[0] for p in device_plugin_pods]}"
        )

        # Discover GPU nodes and select targets
        gpu_nodes = discover_gpu_nodes(kubecli)
        if not gpu_nodes:
            logging.error("no GPU nodes found in the cluster")
            return 1

        if config.node_selector:
            matching_nodes = kubecli.list_nodes(config.node_selector)
            gpu_nodes = [n for n in gpu_nodes if n["name"] in matching_nodes]
            if not gpu_nodes:
                logging.error(
                    f"no GPU nodes match node_selector "
                    f"'{config.node_selector}'"
                )
                return 1

        target_nodes = gpu_nodes[: config.number_of_nodes]
        target_node_names = [n["name"] for n in target_nodes]
        logging.info(f"targeting GPU nodes: {target_node_names}")

        # Match device plugin pods to target nodes
        target_pods = []
        for pod_name, pod_ns in device_plugin_pods:
            pod_info = kubecli.read_pod(pod_name, pod_ns)
            if pod_info and pod_info.spec.node_name in target_node_names:
                target_pods.append((pod_name, pod_ns))

        if not target_pods:
            logging.error(
                "no device plugin pods found on targeted GPU nodes"
            )
            return 1

        logging.info(
            f"target device plugin pods: {[p[0] for p in target_pods]}"
        )

        # Snapshot GPU allocatable counts
        gpu_snapshots = {}
        for node_info in target_nodes:
            node_name = node_info["name"]
            gpu_snapshots[node_name] = get_node_gpu_allocatable(
                kubecli, node_name
            )
            logging.info(
                f"node {node_name} GPU allocatable snapshot: "
                f"{gpu_snapshots[node_name]}"
            )

        # Pre-disruption GPU health check
        if config.validate_gpu_health:
            for node_info in target_nodes:
                node_name = node_info["name"]
                if not validate_gpu_health_on_node(kubecli, node_name, namespace=config.namespace):
                    logging.error(
                        f"pre-disruption GPU health check failed on "
                        f"node {node_name}"
                    )
                    return 1
                logging.info(
                    f"pre-disruption GPU health check passed on "
                    f"node {node_name}"
                )

        # Start monitoring for pod recovery
        future_snapshot = select_and_monitor_by_namespace_pattern_and_label(
            namespace_pattern=f"^{config.namespace}$",
            label_selector=config.pod_label_selector,
            max_timeout=config.krkn_pod_recovery_time,
            v1_client=kubecli.cli,
        )
        logging.info(
            f"monitoring device plugin pods for up to "
            f"{config.krkn_pod_recovery_time}s"
        )

        # Register rollback (once — args are invariant across pods)
        self.rollback_handler.set_rollback_callable(
            self.rollback_verify_device_plugin,
            RollbackContent(
                namespace=config.namespace,
                resource_identifier=config.pod_label_selector,
            ),
        )

        # Inject: delete device plugin pods
        for pod_name, pod_ns in target_pods:
            logging.info(f"deleting device plugin pod {pod_name} in {pod_ns}")
            kubecli.delete_pod(pod_name, pod_ns)

        # Verify recovery
        snapshot = future_snapshot.result()
        result = snapshot.get_pods_status()
        scenario_telemetry.affected_pods = result

        for pod in result.recovered:
            logging.info(
                "device plugin pod %s on %s recovered in %.2fs "
                "(rescheduling %.2fs, readiness %.2fs)",
                pod.pod_name,
                pod.namespace,
                pod.total_recovery_time or 0.0,
                pod.pod_rescheduling_time or 0.0,
                pod.pod_readiness_time or 0.0,
            )

        if len(result.unrecovered) > 0:
            logging.error(
                f"device plugin pods did not recover: "
                f"{[p.name for p in result.unrecovered]}"
            )
            if config.expected_recovery:
                return 1
            else:
                logging.info(
                    "expected_recovery=False: skipping remaining "
                    "verification for intentionally unrecovered pods"
                )
                return 0

        # Verify GPU allocatable restored
        if config.verify_allocatable:
            for node_name, expected_count in gpu_snapshots.items():
                if not wait_for_gpu_allocatable(
                    kubecli, node_name, expected_count, config.recovery_timeout
                ):
                    logging.error(
                        f"GPU allocatable not restored on node {node_name}"
                    )
                    return 1

        # Post-disruption GPU health check
        if config.validate_gpu_health:
            for node_info in target_nodes:
                node_name = node_info["name"]
                if not validate_gpu_health_on_node(kubecli, node_name, namespace=config.namespace):
                    logging.error(
                        f"post-disruption GPU health check failed on "
                        f"node {node_name}"
                    )
                    return 1
                logging.info(
                    f"post-disruption GPU health check passed on "
                    f"node {node_name}"
                )

        logging.info("GPU device plugin disruption scenario completed")
        return 0

    @staticmethod
    def rollback_verify_device_plugin(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        try:
            namespace = rollback_content.namespace
            label_selector = rollback_content.resource_identifier
            kubecli = lib_telemetry.get_lib_kubernetes()
            pods = kubecli.select_pods_by_namespace_pattern_and_label(
                namespace_pattern=f"^{namespace}$",
                label_selector=label_selector,
                field_selector="status.phase=Running",
            )
            if pods:
                logging.info(
                    f"rollback: device plugin pod(s) recovered: "
                    f"{[p[0] for p in pods]}"
                )
            else:
                logging.warning(
                    f"rollback: no running device plugin pods found "
                    f"with label '{label_selector}' in '{namespace}'"
                )
        except Exception as e:
            logging.error(f"rollback verification failed: {e}")
