from __future__ import annotations

import datetime
import math
import os
import logging
from typing import Dict, Any, List

import yaml
from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus


def collect_prometheus_metrics(
    prom_cli: KrknPrometheus,
    metrics_profile: str | dict,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    granularity: int = 30,
) -> Dict[str, Any]:
    """Collect Prometheus metrics described by a metrics profile for a given time window.

    Args:
        prom_cli: Configured KrknPrometheus client instance.
        metrics_profile: Either a path to a YAML file or a pre-parsed dict containing a
            `metrics` list. Each item must include `query` and `metricName` keys and can
            optionally set `instant: true` to request an instant query.
        start_time: Start of the window (datetime).
        end_time: End of the window (datetime).
        granularity: Step in seconds used for range queries (default: 30).

    Returns:
        A dictionary keyed by ``metricName`` containing the original query, whether it
        was an instant query and the raw Prometheus response returned by the client.
    """

    # Load YAML profile from disk when a string path is provided
    if isinstance(metrics_profile, str):
        if not os.path.exists(metrics_profile):
            raise FileNotFoundError(f"Metrics profile {metrics_profile} does not exist")
        with open(metrics_profile, "r", encoding="utf-8") as f:
            profile_data = yaml.safe_load(f)
    else:
        profile_data = metrics_profile

    if not profile_data or "metrics" not in profile_data or not isinstance(profile_data["metrics"], list):
        raise ValueError("metrics_profile must define a top-level 'metrics' list")

    elapsed_minutes = math.ceil((end_time.timestamp() - start_time.timestamp()) / 60)
    elapsed_token = f"{elapsed_minutes}m"

    results: Dict[str, Any] = {}

    for metric in profile_data["metrics"]:
        if "query" not in metric or "metricName" not in metric:
            logging.warning("Skipping invalid metric entry: %s", metric)
            continue

        query = metric["query"].replace(".elapsed", elapsed_token)
        metric_name = metric["metricName"]
        is_instant = bool(metric.get("instant", False))

        try:
            if is_instant:
                response = prom_cli.process_query(query)
            else:
                response = prom_cli.process_prom_query_in_range(
                    query,
                    start_time=start_time,
                    end_time=end_time,
                    granularity=granularity,
                )
            results[metric_name] = {
                "query": query,
                "instant": is_instant,
                "data": response,
            }
        except Exception as exc:  # Broad check to avoid aborting the entire collection
            logging.error("Failed to execute Prometheus query '%s': %s", query, exc)
            results[metric_name] = {
                "query": query,
                "instant": is_instant,
                "data": [],
                "error": str(exc),
            }

    return results


# -----------------------------------------------------------------------------
# SLO evaluation helpers (used by krkn.resiliency)
# -----------------------------------------------------------------------------


def slo_passed(prometheus_result: List[Any]) -> bool:  
    """Return True when an SLO passed based on Prometheus query result."""
    # If query returns no data we cannot assert pass→treat as failure
    if not prometheus_result:
        return False
    for series in prometheus_result:
        if "values" in series:
            for _ts, val in series["values"]:
                try:
                    if float(val) > 0:
                        return False
                except (TypeError, ValueError):
                    continue
        elif "value" in series:
            try:
                return float(series["value"][1]) == 0
            except (TypeError, ValueError):
                return False
    return True


def evaluate_slos(
    prom_cli: KrknPrometheus,
    slo_list: List[Dict[str, Any]],
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    granularity: int = 30,
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
                granularity=granularity,
            )
            if not response:
                logging.warning("SLO '%s' query returned no data; treating as failure", name)
            results[name] = slo_passed(response)
        except Exception as exc:  
            logging.error("PromQL query failed for SLO '%s': %s", name, exc)
            results[name] = False  
    return results
