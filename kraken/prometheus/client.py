import datetime
import os.path
from typing import Optional

import urllib3
import logging
import sys

import yaml
from krkn_lib.models.krkn import ChaosRunAlertSummary, ChaosRunAlert
from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
def alerts(prom_cli: KrknPrometheus, start_time, end_time, alert_profile):

    if alert_profile is None or os.path.exists(alert_profile) is False:
        logging.error(f"{alert_profile} alert profile does not exist")
        sys.exit(1)

    with open(alert_profile) as profile:
        profile_yaml = yaml.safe_load(profile)
        if not isinstance(profile_yaml, list):
            logging.error(f"{alert_profile} wrong file format, alert profile must be "
                          f"a valid yaml file containing a list of items with 3 properties: "
                          f"expr, description, severity" )
            sys.exit(1)

        for alert in profile_yaml:
            if list(alert.keys()).sort() != ["expr", "description", "severity"].sort():
                logging.error(f"wrong alert {alert}, skipping")

            prom_cli.process_alert(alert,
                                   datetime.datetime.fromtimestamp(start_time),
                                   datetime.datetime.fromtimestamp(end_time))


def critical_alerts(prom_cli: KrknPrometheus,
                    summary: ChaosRunAlertSummary,
                    run_id,
                    scenario,
                    start_time,
                    end_time):
    summary.scenario = scenario
    summary.run_id = run_id
    query = r"""ALERTS{severity="critical"}"""
    logging.info("Checking for critical alerts firing post chaos")

    during_critical_alerts = prom_cli.process_prom_query_in_range(
        query,
        start_time=datetime.datetime.fromtimestamp(start_time),
        end_time=end_time

    )

    for alert in during_critical_alerts:
        if "metric" in alert:
            alertname = alert["metric"]["alertname"] if "alertname" in alert["metric"] else "none"
            alertstate = alert["metric"]["alertstate"] if "alertstate" in alert["metric"] else "none"
            namespace = alert["metric"]["namespace"] if "namespace" in alert["metric"] else "none"
            severity = alert["metric"]["severity"] if "severity" in alert["metric"] else "none"
            alert = ChaosRunAlert(alertname, alertstate, namespace, severity)
            summary.chaos_alerts.append(alert)


    post_critical_alerts = prom_cli.process_query(
        query
    )

    for alert in post_critical_alerts:
        if "metric" in alert:
            alertname = alert["metric"]["alertname"] if "alertname" in alert["metric"] else "none"
            alertstate = alert["metric"]["alertstate"] if "alertstate" in alert["metric"] else "none"
            namespace = alert["metric"]["namespace"] if "namespace" in alert["metric"] else "none"
            severity = alert["metric"]["severity"] if "severity" in alert["metric"] else "none"
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
