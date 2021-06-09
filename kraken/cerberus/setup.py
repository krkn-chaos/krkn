import logging
import requests
import sys


# Get cerberus status
def get_status(config):
    cerberus_status = True
    if config["cerberus"]["cerberus_enabled"]:
        cerberus_url = config["cerberus"]["cerberus_url"]
        if not cerberus_url:
            logging.error("url where Cerberus publishes True/False signal is not provided.")
            sys.exit(1)
        cerberus_status = requests.get(cerberus_url).content
        cerberus_status = True if cerberus_status == b"True" else False
        if not cerberus_status:
            logging.error(
                "Received a no-go signal from Cerberus, looks like "
                "the cluster is unhealthy. Please check the Cerberus "
                "report for more details. Test failed."
            )
            sys.exit(1)
        else:
            logging.info("Received a go signal from Ceberus, the cluster is healthy. " "Test passed.")
    return cerberus_status


# Function to publish kraken status to cerberus
def publish_kraken_status(config, failed_post_scenarios):
    cerberus_status = get_status(config)
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
