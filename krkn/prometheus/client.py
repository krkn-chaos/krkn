from __future__ import annotations

import datetime
import os.path
import math
from typing import Optional, List, Dict, Any

import logging
import urllib3
import sys
import json
import tempfile

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
    elastic_alerts_index
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
                continue

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
    telemetry_json
) -> list[dict[str, list[(int, float)] | str]]:
   
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
        elapsed_ceil = math.ceil((end_time - start_time)/ 60 )
        elapsed_time = str(elapsed_ceil) + "m"
        metrics_list: list[dict[str, int | float | str]] = []
        for metric_query in profile_yaml["metrics"]:
            query = metric_query['query']
            
            # calculate elapsed time
            if ".elapsed" in metric_query["query"]:
                query = metric_query['query'].replace(".elapsed", elapsed_time)
            if "instant" in list(metric_query.keys()) and metric_query['instant']:
                metrics_result = prom_cli.process_query(
                   query
                )
            elif (
                list(metric_query.keys()).sort()
                == ["query", "metricName"].sort()
            ):
                metrics_result = prom_cli.process_prom_query_in_range(
                    query,
                    start_time=datetime.datetime.fromtimestamp(start_time),
                    end_time=datetime.datetime.fromtimestamp(end_time), granularity=30
                )
            else: 
                logging.info('didnt match keys')
                continue
            
            for returned_metric in metrics_result:
                metric = {"query": query, "metricName": metric_query['metricName']}
                for k,v in returned_metric['metric'].items():
                    metric[k] = v
                
                if "values" in returned_metric: 
                    for value in returned_metric["values"]:
                        try:
                            metric['timestamp'] = str(datetime.datetime.fromtimestamp(value[0]))
                            metric["value"] = float(value[1])
                            # want double array of the known details and the metrics specific to each call                    
                            metrics_list.append(metric.copy())
                        except ValueError:
                            pass
                elif "value" in returned_metric:
                    try:
                        value = returned_metric["value"]
                        metric['timestamp'] = str(datetime.datetime.fromtimestamp(value[0]))
                        metric["value"] = float(value[1])

                        # want double array of the known details and the metrics specific to each call
                        metrics_list.append(metric.copy())
                    except ValueError:
                        pass
        telemetry_json = json.loads(telemetry_json)
        for scenario in telemetry_json['scenarios']:
            for k,v in scenario["affected_pods"].items():
                metric_name = "affected_pods_recovery"
                metric = {"metricName": metric_name, "type": k}
                if type(v) is list:
                    for pod in v:
                        for k,v in pod.items():
                            metric[k] = v
                            metric['timestamp'] = str(datetime.datetime.now())
                        print('adding pod' + str(metric))
                        metrics_list.append(metric.copy())
            for affected_node in scenario["affected_nodes"]:
                metric_name = "affected_nodes_recovery"
                metric = {"metricName": metric_name}
                for k,v in affected_node.items():
                    metric[k] = v
                    metric['timestamp'] = str(datetime.datetime.now())
                metrics_list.append(metric.copy())
        if telemetry_json['health_checks']:
            for health_check in telemetry_json["health_checks"]:
                    metric_name = "health_check_recovery"
                    metric = {"metricName": metric_name}
                    for k,v in health_check.items():
                        metric[k] = v
                        metric['timestamp'] = str(datetime.datetime.now())
                    metrics_list.append(metric.copy())
        if elastic is not None and elastic_metrics_index is not None and hasattr(elastic, 'upload_metrics_to_elasticsearch'):
            result = elastic.upload_metrics_to_elasticsearch(
                run_uuid=run_uuid, index=elastic_metrics_index, raw_data=metrics_list
            )
            if result == -1:
                logging.error("failed to save metrics on ElasticSearch")
                save_metrics = True
            else:
                save_metrics = False
        else:
            save_metrics = True
        if save_metrics:
            local_dir = os.path.join(tempfile.gettempdir(), "krkn_metrics")
            os.makedirs(local_dir, exist_ok=True)
            local_file = os.path.join(local_dir, f"{elastic_metrics_index}_{run_uuid}.json")

            try:
                with open(local_file, "w") as f:
                    json.dump({
                        "metadata": {
                            "run_uuid": run_uuid,
                        },
                        "metrics": metrics_list
                    }, f, indent=2)
                    logging.info(f"Metrics saved to {local_file}")
            except Exception as e:
                logging.error(f"Failed to save metrics to {local_file}: {e}")
    return metrics_list
