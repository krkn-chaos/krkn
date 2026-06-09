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
import copy
import logging
import queue
import random
import re
import threading
import time


import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.krkn import HogConfig, HogType
from krkn_lib.models.k8s import NodeResources
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.utils import get_random_string

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator

# How close a metric must be to the pre-chaos baseline to be considered
# "recovered" (5 % tolerance).
_RECOVERY_TOLERANCE = 0.05

# Default maximum seconds to wait for node resources to return to baseline.
_DEFAULT_RECOVERY_TIMEOUT = 120


class HogsScenarioPlugin(AbstractScenarioPlugin):

    @set_rollback_context_decorator
    def run(self, run_uuid: str, scenario: str, lib_telemetry: KrknTelemetryOpenshift,
            scenario_telemetry: ScenarioTelemetry) -> int:
        try:
            with open(scenario, "r") as f:
                scenario = yaml.safe_load(f)
            scenario_config = HogConfig.from_yaml_dict(scenario)

            # Optional: maximum seconds to wait for node resources to recover
            # after the hog completes (mirrors krkn_pod_recovery_time in
            # pod_disruption scenario).  Defaults to _DEFAULT_RECOVERY_TIMEOUT.
            scenario_config.krkn_node_recovery_timeout = int(
                scenario.get("node-recovery-timeout", _DEFAULT_RECOVERY_TIMEOUT)
            )

            # Get node-name if provided
            node_name = scenario.get('node-name')

            has_selector = True
            if not scenario_config.node_selector or not re.match("^.+=.*$", scenario_config.node_selector):
                if scenario_config.node_selector:
                    logging.warning(f"node selector {scenario_config.node_selector} not in right format (key=value)")
                node_selector = ""
            else:
                node_selector = scenario_config.node_selector

            if node_name:
                logging.info(f"Using specific node: {node_name}")
                all_nodes = lib_telemetry.get_lib_kubernetes().list_nodes("")
                if node_name not in all_nodes:
                    raise Exception(f"Specified node {node_name} not found or not available")
                available_nodes = [node_name]
            else:
                available_nodes = lib_telemetry.get_lib_kubernetes().list_nodes(node_selector)
                if len(available_nodes) == 0:
                    raise Exception("no available nodes to schedule workload")

                if not has_selector:
                    available_nodes = [available_nodes[random.randint(0, len(available_nodes) - 1)]]

            if scenario_config.number_of_nodes and len(available_nodes) > scenario_config.number_of_nodes:
                available_nodes = random.sample(available_nodes, scenario_config.number_of_nodes)

            # Ensure scenario_telemetry.parameters is a dict so per-node
            # metrics can be written into it thread-safely.
            if not isinstance(scenario_telemetry.parameters, dict):
                scenario_telemetry.parameters = {}

            telemetry_lock = threading.Lock()
            exception_queue = queue.Queue()
            self.run_scenario(
                scenario_config,
                lib_telemetry.get_lib_kubernetes(),
                available_nodes,
                exception_queue,
                scenario_telemetry,
                telemetry_lock,
            )
            return 0
        except Exception as e:
            logging.error(f"scenario exception: {e}")
            return 1

    def get_scenario_types(self) -> list[str]:
        return ["hog_scenarios"]

    def run_scenario_worker(
        self,
        config: HogConfig,
        lib_k8s: KrknKubernetes,
        node: str,
        exception_queue: queue.Queue,
        scenario_telemetry: ScenarioTelemetry,
        telemetry_lock: threading.Lock,
    ):
        try:
            if not config.workers:
                config.workers = lib_k8s.get_node_cpu_count(node)
                logging.info(f"[{node}] detected {config.workers} cpus for node {node}")

            logging.info(f"[{node}] workers number: {config.workers}")

            # using kubernetes.io/hostname = <node_name> selector to
            # precisely deploy each workload on each selected node
            config.node_selector = f"kubernetes.io/hostname={node}"
            pod_name = f"{config.type.value}-hog-{get_random_string(5)}"

            # Capture pre-chaos baseline
            node_resources_start = lib_k8s.get_node_resources_info(node)

            self.rollback_handler.set_rollback_callable(
                self.rollback_hog_pod,
                RollbackContent(
                    namespace=config.namespace,
                    resource_identifier=pod_name,
                ),
            )
            lib_k8s.deploy_hog(pod_name, config)
            start = time.time()
            # waiting 3 seconds before starting sample collection
            time.sleep(3)
            node_resources_end = lib_k8s.get_node_resources_info(node)

            samples: list[NodeResources] = []
            avg_node_resources = NodeResources()

            while time.time() - start < config.duration - 1:
                samples.append(lib_k8s.get_node_resources_info(node))

            max_wait = 30
            wait = 0
            logging.info(
                f"[{node}] waiting {max_wait} up to seconds pod: {pod_name} "
                f"namespace: {config.namespace} to finish"
            )
            while lib_k8s.is_pod_running(pod_name, config.namespace):
                if wait >= max_wait:
                    raise Exception(
                        f"[{node}] hog workload pod: {pod_name} "
                        f"namespace: {config.namespace} didn't finish after {max_wait}"
                    )
                time.sleep(1)
                wait += 1
                continue

            logging.info(f"[{node}] deleting pod: {pod_name} namespace: {config.namespace}")
            lib_k8s.delete_pod(pod_name, config.namespace)

            # ── Injection impact metrics ──────────────────────────────────────
            # Compute averages from samples collected during the hog duration.
            if samples:
                for resource in samples:
                    avg_node_resources.cpu += resource.cpu
                    avg_node_resources.memory += resource.memory
                    avg_node_resources.disk_space += resource.disk_space

                avg_node_resources.cpu = avg_node_resources.cpu / len(samples)
                avg_node_resources.memory = avg_node_resources.memory / len(samples)
                avg_node_resources.disk_space = avg_node_resources.disk_space / len(samples)
            else:
                logging.warning(f"[{node}] no resource samples collected; skipping average computation")

            if config.type == HogType.cpu:
                logging.info(
                    f"[{node}] detected cpu consumption: "
                    f"{(avg_node_resources.cpu / (config.workers * 1_000_000_000)) * 100:.2f} %"
                )
            if config.type == HogType.memory:
                logging.info(
                    f"[{node}] detected memory increase: "
                    f"{avg_node_resources.memory / node_resources_start.memory * 100:.2f} %"
                )
            if config.type == HogType.io:
                logging.info(
                    f"[{node}] detected disk space allocated: "
                    f"{(avg_node_resources.disk_space - node_resources_end.disk_space) / 1_048_576:.2f} MB"
                )

            # ── Resource-level recovery time ──────────────────────────────────
            # Poll until all relevant metrics return within _RECOVERY_TOLERANCE
            # of the pre-chaos baseline, up to krkn_node_recovery_timeout seconds.
            recovery_timeout = getattr(config, "krkn_node_recovery_timeout", _DEFAULT_RECOVERY_TIMEOUT)
            recovery_start = time.time()
            recovery_elapsed: float = -1  # -1 means "did not recover within timeout"

            logging.info(
                f"[{node}] waiting up to {recovery_timeout}s for node resources "
                "to return to pre-chaos baseline"
            )

            while time.time() - recovery_start < recovery_timeout:
                current = lib_k8s.get_node_resources_info(node)
                recovered = self._is_recovered(
                    config.type, current, node_resources_start, avg_node_resources
                )
                if recovered:
                    recovery_elapsed = time.time() - recovery_start
                    logging.info(
                        f"[{node}] node resources recovered to baseline in "
                        f"{recovery_elapsed:.1f}s"
                    )
                    break
                time.sleep(5)

            if recovery_elapsed < 0:
                logging.warning(
                    f"[{node}] node resources did NOT return to pre-chaos baseline "
                    f"within {recovery_timeout}s"
                )

            # ── Write metrics into scenario_telemetry ─────────────────────────
            node_metrics = {
                "avg_cpu_nanocores": avg_node_resources.cpu,
                "avg_memory_available_bytes": avg_node_resources.memory,
                "avg_disk_available_bytes": avg_node_resources.disk_space,
                "baseline_cpu_nanocores": node_resources_start.cpu,
                "baseline_memory_available_bytes": node_resources_start.memory,
                "baseline_disk_available_bytes": node_resources_start.disk_space,
                "resource_recovery_time_seconds": recovery_elapsed,
            }

            with telemetry_lock:
                if "node_resource_metrics" not in scenario_telemetry.parameters:
                    scenario_telemetry.parameters["node_resource_metrics"] = {}
                scenario_telemetry.parameters["node_resource_metrics"][node] = node_metrics

        except Exception as e:
            exception_queue.put(e)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_recovered(
        hog_type: HogType,
        current: NodeResources,
        baseline: NodeResources,
        chaos_avg: NodeResources,
    ) -> bool:
        """Return True when the metric relevant to *hog_type* is back within
        ``_RECOVERY_TOLERANCE`` of the pre-chaos *baseline*.

        For CPU the check is delta-based: the chaos injection delta
        (``chaos_avg.cpu - baseline.cpu``) is used as the scale so that
        normal idle-node noise (which is small relative to the baseline
        nanocores value but large relative to a tiny relative tolerance)
        does not cause a false-positive "already recovered" on the very
        first poll.  If the measured delta was zero or negative (no
        meaningful CPU injection occurred) we fall back to an absolute
        threshold of 100 000 000 nanocores (~10 % of one core).

        For memory and disk the relative check against the baseline value
        is retained because those metrics are ``availableBytes`` and the
        idle-node noise is proportionally small.
        """
        tolerance = _RECOVERY_TOLERANCE

        if hog_type == HogType.cpu:
            cpu_delta = chaos_avg.cpu - baseline.cpu
            if cpu_delta > 0:
                # Recovered when current is within tolerance*delta of baseline.
                return abs(current.cpu - baseline.cpu) <= tolerance * cpu_delta
            else:
                # No significant injection measured; use a fixed absolute
                # threshold (100 ms worth of CPU in nanocores).
                _CPU_ABSOLUTE_THRESHOLD = 100_000_000
                return abs(current.cpu - baseline.cpu) <= _CPU_ABSOLUTE_THRESHOLD

        if hog_type == HogType.memory:
            if baseline.memory == 0:
                return True
            return abs(current.memory - baseline.memory) / baseline.memory <= tolerance

        if hog_type == HogType.io:
            if baseline.disk_space == 0:
                return True
            return abs(current.disk_space - baseline.disk_space) / baseline.disk_space <= tolerance

        # Unknown type — treat as recovered to avoid blocking indefinitely.
        return True

    def run_scenario(
        self,
        config: HogConfig,
        lib_k8s: KrknKubernetes,
        available_nodes: list[str],
        exception_queue: queue.Queue,
        scenario_telemetry: ScenarioTelemetry,
        telemetry_lock: threading.Lock,
    ):
        workers = []
        logging.info(f"running {config.type.value} hog scenario")
        logging.info(f"targeting nodes: [{','.join(available_nodes)}]")
        for node in available_nodes:
            config_copy = copy.deepcopy(config)
            worker = threading.Thread(
                target=self.run_scenario_worker,
                args=(config_copy, lib_k8s, node, exception_queue, scenario_telemetry, telemetry_lock),
            )
            worker.daemon = True
            worker.start()
            workers.append(worker)

        for worker in workers:
            worker.join()

        try:
            while True:
                exception = exception_queue.get_nowait()
                raise exception
        except queue.Empty:
            pass

    @staticmethod
    def rollback_hog_pod(rollback_content: RollbackContent, lib_telemetry: KrknTelemetryOpenshift):
        """
        Rollback function to delete hog pod.

        :param rollback_content: Rollback content containing namespace and resource_identifier.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations
        """
        try:
            namespace = rollback_content.namespace
            pod_name = rollback_content.resource_identifier
            logging.info(
                f"Rolling back hog pod: {pod_name} in namespace: {namespace}"
            )
            lib_telemetry.get_lib_kubernetes().delete_pod(pod_name, namespace)
            logging.info("Rollback of hog pod completed successfully.")
        except Exception as e:
            logging.error(f"Failed to rollback hog pod: {e}")
