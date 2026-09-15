#!/usr/bin/env python
#
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

from __future__ import annotations

import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus


# -----------------------------------------------------------------------------
# SLO evaluation helpers (used by krkn.resiliency)
# -----------------------------------------------------------------------------


def slo_passed(prometheus_result: List[Any]) -> Optional[bool]:
    if not prometheus_result:
        return None
    has_samples = False
    for series in prometheus_result:
        if "values" in series:
            has_samples = True
            for _ts, val in series["values"]:
                try:
                    if float(val) > 0:
                        return False
                except (TypeError, ValueError):
                    continue
        elif "value" in series:
            has_samples = True
            try:
                return float(series["value"][1]) == 0
            except (TypeError, ValueError):
                return False

    # If we reached here and never saw any samples, skip
    return None if not has_samples else True


def evaluate_slos(
    prom_cli: KrknPrometheus,
    slo_list: List[Dict[str, Any]],
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    max_workers: int = 10,
) -> Dict[str, bool]:
    """Evaluate a list of SLO expressions against Prometheus in parallel.

    Args:
        prom_cli: Configured Prometheus client.
        slo_list: List of dicts with keys ``name``, ``expr``.
        start_time: Start timestamp.
        end_time: End timestamp.
        max_workers: Maximum number of concurrent PromQL queries. Clamped to
            a minimum of 1.
    Returns:
        Mapping name -> bool indicating pass status.
        True means good we passed the SLO test otherwise failed the SLO
    """
    results: Dict[str, bool] = {}

    if not slo_list:
        return results

    logging.info("Evaluating %d SLOs over window %s – %s", len(slo_list), start_time, end_time)

    def _eval_single(slo: Dict[str, Any]) -> tuple[str, bool]:
        try:
            expr = slo["expr"]
            name = slo["name"]
        except KeyError as exc:
            raise ValueError(
                f"Malformed SLO definition (missing key {exc}): {slo!r}"
            ) from exc
        try:
            response = prom_cli.process_prom_query_in_range(
                expr,
                start_time=start_time,
                end_time=end_time,
            )
            passed = slo_passed(response)
            if passed is None:
                logging.debug("SLO '%s' query returned no data; assuming pass.", name)
                return name, True
            return name, passed
        except Exception as exc:
            logging.error("PromQL query failed for SLO '%s': %s", name, exc)
            return name, False

    worker_count = min(len(slo_list), max(1, max_workers))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {pool.submit(_eval_single, slo): slo for slo in slo_list}
        for future in as_completed(futures):
            try:
                name, passed = future.result()
                results[name] = passed
            except Exception as exc:
                slo = futures[future]
                slo_name = slo.get("name", "<unknown>")
                logging.error("Unexpected error evaluating SLO '%s': %s",
                              slo_name, exc)
                results[slo_name] = False

    return results
