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
import shlex
import threading
import time

import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor


class StandaloneFileScenarioPlugin(AbstractScenarioPlugin):

    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        ssh_executor = None
        revert_data = {}
        action = ""
        file_path = ""
        try:
            with open(scenario, "r") as f:
                config = yaml.safe_load(f)

            targets = config.get("targets", [])
            if not targets:
                logging.error(
                    "standalone_file_scenarios: 'targets' list is required"
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

            action = config.get("action", "chmod")
            file_path = config.get("file_path", "")
            duration = config.get("duration", 0)

            if not file_path:
                logging.error("standalone_file_scenarios: 'file_path' is required")
                return 1

            for target in targets:
                revert_info = self._apply_file_chaos(
                    ssh_executor, target, action, file_path, config
                )
                revert_data[target] = revert_info

            if duration > 0:
                logging.info(
                    "File chaos active for %ds on %d target(s)"
                    % (duration, len(targets))
                )
                threading.Event().wait(timeout=duration)


                for target in targets:
                    self._revert_file_chaos(
                        ssh_executor, target, action, file_path,
                        revert_data.get(target, {})
                    )

            return 0
        except Exception as e:
            logging.error("standalone_file_scenarios exception: %s" % e)
            if ssh_executor and revert_data:
                for target in revert_data:
                    try:
                        self._revert_file_chaos(
                            ssh_executor, target, action, file_path,
                            revert_data[target]
                        )
                    except Exception as rollback_err:
                        logging.error(
                            "[%s] Rollback failed: %s" % (target, rollback_err)
                        )
            return 1

    def _apply_file_chaos(
        self,
        ssh: SSHExecutor,
        host: str,
        action: str,
        file_path: str,
        config: dict,
    ) -> dict:
        revert_info = {}
        safe_path = shlex.quote(file_path)

        if action == "chmod":
            exit_code, stdout, _ = ssh.execute(
                host, "stat -c '%%a' %s" % safe_path, timeout=10
            )
            if exit_code != 0:
                raise Exception("[%s] File not found: %s" % (host, file_path))
            revert_info["original_perms"] = stdout.strip()
            new_perms = config.get("permissions", "000")
            safe_perms = shlex.quote(new_perms)
            logging.info(
                "[%s] Changing permissions of %s from %s to %s"
                % (host, file_path, revert_info["original_perms"], new_perms)
            )
            ssh.execute(
                host, "sudo chmod %s %s" % (safe_perms, safe_path), timeout=10
            )

        elif action == "rename":
            target_path = config.get("target_path", file_path + ".krkn_bak")
            safe_target = shlex.quote(target_path)
            logging.info(
                "[%s] Renaming %s to %s" % (host, file_path, target_path)
            )
            ssh.execute(
                host, "sudo mv %s %s" % (safe_path, safe_target), timeout=10
            )
            revert_info["target_path"] = target_path

        elif action == "append":
            content = config.get("content", "# krkn chaos injection")
            count = config.get("count", 1)
            exit_code, stdout, _ = ssh.execute(
                host, "wc -c < %s" % safe_path, timeout=10
            )
            if exit_code != 0:
                raise Exception("[%s] File not found: %s" % (host, file_path))
            revert_info["original_size"] = stdout.strip()
            logging.info(
                "[%s] Appending %d line(s) to %s" % (host, count, file_path)
            )
            safe_content = shlex.quote(content)
            for _ in range(count):
                ssh.execute(
                    host,
                    "printf '%%s\\n' %s | sudo tee -a %s > /dev/null"
                    % (safe_content, safe_path),
                    timeout=10,
                )

        elif action == "delete":
            ssh.execute(
                host,
                "sudo cp %s %s.krkn_bak" % (safe_path, safe_path),
                timeout=10,
            )
            revert_info["backup_path"] = file_path + ".krkn_bak"
            logging.info("[%s] Deleting %s" % (host, file_path))
            ssh.execute(host, "sudo rm -f %s" % safe_path, timeout=10)

        else:
            raise ValueError(
                "Unknown file action: %s. Supported: chmod, rename, append, delete"
                % action
            )

        return revert_info

    def _revert_file_chaos(
        self,
        ssh: SSHExecutor,
        host: str,
        action: str,
        file_path: str,
        revert_info: dict,
    ) -> None:
        logging.info("[%s] Reverting file chaos on %s" % (host, file_path))
        safe_path = shlex.quote(file_path)

        if action == "chmod":
            original_perms = revert_info.get("original_perms", "644")
            ssh.execute(
                host, "sudo chmod %s %s" % (shlex.quote(original_perms), safe_path),
                timeout=10,
            )

        elif action == "rename":
            target_path = revert_info.get("target_path", file_path + ".krkn_bak")
            ssh.execute(
                host, "sudo mv %s %s" % (shlex.quote(target_path), safe_path),
                timeout=10,
            )

        elif action == "append":
            original_size = revert_info.get("original_size", "")
            if original_size:
                ssh.execute(
                    host,
                    "sudo truncate -s %s %s" % (shlex.quote(original_size), safe_path),
                    timeout=10,
                )

        elif action == "delete":
            backup_path = revert_info.get("backup_path", file_path + ".krkn_bak")
            ssh.execute(
                host, "sudo mv %s %s" % (shlex.quote(backup_path), safe_path),
                timeout=10,
            )

        logging.info("[%s] File chaos reverted on %s" % (host, file_path))

    def supports_standalone(self) -> bool:
        return True

    def get_scenario_types(self) -> list[str]:
        return ["standalone_file_scenarios"]
