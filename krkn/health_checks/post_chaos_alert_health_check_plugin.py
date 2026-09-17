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
Post-Chaos Alert Health Check Plugin

Unlike the other health check plugins, this one does not poll continuously.
It blocks on `self._stop_event` (set by `HealthCheckFactory.stop_all()` right
after the chaos loop and wait duration complete), then performs a single
Prometheus alert/metrics evaluation over the full run window.

Example configuration in config.yaml:
    post_chaos_alert_check:
      check_critical_alerts: true
      enable_alerts: true
      enable_metrics: true
      alert_profile: config/alerts.yaml
      metrics_profile: config/metrics.yaml
      elastic_alerts_index: alerts
      elastic_metrics_index: metrics
"""

import datetime
import json
import logging
import queue
import time
from typing import Any

import krkn.prometheus as prometheus_plugin
from krkn_lib.models.krkn import ChaosRunAlertSummary

from krkn.health_checks.abstract_health_check_plugin import AbstractHealthCheckPlugin


class PostChaosAlertHealthCheckPlugin(AbstractHealthCheckPlugin):
    """
    One-shot post-chaos Prometheus alert/metrics evaluation, run once the
    chaos loop and wait duration are finished.
    """

    def __init__(
        self,
        health_check_type: str = "post_chaos_alert_check",
        iterations: int = 1,
        **kwargs,
    ):
        super().__init__(health_check_type)
        self.prometheus = kwargs.get("prometheus")
        self.elastic_search = kwargs.get("elastic_search")
        self.run_uuid = kwargs.get("run_uuid")

    def get_health_check_types(self) -> list[str]:
        return ["post_chaos_alert_check"]

    def get_config_key(self) -> str:
        return "post_chaos_alert_check"

    def increment_iterations(self) -> None:
        """Not iteration-driven; this plugin only cares about start/stop."""
        pass

    def run_health_check(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue,
    ) -> None:
        """
        Blocks until the main run signals completion via `stop()`, then runs
        the configured post-chaos alert/metrics evaluation once.

        :param config: the `post_chaos_alert_check` section from config.yaml
        :param telemetry_queue: a queue to put telemetry data for collection
        :return: None
        """
        check_critical_alerts = config.get("check_critical_alerts", False)
        enable_alerts = config.get("enable_alerts", False)
        enable_metrics = config.get("enable_metrics", False)
        alert_profile = config.get("alert_profile")
        metrics_profile = config.get("metrics_profile")
        elastic_alerts_index = config.get("elastic_alerts_index")
        elastic_metrics_index = config.get("elastic_metrics_index")

        start_time = int(time.time())
        self._stop_event.wait()
        end_time = int(time.time())

        if not (check_critical_alerts or enable_alerts or enable_metrics):
            telemetry_queue.put([])
            return

        logging.info("Running post-chaos health check")

        if check_critical_alerts:
            summary = ChaosRunAlertSummary()
            prometheus_plugin.critical_alerts(
                self.prometheus,
                summary,
                self.elastic_search,
                self.run_uuid,
                "post_chaos_check",
                start_time,
                datetime.datetime.fromtimestamp(end_time),
                elastic_alerts_index,
                phase="post_chaos",
            )
            if len(summary.post_chaos_alerts) > 0:
                self.set_return_value(2)

        if enable_alerts and alert_profile:
            profile_alerts = prometheus_plugin.alerts(
                self.prometheus,
                self.elastic_search,
                self.run_uuid,
                start_time,
                end_time,
                alert_profile,
                elastic_alerts_index,
                phase="post_chaos",
            )
            if profile_alerts:
                self.set_return_value(2)

        if enable_metrics and metrics_profile:
            prometheus_plugin.metrics(
                self.prometheus,
                self.elastic_search,
                self.run_uuid,
                start_time,
                end_time,
                metrics_profile,
                elastic_metrics_index,
                json.dumps({"scenarios": [], "health_checks": [], "virt_checks": []}),
                phase="post_chaos",
            )

        telemetry_queue.put([])
