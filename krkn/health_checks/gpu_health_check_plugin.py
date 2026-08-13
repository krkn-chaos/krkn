# Copyright 2026 The Krkn Authors
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
"""
GPU Health Check Plugin

Continuously monitors GPU availability on GPU nodes throughout a chaos run and
records downtime windows into telemetry. The primary signal is node
``nvidia.com/gpu`` allocatable: when the NVIDIA device plugin dies (or a node
loses its GPUs), allocatable drops and this plugin captures the outage window
(start/end/duration). Optionally validates driver-level health via nvidia-smi.

This is a passive, read-only monitor. It does not modify the cluster; pair it
with a disruption scenario (e.g. ``gpu_device_plugin_scenarios``) to measure how
long GPU scheduling was unavailable during the disruption.

Example configuration in config.yaml:
    gpu_health_checks:
      interval: 5                       # seconds between polls (default: 5)
      namespace: nvidia-gpu-operator    # GPU Operator namespace (default)
      validate_gpu_health: false        # also run nvidia-smi (default: false)
      exit_on_failure: false            # fail the krkn run on GPU downtime
"""

import logging
import queue
import time
from datetime import datetime
from typing import Any

from krkn_lib.models.telemetry.models import HealthCheck

from krkn.health_checks.abstract_health_check_plugin import (
    AbstractHealthCheckPlugin,
)
from krkn.utils.gpu import (
    discover_gpu_nodes,
    get_node_gpu_allocatable,
    validate_gpu_health_on_node,
)


class GpuHealthCheckPlugin(AbstractHealthCheckPlugin):
    """
    Monitors GPU allocatable (and optionally nvidia-smi health) on GPU nodes
    and records availability/downtime periods to telemetry.
    """

    def __init__(
        self,
        health_check_type: str = "gpu_health_check",
        iterations: int = 1,
        krkn_lib=None,
        **kwargs,
    ):
        """
        :param health_check_type: the health check type identifier
        :param iterations: number of chaos iterations to monitor
        :param krkn_lib: KrknKubernetes client forwarded by the factory
            (``start_all(..., krkn_lib=kubecli)``)
        """
        super().__init__(health_check_type)
        self.iterations = iterations
        self.current_iterations = 0
        self.kubecli = krkn_lib

    def get_health_check_types(self) -> list[str]:
        return ["gpu_health_check"]

    def get_config_key(self) -> str:
        return "gpu_health_checks"

    def increment_iterations(self) -> None:
        self.current_iterations += 1

    def _probe_node(
        self,
        node_name: str,
        baseline: int,
        namespace: str,
        validate_health: bool,
    ) -> tuple[bool, str]:
        """
        Probe a single node's GPU availability.

        :return: (healthy, status_code) where status_code is the current
            allocatable count as a string, or an error marker.
        """
        try:
            current = get_node_gpu_allocatable(self.kubecli, node_name)
        except Exception as e:
            logging.error(
                f"GPU health check: failed to read allocatable on "
                f"{node_name}: {e}"
            )
            return False, "error"

        healthy = current >= baseline
        if healthy and validate_health:
            healthy = validate_gpu_health_on_node(
                self.kubecli, node_name, namespace=namespace
            )
        return healthy, str(current)

    def run_health_check(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue,
    ) -> None:
        """
        Runs the GPU health monitoring loop until the configured number of
        chaos iterations completes (or an early stop is signalled). Records a
        telemetry entry for every availability state change and a final entry
        per node when the loop ends.
        """
        if self.kubecli is None:
            logging.error(
                "GPU health check: no Kubernetes client available, skipping"
            )
            return

        config = config or {}
        interval = config.get("interval", 5)
        namespace = config.get("namespace", "nvidia-gpu-operator")
        validate_health = config.get("validate_gpu_health", False)
        exit_on_failure = config.get("exit_on_failure", False)

        gpu_nodes = discover_gpu_nodes(self.kubecli)
        if not gpu_nodes:
            logging.warning(
                "GPU health check: no GPU nodes found, nothing to monitor"
            )
            return

        baselines = {n["name"]: n["gpu_count"] for n in gpu_nodes}
        logging.info(
            f"GPU health check monitoring {len(baselines)} node(s): "
            f"{baselines}"
        )

        health_check_telemetry: list[HealthCheck] = []
        # node -> {"healthy": bool, "status_code": str, "start_timestamp": dt}
        tracker: dict[str, dict[str, Any]] = {}

        while (
            self.current_iterations < self.iterations
            and not self._stop_event.is_set()
        ):
            for node_name, baseline in baselines.items():
                healthy, status_code = self._probe_node(
                    node_name, baseline, namespace, validate_health
                )
                now = datetime.now()

                if node_name not in tracker:
                    tracker[node_name] = {
                        "healthy": healthy,
                        "status_code": status_code,
                        "start_timestamp": now,
                    }
                    if not healthy:
                        logging.error(
                            f"GPU health check: {node_name} unhealthy "
                            f"(allocatable={status_code}, baseline={baseline})"
                        )
                        if exit_on_failure and self.ret_value == 0:
                            self.ret_value = 3
                elif healthy != tracker[node_name]["healthy"]:
                    # State changed: record the period that just ended.
                    prev = tracker[node_name]
                    duration = (now - prev["start_timestamp"]).total_seconds()
                    health_check_telemetry.append(
                        HealthCheck(
                            {
                                "url": f"gpu://{node_name}",
                                "status": prev["healthy"],
                                "status_code": prev["status_code"],
                                "start_timestamp": prev[
                                    "start_timestamp"
                                ].isoformat(),
                                "end_timestamp": now.isoformat(),
                                "duration": duration,
                            }
                        )
                    )
                    if healthy:
                        logging.info(
                            f"GPU health check: {node_name} recovered after "
                            f"{duration:.2f}s (allocatable={status_code})"
                        )
                    else:
                        logging.error(
                            f"GPU health check: {node_name} unhealthy "
                            f"(allocatable={status_code}, baseline={baseline})"
                        )
                        if exit_on_failure and self.ret_value == 0:
                            self.ret_value = 3
                    tracker[node_name] = {
                        "healthy": healthy,
                        "status_code": status_code,
                        "start_timestamp": now,
                    }

            time.sleep(interval)

        # Flush the final open period for each node.
        end_timestamp = datetime.now()
        for node_name, state in tracker.items():
            duration = (
                end_timestamp - state["start_timestamp"]
            ).total_seconds()
            health_check_telemetry.append(
                HealthCheck(
                    {
                        "url": f"gpu://{node_name}",
                        "status": state["healthy"],
                        "status_code": state["status_code"],
                        "start_timestamp": state["start_timestamp"].isoformat(),
                        "end_timestamp": end_timestamp.isoformat(),
                        "duration": duration,
                    }
                )
            )

        telemetry_queue.put(health_check_telemetry)
