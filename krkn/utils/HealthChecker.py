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

import requests
import time
import logging
import queue
from datetime import datetime
from krkn_lib.models.telemetry.models import HealthCheck

class HealthChecker:
    def __init__(self, iterations):
        self.iterations = iterations
        self.current_iterations: int = 0
        self.ret_value = 0

    def make_request(self, url, auth=None, headers=None, verify=True):
        response_data = {}
        response = requests.get(url, auth=auth, headers=headers, verify=verify, timeout=3)
        response_data["url"] = url
        response_data["status"] = response.status_code == 200
        response_data["status_code"] = response.status_code
        return response_data


    def run_health_check(self, health_check_config, health_check_telemetry_queue: queue.Queue):        
        if health_check_config and health_check_config["config"] and any(config.get("url") for config in health_check_config["config"]):
            health_check_telemetry = []
            health_check_tracker = {}
            interval = health_check_config["interval"] if health_check_config["interval"] else 2
            
            response_tracker = {config["url"]:True for config in health_check_config["config"]}
            while self.current_iterations < self.iterations:
                for config in health_check_config.get("config"):
                    auth, headers = None, None
                    verify_url = config["verify_url"] if "verify_url" in config else True
                    if config["url"]: url = config["url"]

                    if config["bearer_token"]:
                        bearer_token = "Bearer " + config["bearer_token"]
                        headers = {"Authorization": bearer_token}
                    if config["auth"]: auth = tuple(config["auth"].split(','))
                    try: 
                        response = self.make_request(url, auth, headers, verify_url)
                    except Exception:
                        response = {}
                        response['status_code'] = 500
                    
                    if config["url"] not in health_check_tracker:
                        start_timestamp = datetime.now()
                        health_check_tracker[config["url"]] = {
                            "status_code": response["status_code"],
                            "start_timestamp": start_timestamp
                        }
                        if response["status_code"] != 200:
                            if response_tracker[config["url"]] is not False:
                                response_tracker[config["url"]] = False
                            if config["exit_on_failure"] is True and self.ret_value == 0:
                                self.ret_value = 2
                    else:
                            if response["status_code"] != health_check_tracker[config["url"]]["status_code"]:
                                end_timestamp = datetime.now()
                                start_timestamp = health_check_tracker[config["url"]]["start_timestamp"]
                                previous_status_code = str(health_check_tracker[config["url"]]["status_code"])
                                duration = (end_timestamp - start_timestamp).total_seconds()
                                change_record = {
                                    "url": config["url"],
                                    "status": False,
                                    "status_code": previous_status_code,
                                    "start_timestamp": start_timestamp.isoformat(),
                                    "end_timestamp": end_timestamp.isoformat(),
                                    "duration": duration
                                }

                                health_check_telemetry.append(HealthCheck(change_record))
                                if response_tracker[config["url"]] != True: response_tracker[config["url"]] = True
                                del health_check_tracker[config["url"]]
                    time.sleep(interval)
            health_check_end_time_stamp = datetime.now()
            for url in health_check_tracker.keys():
                duration = (health_check_end_time_stamp - health_check_tracker[url]["start_timestamp"]).total_seconds()
                success_response = {
                    "url": url,
                    "status": True,
                    "status_code": health_check_tracker[url]["status_code"],
                    "start_timestamp": health_check_tracker[url]["start_timestamp"].isoformat(),
                    "end_timestamp": health_check_end_time_stamp.isoformat(),
                    "duration": duration
                }
                health_check_telemetry.append(HealthCheck(success_response))

            health_check_telemetry_queue.put(health_check_telemetry)
        else:
            logging.info("health checks config is not defined, skipping them")
        return self.ret_value
