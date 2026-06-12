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
from typing import Dict, Any, List, Optional

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus


# -----------------------------------------------------------------------------
# SLO evaluation helpers (used by krkn.resiliency)
# -----------------------------------------------------------------------------


def slo_passed(prometheus_result: List[Any]) -> Optional[bool]:
    """Evaluate whether a Prometheus query result indicates an SLO has passed.

    For range vector results (``"values"`` key), all samples across all series
    are checked. For instant vector results (``"value"`` key), all returned
    series are checked. If **any** sample or series has a non-zero value, the
    SLO is considered failed.

    Args:
        prometheus_result: List of series dicts returned by a Prometheus query.

    Returns:
        ``True``  if all samples are zero (SLO passed),
        ``False`` if any sample is non-zero (SLO failed),
        ``None``  if the result contained no evaluable samples (query returned
        no data — caller decides how to treat this).
    """
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
                # If any series fails the SLO (!= 0), return False immediately.
                # If it passes (== 0), continue checking remaining series.
                if float(series["value"][1]) != 0:
                    return False
            except (TypeError, ValueError):
                continue

    # If we reached here and never saw any samples, skip
    return None if not has_samples else True


def evaluate_slos(
    prom_cli: KrknPrometheus,
    slo_list: List[Dict[str, Any]],
    start_time: datetime.datetime,
    end_time: datetime.datetime,
) -> Dict[str, bool]:
    """Evaluate a list of SLO expressions against Prometheus.

    Args:
        prom_cli: Configured Prometheus client.
        slo_list: List of dicts with keys ``name``, ``expr``.
        start_time: Start timestamp.
        end_time: End timestamp.
        granularity: Step in seconds for range queries.
    Returns:
        Mapping name -> bool indicating pass status.
        True means good we passed the SLO test otherwise failed the SLO
    """
    results: Dict[str, bool] = {}
    logging.info("Evaluating %d SLOs over window %s – %s", len(slo_list), start_time, end_time)
    for slo in slo_list:
        expr = slo["expr"]
        name = slo["name"]
        try:
            response = prom_cli.process_prom_query_in_range(
                expr,
                start_time=start_time,
                end_time=end_time,
            )

            passed = slo_passed(response)
            if passed is None:
                # Absence of data indicates the condition did not trigger; treat as pass.
                logging.debug("SLO '%s' query returned no data; assuming pass.", name)
                results[name] = True
            else:
                results[name] = passed
        except Exception as exc:  
            logging.error("PromQL query failed for SLO '%s': %s", name, exc)
            results[name] = False  
    return results
