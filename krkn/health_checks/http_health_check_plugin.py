"""
HTTP Health Check Plugin

This plugin provides HTTP-based health checking functionality for monitoring
web services and API endpoints during chaos engineering experiments.

Example configuration in config.yaml:
    health_checks:
      type: http_health_check
      interval: 2
      config:
        - url: "http://example.com/health"
          bearer_token: "your-token"  # Optional
          auth: "username,password"   # Optional (basic auth)
          verify_url: true             # Optional, default: true
          exit_on_failure: false       # Optional, default: false
"""

import logging
import queue
import time
from datetime import datetime
from typing import Any

import requests
from krkn_lib.models.telemetry.models import HealthCheck

from krkn.health_checks.abstract_health_check_plugin import AbstractHealthCheckPlugin


class HttpHealthCheckPlugin(AbstractHealthCheckPlugin):
    """
    HTTP-based health check plugin that monitors web services by making periodic HTTP requests.

    This plugin tracks the health status of HTTP endpoints, detects status changes,
    and collects telemetry data about uptime and downtime periods.
    """

    def __init__(
        self,
        health_check_type: str = "http_health_check",
        iterations: int = 1,
        **kwargs
    ):
        """
        Initializes the HTTP health check plugin.

        :param health_check_type: the health check type identifier
        :param iterations: the number of chaos iterations to monitor
        :param kwargs: additional keyword arguments
        """
        super().__init__(health_check_type)
        self.iterations = iterations
        self.current_iterations = 0

    def get_health_check_types(self) -> list[str]:
        """
        Returns the health check types this plugin handles.

        :return: list of health check type identifiers
        """
        return ["http_health_check"]

    def get_config_key(self) -> str:
        """
        Returns the top-level config.yaml key this plugin reads from.

        :return: config key string
        """
        return "health_checks"

    def increment_iterations(self) -> None:
        """
        Increments the current iteration counter.

        :return: None
        """
        self.current_iterations += 1

    def make_request(
        self, url: str, auth=None, headers=None, verify: bool = True, timeout: int = 3
    ) -> dict[str, Any]:
        """
        Makes an HTTP GET request to the specified URL.

        :param url: the URL to request
        :param auth: optional authentication tuple (username, password)
        :param headers: optional HTTP headers dictionary
        :param verify: whether to verify SSL certificates
        :param timeout: request timeout in seconds
        :return: dictionary with url, status, and status_code
        """
        response_data = {}
        try:
            response = requests.get(
                url, auth=auth, headers=headers, verify=verify, timeout=timeout
            )
            response_data["url"] = url
            response_data["status"] = response.status_code == 200
            response_data["status_code"] = response.status_code
        except Exception as e:
            logging.warning(f"HTTP request to {url} failed: {e}")
            response_data["url"] = url
            response_data["status"] = False
            response_data["status_code"] = 500

        return response_data

    def run_health_check(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue,
    ) -> None:
        """
        Runs the HTTP health check monitoring loop.

        Continuously monitors the configured HTTP endpoints until the specified
        number of iterations is complete. Tracks status changes and collects
        telemetry data about uptime/downtime periods.

        :param config: the health check configuration dictionary
        :param telemetry_queue: a queue to put telemetry data for collection
        :return: None
        """
        if not config or not config.get("config") or not any(
            cfg.get("url") for cfg in config.get("config", [])
        ):
            logging.info("HTTP health check config is not defined, skipping")
            return

        health_check_telemetry = []
        health_check_tracker = {}
        interval = config.get("interval", 2)

        # Track current response status for each URL
        response_tracker = {
            cfg["url"]: True for cfg in config["config"] if cfg.get("url")
        }

        while self.current_iterations < self.iterations and not self._stop_event.is_set():
            for check_config in config.get("config", []):
                auth, headers = None, None
                verify_url = check_config.get("verify_url", True)
                url = check_config.get("url")

                if not url:
                    continue

                # Set up authentication
                if check_config.get("bearer_token"):
                    bearer_token = "Bearer " + check_config["bearer_token"]
                    headers = {"Authorization": bearer_token}

                if check_config.get("auth"):
                    auth = tuple(check_config["auth"].split(","))

                # Make the HTTP request
                try:
                    response = self.make_request(url, auth, headers, verify_url)
                except Exception as e:
                    logging.error(f"Exception during HTTP health check: {e}")
                    response = {
                        "url": url,
                        "status": False,
                        "status_code": 500
                    }

                # Track status changes
                if url not in health_check_tracker:
                    # First time seeing this URL in this run
                    start_timestamp = datetime.now()
                    health_check_tracker[url] = {
                        "status_code": response["status_code"],
                        "start_timestamp": start_timestamp,
                    }
                    if response["status_code"] != 200:
                        if response_tracker[url] != False:
                            response_tracker[url] = False
                        if (
                            check_config.get("exit_on_failure", False)
                            and self.ret_value == 0
                        ):
                            self.ret_value = 3
                else:
                    # Check if status changed
                    if (
                        response["status_code"]
                        != health_check_tracker[url]["status_code"]
                    ):
                        end_timestamp = datetime.now()
                        start_timestamp = health_check_tracker[url]["start_timestamp"]
                        previous_status_code = str(
                            health_check_tracker[url]["status_code"]
                        )
                        duration = (end_timestamp - start_timestamp).total_seconds()

                        # Record the status change period
                        change_record = {
                            "url": url,
                            "status": False,
                            "status_code": previous_status_code,
                            "start_timestamp": start_timestamp.isoformat(),
                            "end_timestamp": end_timestamp.isoformat(),
                            "duration": duration,
                        }

                        health_check_telemetry.append(HealthCheck(change_record))

                        if response_tracker[url] != True:
                            response_tracker[url] = True

                        # Reset tracker with new status
                        del health_check_tracker[url]

            time.sleep(interval)

        # Record final status for all tracked URLs
        health_check_end_timestamp = datetime.now()
        for url in health_check_tracker.keys():
            duration = (
                health_check_end_timestamp
                - health_check_tracker[url]["start_timestamp"]
            ).total_seconds()
            final_record = {
                "url": url,
                "status": True,
                "status_code": health_check_tracker[url]["status_code"],
                "start_timestamp": health_check_tracker[url][
                    "start_timestamp"
                ].isoformat(),
                "end_timestamp": health_check_end_timestamp.isoformat(),
                "duration": duration,
            }
            health_check_telemetry.append(HealthCheck(final_record))

        # Put telemetry data in the queue
        telemetry_queue.put(health_check_telemetry)
