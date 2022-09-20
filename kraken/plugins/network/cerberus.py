import logging
import requests
import sys
import json


def get_status(config, start_time, end_time):
    """
    Function to get Cerberus status
    
    Args:
        config
            - Kraken config dictionary

        start_time
            - The time when chaos is injected
        
        end_time
            - The time when chaos is removed

    Returns:
        Cerberus status
    """
    
    cerberus_status = True
    check_application_routes = False
    application_routes_status = True
    if config["cerberus"]["cerberus_enabled"]:
        cerberus_url = config["cerberus"]["cerberus_url"]
        check_application_routes = config["cerberus"]["check_applicaton_routes"]
        if not cerberus_url:
            logging.error("url where Cerberus publishes True/False signal is not provided.")
            sys.exit(1)
        cerberus_status = requests.get(cerberus_url, timeout=60).content
        cerberus_status = True if cerberus_status == b"True" else False

        # Fail if the application routes monitored by cerberus experience downtime during the chaos
        if check_application_routes:
            application_routes_status, unavailable_routes = application_status(cerberus_url, start_time, end_time)
            if not application_routes_status:
                logging.error(
                    "Application routes: %s monitored by cerberus encountered downtime during the run, failing"
                    % unavailable_routes
                )
            else:
                logging.info("Application routes being monitored didn't encounter any downtime during the run!")

        if not cerberus_status:
            logging.error(
                "Received a no-go signal from Cerberus, looks like "
                "the cluster is unhealthy. Please check the Cerberus "
                "report for more details. Test failed."
            )

        if not application_routes_status or not cerberus_status:
            sys.exit(1)
        else:
            logging.info("Received a go signal from Ceberus, the cluster is healthy. " "Test passed.")
    return cerberus_status


def publish_kraken_status(config, failed_post_scenarios, start_time, end_time):
    """
    Function to publish Kraken status to Cerberus
    
    Args:
        config
            - Kraken config dictionary
        
        failed_post_scenarios
            - String containing the failed post scenarios

        start_time
            - The time when chaos is injected
        
        end_time
            - The time when chaos is removed
    """

    cerberus_status = get_status(config, start_time, end_time)
    if not cerberus_status:
        if failed_post_scenarios:
            if config["kraken"]["exit_on_failure"]:
                logging.info(
                    "Cerberus status is not healthy and post action scenarios " "are still failing, exiting kraken run"
                )
                sys.exit(1)
            else:
                logging.info("Cerberus status is not healthy and post action scenarios " "are still failing")
    else:
        if failed_post_scenarios:
            if config["kraken"]["exit_on_failure"]:
                logging.info(
                    "Cerberus status is healthy but post action scenarios " "are still failing, exiting kraken run"
                )
                sys.exit(1)
            else:
                logging.info("Cerberus status is healthy but post action scenarios " "are still failing")


def application_status(cerberus_url, start_time, end_time):
    """
    Function to check application availability
    
    Args:
        cerberus_url
            - url where Cerberus publishes True/False signal

        start_time
            - The time when chaos is injected
        
        end_time
            - The time when chaos is removed

    Returns:
        Application status and failed routes
    """
    
    if not cerberus_url:
        logging.error("url where Cerberus publishes True/False signal is not provided.")
        sys.exit(1)
    else:
        duration = (end_time - start_time) / 60
        url = cerberus_url + "/" + "history" + "?" + "loopback=" + str(duration)
        logging.info("Scraping the metrics for the test duration from cerberus url: %s" % url)
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
            logging.error("Failed to scrape metrics from cerberus API at %s: %s" % (url, e))
            sys.exit(1)
    return status, set(failed_routes)
