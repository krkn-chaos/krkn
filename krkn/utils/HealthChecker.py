import server as server
import requests
import time
import logging
import queue
from datetime import datetime
import pdb


class HealthChecker:
    current_iterations: int = 0

    def __init__(self, iterations):
        self.iterations = iterations

    def make_request(self, url, args):
        response_data = {}
        response = requests.get(url, args, verify=False)

        response_data["url"] = url
        response_data["status"] = True if response.status_code == 200 else False
        response_data["status_code"] = response.status_code
        logging.info(response_data)
        return response_data

    def run_health_check(self, config: any, health_check_telemetry_queue: queue.Queue):
        auth = config["auth"]
        bearer_token = config["bearer_token"]
        urls = config["urls"]
        interval = config["interval"] if config["interval"] else 2
        health_check_telemetry = []
        request_args = {}
        headers = {}
        if bearer_token: headers["Authorization"] = "Bearer " + bearer_token
        if auth: request_args["auth"] = auth
        if headers: request_args["headers"] = headers

        health_check_tracker = {}
        while self.current_iterations < self.iterations:
            for url in urls:
                response = self.make_request(url, request_args)
                if response["status_code"] != 200:
                    if url not in health_check_tracker:
                        start_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        health_check_tracker[url] = {
                            "status_code": response["status_code"],
                            "start_timestamp": start_timestamp
                        }
                else:
                    if url in health_check_tracker:
                        end_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        start_timestamp = health_check_tracker[url]["start_timestamp"]
                        previous_status_code = str(health_check_tracker[url]["status_code"])

                        start_time = datetime.strptime(start_timestamp, "%Y-%m-%d %H:%M:%S")
                        end_time = datetime.strptime(end_timestamp, "%Y-%m-%d %H:%M:%S")
                        duration = str(end_time - start_time)

                        downtime_record = {
                            "url": url,
                            "status_code": previous_status_code,
                            "start_timestamp": start_timestamp,
                            "end_timestamp": end_timestamp,
                            "duration": duration
                        }

                        health_check_telemetry.append(downtime_record)
                        del health_check_tracker[url]
            time.sleep(interval)
        health_check_telemetry_queue.put(health_check_telemetry)

