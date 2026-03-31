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

import logging
import requests
import sys
import json
from krkn_lib.utils.functions import get_yaml_item_value

check_application_routes = ""
cerberus_url = None
exit_on_failure = False
cerberus_enabled = False

def set_url(config):
    global exit_on_failure
    exit_on_failure = get_yaml_item_value(config["kraken"], "exit_on_failure", False)
    global cerberus_enabled
    cerberus_enabled = get_yaml_item_value(config["cerberus"],"cerberus_enabled", False)
    if cerberus_enabled:
        global cerberus_url
        cerberus_url = get_yaml_item_value(config["cerberus"],"cerberus_url", "")
        global check_application_routes
        # Use None as sentinel to distinguish "key missing" from explicit False.
        # Only fall back to the legacy misspelled key when the correct key is absent.
        check_application_routes = get_yaml_item_value(
            config["cerberus"], "check_application_routes", None
        )
        if check_application_routes is None:
            legacy = get_yaml_item_value(
                config["cerberus"], "check_applicaton_routes", None
            )
            if legacy is not None:
                logging.warning(
                    "Config key 'check_applicaton_routes' is deprecated and will be "
                    "removed in a future release. Please rename it to 'check_application_routes'."
                )
                check_application_routes = legacy
            else:
                check_application_routes = ""


def get_status(start_time, end_time):
    """
    Get cerberus status — returns (cerberus_ok, routes_ok) booleans.
    Never calls sys.exit(); callers decide whether to exit.
    """
    cerberus_status = True
    application_routes_status = True
    if cerberus_enabled:
        if not cerberus_url:
            logging.error(
                "url where Cerberus publishes True/False signal "
                "is not provided."
            )
            return False, False
        cerberus_status = requests.get(cerberus_url, timeout=60).content
        cerberus_status = True if cerberus_status == b"True" else False

        # Fail if the application routes monitored by cerberus
        # experience downtime during the chaos
        if check_application_routes:
            application_routes_status, unavailable_routes = application_status(
                start_time,
                end_time
            )
            if not application_routes_status:
                logging.error(
                    "Application routes: %s monitored by cerberus "
                    "encountered downtime during the run, failing"
                    % unavailable_routes
                )
            else:
                logging.info(
                    "Application routes being monitored "
                    "didn't encounter any downtime during the run!"
                )

        if not cerberus_status:
            logging.error(
                "Received a no-go signal from Cerberus, looks like "
                "the cluster is unhealthy. Please check the Cerberus "
                "report for more details. Test failed."
            )
        elif application_routes_status:
            logging.info(
                "Received a go signal from Ceberus, the cluster is healthy. "
                "Test passed."
            )

    return cerberus_status, application_routes_status


def publish_kraken_status(start_time, end_time):
    """
    Publish kraken status to cerberus.
    Exits only when exit_on_failure is True and status is unhealthy.
    """
    cerberus_status, application_routes_status = get_status(start_time, end_time)
    overall_healthy = cerberus_status and application_routes_status

    if not overall_healthy:
        if exit_on_failure:
            logging.info("Cerberus status is not healthy, exiting kraken run")
            sys.exit(1)
        else:
            logging.info("Cerberus status is not healthy")


def application_status(start_time, end_time):
    """
    Check application availability
    """
    if not cerberus_url:
        logging.error(
            "url where Cerberus publishes True/False signal is not provided."
        )
        sys.exit(1)
    else:
        duration = (end_time - start_time) / 60
        url = "{baseurl}/history?loopback={duration}".format(
            baseurl=cerberus_url,
            duration=str(duration)
        )
        logging.info(
            "Scraping the metrics for the test "
            "duration from cerberus url: %s" % url
        )
        try:
            failed_routes = []
            status = True
            metrics = requests.get(url, timeout=60).content
            metrics_json = json.loads(metrics)
            for entry in metrics_json["history"]["failures"]:
                if entry["component"] == "route":
                    name = entry["name"]
                    failed_routes.append(name)
                    status = False
                else:
                    continue
        except Exception as e:
            logging.error(
                "Failed to scrape metrics from cerberus API at %s: %s" % (
                    url,
                    e
                )
            )
            sys.exit(1)
    return status, set(failed_routes)
