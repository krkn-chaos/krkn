from __future__ import annotations

import datetime
import logging
from typing import Dict, Any, List, Optional

import yaml
from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
from krkn.prometheus.client import metrics as client_metrics


def collect_prometheus_metrics(
    prom_cli: KrknPrometheus,
    metrics_profile: str | dict,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    granularity: int = 30,
) -> list[dict[str, Any]]:
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
        List of metric dictionaries as produced by `krkn.prometheus.client.metrics`.
    """

    # Reuse implementation from krkn.prometheus.client.metrics to avoid code duplication
    return client_metrics(
        prom_cli=prom_cli,
        elastic=None,
        run_uuid="",
        start_time=int(start_time.timestamp()),
        end_time=int(end_time.timestamp()),
        metrics_profile=metrics_profile,
        elastic_metrics_index=None,
        telemetry_json="{}",
    )



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

            passed = slo_passed(response)
            if passed is None:
                logging.warning("SLO '%s' query returned no data; excluding from score.", name)
            else:
                results[name] = passed
        except Exception as exc:  
            logging.error("PromQL query failed for SLO '%s': %s", name, exc)
            results[name] = False  
    return results
