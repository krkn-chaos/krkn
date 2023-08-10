import subprocess
import logging
import urllib.request
import shutil
import sys
import requests
import tempfile
import kraken.prometheus.client as prometheus
from urllib.parse import urlparse


def setup(url):
    """
    Downloads and unpacks kube-burner binary
    """

    filename = "kube_burner.tar"
    try:
        logging.info("Fetching kube-burner binary")
        urllib.request.urlretrieve(url, filename)
    except Exception as e:
        logging.error("Failed to download kube-burner binary located at %s" % url, e)
        sys.exit(1)
    try:
        logging.info("Unpacking kube-burner tar ball")
        shutil.unpack_archive(filename)
    except Exception as e:
        logging.error("Failed to unpack the kube-burner binary tarball: %s" % e)
        sys.exit(1)


def scrape_metrics(
    distribution, uuid, prometheus_url, prometheus_bearer_token, start_time, end_time, config_path, metrics_profile
):
    """
    Scrapes metrics defined in the profile from Prometheus and indexes them into Elasticsearch
    """

    if not prometheus_url:
        if distribution == "openshift":
            logging.info("Looks like prometheus_url is not defined, trying to use the default instance on the cluster")
            prometheus_url, prometheus_bearer_token = prometheus.instance(
                distribution, prometheus_url, prometheus_bearer_token
            )
        else:
            logging.error("Looks like prometheus url is not defined, exiting")
            sys.exit(1)
    command = (
        "./kube-burner index --uuid "
        + str(uuid)
        + " -u "
        + str(prometheus_url)
        + " -t "
        + str(prometheus_bearer_token)
        + " -m "
        + str(metrics_profile)
        + " --start "
        + str(start_time)
        + " --end "
        + str(end_time)
        + " -c "
        + str(config_path)
    )
    try:
        logging.info("Running kube-burner to capture the metrics: %s" % command)
        logging.info("UUID for the run: %s" % uuid)
        subprocess.run(command, shell=True, universal_newlines=True)
    except Exception as e:
        logging.error("Failed to run kube-burner, error: %s" % (e))
        sys.exit(1)


def alerts(distribution, prometheus_url, prometheus_bearer_token, start_time, end_time, alert_profile):
    """
    Scrapes metrics defined in the profile from Prometheus and alerts based on the severity defined
    """

    is_url = urlparse(alert_profile)
    if is_url.scheme and is_url.netloc:
        response = requests.get(alert_profile)
        temp_alerts = tempfile.NamedTemporaryFile()
        temp_alerts.write(response.content)
        temp_alerts.flush()
        alert_profile = temp_alerts.name

    if not prometheus_url:
        if distribution == "openshift":
            logging.info("Looks like prometheus_url is not defined, trying to use the default instance on the cluster")
            prometheus_url, prometheus_bearer_token = prometheus.instance(
                distribution, prometheus_url, prometheus_bearer_token
            )
        else:
            logging.error("Looks like prometheus url is not defined, exiting")
            sys.exit(1)
    command = (
        "./kube-burner check-alerts "
        + " -u "
        + str(prometheus_url)
        + " -t "
        + str(prometheus_bearer_token)
        + " -a "
        + str(alert_profile)
        + " --start "
        + str(start_time)
        + " --end "
        + str(end_time)
    )
    try:
        logging.info("Running kube-burner to capture the metrics: %s" % command)
        output = subprocess.run(command, shell=True, universal_newlines=True)
        if output.returncode != 0:
            logging.error("command exited with a non-zero rc, please check the logs for errors or critical alerts")
            sys.exit(output.returncode)
    except Exception as e:
        logging.error("Failed to run kube-burner, error: %s" % (e))
        sys.exit(1)
