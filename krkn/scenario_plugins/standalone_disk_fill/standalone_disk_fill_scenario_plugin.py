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
import os
import re
import shlex
import threading
import time

import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor

FILL_FILE_NAME = "krkn_disk_fill_chaos"


class StandaloneDiskFillScenarioPlugin(AbstractScenarioPlugin):

    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        ssh_executor = None
        fill_path = "/tmp"
        targets = []
        filled_hosts = []
        try:
            with open(scenario, "r") as f:
                config = yaml.safe_load(f)

            targets = config.get("targets", [])
            if not targets:
                logging.error(
                    "standalone_disk_fill_scenarios: 'targets' list is required"
                )
                return 1

            ssh_executor = SSHExecutor(
                ssh_user=config.get("ssh_user", "root"),
                ssh_private_key=os.path.expanduser(
                    config.get("ssh_private_key", "~/.ssh/id_rsa")
                ),
                ssh_port=config.get("ssh_port", 22),
                connect_timeout=config.get("ssh_connect_timeout", 30),
            )

            fill_path = config.get("fill_path", "/tmp")
            fill_size = config.get("fill_size", "")
            fill_percentage = config.get("fill_percentage", 0)
            duration = config.get("duration", 60)

            if fill_size and not re.match(r"^\d+[BKMGT]?$", fill_size, re.IGNORECASE):
                logging.error(
                    "standalone_disk_fill_scenarios: invalid fill_size format: %s" % fill_size
                )
                return 1

            if not fill_size and not fill_percentage:
                logging.error(
                    "standalone_disk_fill_scenarios: "
                    "either 'fill_size' or 'fill_percentage' is required"
                )
                return 1

            filled_hosts = []
            for target in targets:
                self._fill_disk(
                    ssh_executor, target, fill_path, fill_size, fill_percentage
                )
                filled_hosts.append(target)

            logging.info(
                "Disk fill active for %ds on %d target(s)"
                % (duration, len(filled_hosts))
            )
            threading.Event().wait(timeout=duration)


            for target in filled_hosts:
                self._cleanup(ssh_executor, target, fill_path)

            return 0
        except Exception as e:
            logging.error("standalone_disk_fill_scenarios exception: %s" % e)
            if ssh_executor:
                for target in filled_hosts:
                    try:
                        self._cleanup(ssh_executor, target, fill_path)
                    except Exception:
                        pass
            return 1

    def _fill_disk(
        self,
        ssh: SSHExecutor,
        host: str,
        fill_path: str,
        fill_size: str,
        fill_percentage: int,
    ) -> None:
        safe_path = shlex.quote(fill_path)
        fill_file = "%s/%s" % (fill_path, FILL_FILE_NAME)
        safe_fill_file = shlex.quote(fill_file)

        if fill_size:
            logging.info(
                "[%s] Filling %s with %s" % (host, fill_path, fill_size)
            )
            cmd = "fallocate -l %s %s" % (shlex.quote(fill_size), safe_fill_file)
        else:
            logging.info(
                "[%s] Filling %s to %d%%" % (host, fill_path, fill_percentage)
            )
            exit_code, stdout, _ = ssh.execute(
                host,
                "df --output=avail,size -B1 %s | tail -1" % safe_path,
                timeout=30,
            )
            if exit_code != 0:
                raise Exception("[%s] Failed to get disk info for %s" % (host, fill_path))
            parts = stdout.strip().split()
            avail = int(parts[0])
            total = int(parts[1])
            used = total - avail
            target_used = int(total * fill_percentage / 100)
            fill_bytes = max(0, target_used - used)
            if fill_bytes == 0:
                logging.warning(
                    "[%s] Disk already at or above %d%%" % (host, fill_percentage)
                )
                return
            cmd = "fallocate -l %d %s" % (fill_bytes, safe_fill_file)

        exit_code, _, stderr = ssh.execute(host, cmd, timeout=120)
        if exit_code != 0:
            if fill_size:
                fill_bytes = self._parse_size_to_bytes(fill_size)
            fill_mb = max(1, fill_bytes // (1024 * 1024))
            cmd_dd = "dd if=/dev/zero of=%s bs=1M count=%d" % (safe_fill_file, fill_mb)
            logging.warning(
                "[%s] fallocate failed, falling back to dd" % host
            )
            ssh.execute(host, cmd_dd, timeout=300)

        logging.info("[%s] Disk fill complete: %s" % (host, fill_file))

    @staticmethod
    def _parse_size_to_bytes(size_str: str) -> int:
        """Parse a human-readable size string (e.g. '1G', '500M') to bytes."""
        units = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        size_str = size_str.strip().upper()
        if size_str[-1] in units:
            return int(size_str[:-1]) * units[size_str[-1]]
        return int(size_str)

    def _cleanup(self, ssh: SSHExecutor, host: str, fill_path: str = "/tmp") -> None:
        fill_file = "%s/%s" % (fill_path, FILL_FILE_NAME)
        safe_fill_file = shlex.quote(fill_file)
        logging.info("[%s] Removing disk fill file: %s" % (host, fill_file))
        ssh.execute(host, "rm -f %s" % safe_fill_file, timeout=30)
        logging.info("[%s] Disk fill cleaned up" % host)

    def supports_standalone(self) -> bool:
        return True

    def get_scenario_types(self) -> list[str]:
        return ["standalone_disk_fill_scenarios"]
