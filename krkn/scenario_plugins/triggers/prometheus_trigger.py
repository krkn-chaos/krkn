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
import logging

import requests

from krkn.scenario_plugins.triggers.abstract_trigger import AbstractTrigger

# Cap each PromQL request so a hung Prometheus cannot block evaluate()
# past TriggerManager's deadline between polls (same idea as HttpTrigger).
PROM_REQUEST_TIMEOUT_SECONDS = 30


class PrometheusTrigger(AbstractTrigger):
    """Trigger that evaluates a PromQL query against Prometheus.

    Connection details come from the condition config:
    ``prometheus_url`` and optional ``prometheus_bearer_token``.
    The ``KrknPrometheus`` client is created lazily on first evaluate().
    Polling / timeout / on_timeout are handled by TriggerManager.
    """

    def __init__(self, config: dict):
        self._query = config.get("query")
        if not self._query:
            raise ValueError("prometheus trigger requires a 'query' field")

        self._prometheus_url = config.get("prometheus_url")
        if not self._prometheus_url:
            raise ValueError(
                "prometheus trigger requires a 'prometheus_url' field"
            )
        self._prometheus_bearer_token = config.get("prometheus_bearer_token")
        self._prom_client = None
        self._last_result: bool | None = None

    def _get_prom_client(self):
        if self._prom_client is None:
            # Lazy import: avoid pulling prometheus_api_client/pandas at
            # module import time (TriggerManager / unit-test collection).
            from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus

            self._prom_client = KrknPrometheus(
                self._prometheus_url,
                self._prometheus_bearer_token,
            )
            # KrknPrometheus does not expose a timeout; PrometheusConnect does.
            self._prom_client.prom_cli._timeout = PROM_REQUEST_TIMEOUT_SECONDS
        return self._prom_client

    def evaluate(self) -> bool:
        try:
            client = self._get_prom_client()
            result = client.process_query(self._query)
            met = bool(result)
            logging.debug(
                "prometheus trigger: query=%r result_count=%s",
                self._query,
                len(result) if result is not None else 0,
            )
        except requests.exceptions.Timeout:
            logging.warning(
                f"prometheus trigger timed out after "
                f"{PROM_REQUEST_TIMEOUT_SECONDS}s: query={self._query!r}"
            )
            met = False
        except Exception as e:
            logging.warning(f"prometheus trigger query failed: {e}")
            met = False

        # Log only on state change (same pattern as HttpTrigger)
        if met != self._last_result:
            if met:
                logging.info(f"trigger condition satisfied: {self.describe()}")
            else:
                logging.info(
                    f"trigger condition not satisfied: {self.describe()}"
                )
        self._last_result = met
        return met

    def describe(self) -> str:
        return f"prometheus trigger (query: {self._query})"
