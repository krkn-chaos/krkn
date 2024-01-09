import datetime
import os.path
import urllib3
import logging
import sys

import yaml
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