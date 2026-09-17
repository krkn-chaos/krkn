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
from abc import ABC, abstractmethod
from typing import Optional

from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus

from krkn.health_checks.models import AlertHealthCheckResult


class AbstractAlertHealthCheck(ABC):
    """
    Base class for one-shot Prometheus alert/metrics baseline checks
    (e.g. pre-chaos, post-chaos), as opposed to the continuous, threaded
    monitors in krkn.health_checks.
    """

    @abstractmethod
    def phase(self) -> str:
        """
        Returns the phase tag used when tagging alerts/metrics pushed to
        Elastic, e.g. "pre_chaos" or "post_chaos".
        """
        pass

    @abstractmethod
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
        **kwargs,
    ) -> AlertHealthCheckResult:
        """
        Runs the check once and returns its result. Implementations must
        not exit the process themselves -- callers decide what to do with
        `AlertHealthCheckResult.should_exit`.
        """
        pass
