from __future__ import annotations

import datetime
import os.path
from typing import Optional, List, Dict, Any

import urllib3
import logging
import sys

import yaml
from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.models.elastic.models import ElasticAlert
from krkn_lib.models.krkn import ChaosRunAlertSummary, ChaosRunAlert
from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def alerts(
    prom_cli: KrknPrometheus,
    elastic: KrknElastic,
    run_uuid,
    start_time,
    end_time,
    alert_profile,
    elastic_alerts_index,
):

    if alert_profile is None or os.path.exists(alert_profile) is False:
        logging.error(f"{alert_profile} alert profile does not exist")
        sys.exit(1)

    with open(alert_profile) as profile:
        profile_yaml = yaml.safe_load(profile)
        if not isinstance(profile_yaml, list):
            logging.error(
                f"{alert_profile} wrong file format, alert profile must be "
                f"a valid yaml file containing a list of items with at least 3 properties: "
                f"expr, description, severity"
            )
            sys.exit(1)

        for alert in profile_yaml:
            if list(alert.keys()).sort() != ["expr", "description", "severity"].sort():
                logging.error(f"wrong alert {alert}, skipping")

            processed_alert = prom_cli.process_alert(
                alert,
                datetime.datetime.fromtimestamp(start_time),
                datetime.datetime.fromtimestamp(end_time),
            )
            if (
                processed_alert[0]
                and processed_alert[1]
                and elastic
            ):
                elastic_alert = ElasticAlert(
                    run_uuid=run_uuid,
                    severity=alert["severity"],
                    alert=processed_alert[1],
                    created_at=datetime.datetime.fromtimestamp(processed_alert[0]),
                )
                result = elastic.push_alert(elastic_alert, elastic_alerts_index)
                if result == -1:
                    logging.error("failed to save alert on ElasticSearch")
                pass


def critical_alerts(
    prom_cli: KrknPrometheus,
    summary: ChaosRunAlertSummary,
    run_id,
    scenario,
    start_time,
    end_time,
):
    summary.scenario = scenario
    summary.run_id = run_id
    query = r"""ALERTS{severity="critical"}"""
    logging.info("Checking for critical alerts firing post chaos")

    during_critical_alerts = prom_cli.process_prom_query_in_range(
        query, start_time=datetime.datetime.fromtimestamp(start_time), end_time=end_time
    )

    for alert in during_critical_alerts:
        if "metric" in alert:
            alertname = (
                alert["metric"]["alertname"]
                if "alertname" in alert["metric"]
                else "none"
            )
            alertstate = (
                alert["metric"]["alertstate"]
                if "alertstate" in alert["metric"]
                else "none"
            )
            namespace = (
                alert["metric"]["namespace"]
                if "namespace" in alert["metric"]
                else "none"
            )
            severity = (
                alert["metric"]["severity"] if "severity" in alert["metric"] else "none"
            )
            alert = ChaosRunAlert(alertname, alertstate, namespace, severity)
            summary.chaos_alerts.append(alert)

    post_critical_alerts = prom_cli.process_query(query)

    for alert in post_critical_alerts:
        if "metric" in alert:
            alertname = (
                alert["metric"]["alertname"]
                if "alertname" in alert["metric"]
                else "none"
            )
            alertstate = (
                alert["metric"]["alertstate"]
                if "alertstate" in alert["metric"]
                else "none"
            )
            namespace = (
                alert["metric"]["namespace"]
                if "namespace" in alert["metric"]
                else "none"
            )
            severity = (
                alert["metric"]["severity"] if "severity" in alert["metric"] else "none"
            )
            alert = ChaosRunAlert(alertname, alertstate, namespace, severity)
            summary.post_chaos_alerts.append(alert)

    during_critical_alerts_count = len(during_critical_alerts)
    post_critical_alerts_count = len(post_critical_alerts)
    firing_alerts = False

    if during_critical_alerts_count > 0:
        firing_alerts = True

    if post_critical_alerts_count > 0:
        firing_alerts = True

    if not firing_alerts:
        logging.info("No critical alerts are firing!!")


def metrics(
    prom_cli: KrknPrometheus,
    elastic: KrknElastic,
    run_uuid,
    start_time,
    end_time,
    metrics_profile,
    elastic_metrics_index,
) -> list[dict[str, list[(int, float)] | str]]:
    metrics_list: list[dict[str, list[(int, float)] | str]] = []
    if metrics_profile is None or os.path.exists(metrics_profile) is False:
        logging.error(f"{metrics_profile} alert profile does not exist")
        sys.exit(1)
    with open(metrics_profile) as profile:
        profile_yaml = yaml.safe_load(profile)
        if not profile_yaml["metrics"] or not isinstance(profile_yaml["metrics"], list):
            logging.error(
                f"{metrics_profile} wrong file format, alert profile must be "
                f"a valid yaml file containing a list of items with 3 properties: "
                f"expr, description, severity"
            )
            sys.exit(1)

        for metric_query in profile_yaml["metrics"]:
            if (
                list(metric_query.keys()).sort()
                != ["query", "metricName", "instant"].sort()
            ):
                logging.error(f"wrong alert {metric_query}, skipping")
            metrics_result = prom_cli.process_prom_query_in_range(
                metric_query["query"],
                start_time=datetime.datetime.fromtimestamp(start_time),
                end_time=datetime.datetime.fromtimestamp(end_time),
            )

            metric = {"name": metric_query["metricName"], "values": [], }
            for returned_metric in metrics_result:
                if "values" in returned_metric:
                    for value in returned_metric["values"]:
                        try:
                            metric["values"].append((value[0], float(value[1])))
                        except ValueError:
                            pass
            metrics_list.append(metric)

        if elastic:
            result = elastic.upload_metrics_to_elasticsearch(
                run_uuid=run_uuid, index=elastic_metrics_index, raw_data=metrics_list
            )
            if result == -1:
                logging.error("failed to save metrics on ElasticSearch")

    return metrics_list
