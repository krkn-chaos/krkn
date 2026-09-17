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
import datetime
import json
import logging
import time
from typing import Optional

import krkn.prometheus as prometheus_plugin
from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.models.krkn import ChaosRunAlertSummary
from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus

from krkn.health_checks.abstract_alert_health_check import AbstractAlertHealthCheck
from krkn.health_checks.models import AlertHealthCheckResult


class PreChaosCheck(AbstractAlertHealthCheck):
    """
    Pre-chaos baseline check: verify the cluster isn't already unhealthy
    before injecting failures, and record a "pre_chaos" baseline snapshot
    (alerts/metrics) in Elastic if configured.
    """

    def phase(self) -> str:
        return "pre_chaos"

    def run(
        self,
        prometheus: Optional[KrknPrometheus],
        elastic_search: Optional[KrknElastic],
        run_uuid: str,
        elastic_alerts_index: str,
        elastic_metrics_index: str,
        alert_profile: Optional[str],
        metrics_profile: Optional[str],
        check_critical_alerts: bool,
        enable_alerts: bool,
        enable_metrics: bool,
        chaos_scenarios: list,
        exit_on_pre_check_failure: bool,
        **kwargs,
    ) -> AlertHealthCheckResult:
        """
        Never exits the process -- signals via `should_exit` so the caller
        can perform the actual early return.
        """
        if not (chaos_scenarios and (check_critical_alerts or enable_alerts or enable_metrics)):
            return AlertHealthCheckResult(ran=False, failed=False, should_exit=False)

        logging.info("Running pre-chaos health check")
        pre_check_failed = False
        pre_check_start_time = int(time.time()) - 60
        pre_check_end_time = int(time.time())

        if check_critical_alerts:
            pre_summary = ChaosRunAlertSummary()
            prometheus_plugin.critical_alerts(
                prometheus,
                pre_summary,
                elastic_search,
                run_uuid,
                "pre_chaos_check",
                pre_check_start_time,
                datetime.datetime.fromtimestamp(pre_check_end_time),
                elastic_alerts_index,
                phase=self.phase()
            )
            if len(pre_summary.post_chaos_alerts) > 0:
                pre_check_failed = True

        if enable_alerts and alert_profile:
            pre_profile_alerts = prometheus_plugin.alerts(
                prometheus,
                elastic_search,
                run_uuid,
                pre_check_start_time,
                pre_check_end_time,
                alert_profile,
                elastic_alerts_index,
                phase=self.phase()
            )
            if pre_profile_alerts:
                pre_check_failed = True

        should_exit = False
        if pre_check_failed:
            logging.error(
                "Pre-chaos check found critical/error alerts already firing on the cluster"
            )
            if exit_on_pre_check_failure:
                logging.error(
                    "exit_on_pre_check_failure is set, exiting before running chaos scenarios"
                )
                should_exit = True

        if enable_metrics and metrics_profile:
            logging.info("Capturing pre-chaos metrics baseline")
            prometheus_plugin.metrics(
                prometheus,
                elastic_search,
                run_uuid,
                pre_check_start_time,
                pre_check_end_time,
                metrics_profile,
                elastic_metrics_index,
                json.dumps({"scenarios": [], "health_checks": [], "virt_checks": []}),
                phase=self.phase()
            )

        return AlertHealthCheckResult(ran=True, failed=pre_check_failed, should_exit=should_exit)
