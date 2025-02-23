import requests
import time
import logging
import queue
from datetime import datetime

class HealthChecker:
    current_iterations: int = 0
    ret_value = 0
    def __init__(self, iterations):
        self.iterations = iterations

    def make_request(self, url, auth=None, headers=None):
        response_data = {}
        response = requests.get(url, auth=auth, headers=headers)
        response_data["url"] = url
        response_data["status"] = response.status_code == 200
        response_data["status_code"] = response.status_code
        return response_data


    def run_health_check(self, health_check_config, health_check_telemetry_queue: queue.Queue):
        if health_check_config and health_check_config["config"] and any(config.get("url") for config in health_check_config["config"]):
            health_check_start_time_stamp = datetime.now()
            health_check_telemetry = []
            health_check_tracker = {}
            interval = health_check_config["interval"] if health_check_config["interval"] else 2
            response_tracker = {config["url"]:True for config in health_check_config["config"]}
            while self.current_iterations < self.iterations:
                for config in health_check_config.get("config"):
                    auth, headers = None, None
                    if config["url"]: url = config["url"]

                    if config["bearer_token"]:
                        bearer_token = "Bearer " + config["bearer_token"]
                        headers = {"Authorization": bearer_token}

                    if config["auth"]: auth = config["auth"]
                    response = self.make_request(url, auth, headers)

                    if response["status_code"] != 200:
                        if config["url"] not in health_check_tracker:
                            start_timestamp = datetime.now()
                            health_check_tracker[config["url"]] = {
                                "status_code": response["status_code"],
                                "start_timestamp": start_timestamp
                            }
                            if response_tracker[config["url"]] != False: response_tracker[config["url"]] = False
                            if config["exit_on_failure"] and config["exit_on_failure"] == True and self.ret_value==0: self.ret_value = 2
                    else:
                        if config["url"] in health_check_tracker:
                            end_timestamp = datetime.now()
                            start_timestamp = health_check_tracker[config["url"]]["start_timestamp"]
                            previous_status_code = str(health_check_tracker[config["url"]]["status_code"])
                            duration = (end_timestamp - start_timestamp).total_seconds()
                            downtime_record = {
                                "url": config["url"],
                                "status": False,
                                "status_code": previous_status_code,
                                "start_timestamp": start_timestamp.isoformat(),
                                "end_timestamp": end_timestamp.isoformat(),
                                "duration": duration
                            }
                            health_check_telemetry.append(downtime_record)
                            del health_check_tracker[config["url"]]
                    time.sleep(interval)
            health_check_end_time_stamp = datetime.now()
            for url, status in response_tracker.items():
                if status == True:
                    duration = (health_check_end_time_stamp - health_check_start_time_stamp).total_seconds()
                    success_response ={
                        "url": url,
                        "status": True,
                        "status_code": 200,
                        "start_timestamp": health_check_start_time_stamp.isoformat(),
                        "end_timestamp": health_check_end_time_stamp.isoformat(),
                        "duration": duration
                    }
                    health_check_telemetry.append(success_response)
            health_check_telemetry_queue.put(health_check_telemetry)
        else:
            logging.info("health checks config is not defined, skipping them")
