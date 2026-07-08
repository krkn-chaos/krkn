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
"""
Standalone Host Health Check Plugin

Monitors remote host health (CPU, memory, disk, load, process, TCP port)
via SSH during standalone chaos experiments. Produces HealthCheck telemetry
compatible with the existing Elasticsearch pipeline.

Example configuration in config.yaml:
    standalone_health_checks:
      interval: 5
      ssh_user: root
      ssh_private_key: ~/.ssh/id_rsa
      ssh_port: 22
      config:
        - host: 192.168.1.100
          checks:
            - type: tcp
              port: 8080
            - type: process
              name: nginx
            - type: http
              url: http://192.168.1.100:8080/health
            - type: host_metrics
"""

import logging
import os
import queue
import time
from datetime import datetime
from typing import Any

import shlex

import requests
from krkn_lib.models.telemetry.models import HealthCheck
from krkn_lib.utils.functions import is_host_reachable

from krkn.health_checks.abstract_health_check_plugin import AbstractHealthCheckPlugin
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor


class StandaloneHostHealthCheckPlugin(AbstractHealthCheckPlugin):
    """
    SSH-based host health check plugin that monitors remote hosts
    during standalone chaos experiments.
    """

    def __init__(
        self,
        health_check_type: str = "standalone_host_health_check",
        iterations: int = 1,
        **kwargs,
    ):
        super().__init__(health_check_type)
        self.iterations = iterations
        self.current_iterations = 0

    def get_health_check_types(self) -> list[str]:
        return ["standalone_host_health_check"]

    def get_config_key(self) -> str:
        return "standalone_health_checks"

    def increment_iterations(self) -> None:
        self.current_iterations += 1

    def run_health_check(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue,
    ) -> None:
        if not config or not config.get("config"):
            logging.info(
                "Standalone host health check config not defined, skipping"
            )
            return

        interval = config.get("interval", 5)
        ssh_user = config.get("ssh_user", "root")
        ssh_private_key = os.path.expanduser(
            config.get("ssh_private_key", "~/.ssh/id_rsa")
        )
        ssh_port = config.get("ssh_port", 22)

        ssh_executor = SSHExecutor(
            ssh_user=ssh_user,
            ssh_private_key=ssh_private_key,
            ssh_port=ssh_port,
        )

        health_check_telemetry = []
        status_tracker = {}

        while (
            self.current_iterations < self.iterations
            and not self._stop_event.is_set()
        ):
            for host_config in config.get("config", []):
                host = host_config.get("host", "")
                if not host:
                    continue

                checks = host_config.get("checks", [{"type": "host_metrics"}])
                for check in checks:
                    check_type = check.get("type", "host_metrics")
                    check_key = "%s:%s" % (host, check_type)

                    status, status_code = self._run_check(
                        ssh_executor, host, check
                    )

                    if check_key not in status_tracker:
                        status_tracker[check_key] = {
                            "status": status,
                            "status_code": status_code,
                            "start_timestamp": datetime.now(),
                            "url": "%s/%s" % (host, check_type),
                        }
                    elif status != status_tracker[check_key]["status"]:
                        end_timestamp = datetime.now()
                        start_timestamp = status_tracker[check_key][
                            "start_timestamp"
                        ]
                        duration = (
                            end_timestamp - start_timestamp
                        ).total_seconds()

                        record = {
                            "url": status_tracker[check_key]["url"],
                            "status": status_tracker[check_key]["status"],
                            "status_code": status_tracker[check_key][
                                "status_code"
                            ],
                            "start_timestamp": start_timestamp.isoformat(),
                            "end_timestamp": end_timestamp.isoformat(),
                            "duration": duration,
                        }
                        health_check_telemetry.append(HealthCheck(record))

                        status_tracker[check_key] = {
                            "status": status,
                            "status_code": status_code,
                            "start_timestamp": end_timestamp,
                            "url": "%s/%s" % (host, check_type),
                        }

                        if not status and self.ret_value == 0:
                            exit_on_failure = host_config.get(
                                "exit_on_failure", False
                            )
                            if exit_on_failure:
                                self.ret_value = 3

            time.sleep(interval)

        end_timestamp = datetime.now()
        for check_key, tracker in status_tracker.items():
            duration = (
                end_timestamp - tracker["start_timestamp"]
            ).total_seconds()
            record = {
                "url": tracker["url"],
                "status": tracker["status"],
                "status_code": tracker["status_code"],
                "start_timestamp": tracker["start_timestamp"].isoformat(),
                "end_timestamp": end_timestamp.isoformat(),
                "duration": duration,
            }
            health_check_telemetry.append(HealthCheck(record))

        telemetry_queue.put(health_check_telemetry)

    def _run_check(
        self, ssh: SSHExecutor, host: str, check: dict
    ) -> tuple[bool, int]:
        """Run a single health check. Returns (status_bool, status_code_int)."""
        check_type = check.get("type", "host_metrics")

        try:
            if check_type == "tcp":
                return self._check_tcp(ssh, host, check.get("port", 80))
            elif check_type == "process":
                return self._check_process(
                    ssh, host, check.get("name", "")
                )
            elif check_type == "http":
                return self._check_http(check.get("url", ""))
            elif check_type == "host_metrics":
                return self._check_host_metrics(ssh, host)
            elif check_type == "command":
                return self._check_command(ssh, host, check.get("cmd", ""))
            else:
                logging.warning(
                    "Unknown check type: %s" % check_type
                )
                return False, 500
        except Exception as e:
            logging.debug(
                "[%s] Health check '%s' failed: %s" % (host, check_type, e)
            )
            return False, 500

    def _check_tcp(
        self, ssh: SSHExecutor, host: str, port: int
    ) -> tuple[bool, int]:
        reachable = is_host_reachable(host, port, timeout=3)
        return reachable, 200 if reachable else 503

    def _check_process(
        self, ssh: SSHExecutor, host: str, process_name: str
    ) -> tuple[bool, int]:
        if not process_name:
            return False, 400
        exit_code, _, _ = ssh.execute(
            host, "pgrep -f %s" % shlex.quote(process_name), timeout=10
        )
        return exit_code == 0, 200 if exit_code == 0 else 503

    def _check_http(self, url: str) -> tuple[bool, int]:
        try:
            response = requests.get(url, timeout=5, verify=False)
            return response.status_code == 200, response.status_code
        except Exception:
            return False, 503

    def _check_host_metrics(
        self, ssh: SSHExecutor, host: str
    ) -> tuple[bool, int]:
        exit_code, stdout, _ = ssh.execute(
            host,
            "cat /proc/loadavg | awk '{print $1}'; "
            "free -b | awk '/Mem:/{printf \"%.0f %.0f\\n\", $3, $2}'; "
            "df -B1 --output=pcent / | tail -1 | tr -d ' %%'",
            timeout=10,
        )
        if exit_code != 0:
            return False, 503

        lines = stdout.strip().split("\n")
        if len(lines) >= 3:
            load_avg = float(lines[0])
            mem_parts = lines[1].split()
            mem_used = int(mem_parts[0])
            mem_total = int(mem_parts[1])
            disk_pct = int(lines[2])

            logging.debug(
                "[%s] load=%.1f mem=%d/%d (%.0f%%) disk=%d%%"
                % (
                    host,
                    load_avg,
                    mem_used,
                    mem_total,
                    (mem_used / mem_total * 100) if mem_total > 0 else 0,
                    disk_pct,
                )
            )

        return True, 200

    ALLOWED_COMMAND_PREFIXES = (
        "systemctl status", "systemctl is-active",
        "pgrep", "pidof", "test", "cat /proc/loadavg",
        "uptime", "df ", "free ", "who", "ss ", "ip ",
    )

    def _check_command(
        self, ssh: SSHExecutor, host: str, cmd: str
    ) -> tuple[bool, int]:
        if not cmd:
            return False, 400
        if not any(cmd.startswith(prefix) for prefix in self.ALLOWED_COMMAND_PREFIXES):
            logging.warning(
                "[%s] Command not in allowed list: %s" % (host, cmd)
            )
            return False, 403
        exit_code, _, _ = ssh.execute(host, cmd, timeout=30)
        return exit_code == 0, 200 if exit_code == 0 else 503
