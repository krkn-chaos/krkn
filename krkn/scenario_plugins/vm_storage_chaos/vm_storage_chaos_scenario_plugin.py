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
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor


class VmStorageChaosScenarioPlugin(AbstractScenarioPlugin):

    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario, "r") as f:
                config = yaml.safe_load(f)

            scenario_config = config.get("vm_storage_chaos", config)
            action = get_yaml_item_value(scenario_config, "action", "kill_storage_service")
            storage_targets = get_yaml_item_value(scenario_config, "storage_targets", [])
            duration = get_yaml_item_value(scenario_config, "duration", 300)
            verify_vm_recovery = get_yaml_item_value(scenario_config, "verify_vm_recovery", True)
            recovery_timeout = get_yaml_item_value(scenario_config, "recovery_timeout", 600)

            if not storage_targets:
                logging.error("vm_storage_chaos: 'storage_targets' list is required")
                return 1

            ssh_executor = SSHExecutor(
                ssh_user=get_yaml_item_value(scenario_config, "ssh_user", "root"),
                ssh_private_key=os.path.expanduser(
                    get_yaml_item_value(scenario_config, "ssh_private_key", "~/.ssh/id_rsa")
                ),
                ssh_port=get_yaml_item_value(scenario_config, "ssh_port", 22),
            )

            affected_nodes_status = AffectedNodeStatus()

            if action == "kill_storage_service":
                return self._kill_storage_service(
                    ssh_executor, storage_targets, duration,
                    affected_nodes_status, scenario_telemetry,
                )
            elif action == "io_burst":
                return self._io_burst(
                    ssh_executor, storage_targets, duration,
                    scenario_config, affected_nodes_status, scenario_telemetry,
                )
            elif action == "fill_storage":
                return self._fill_storage(
                    ssh_executor, storage_targets, duration,
                    scenario_config, affected_nodes_status, scenario_telemetry,
                )
            else:
                logging.error(
                    "Unknown vm_storage_chaos action: %s. "
                    "Supported: kill_storage_service, io_burst, fill_storage" % action
                )
                return 1

        except Exception as e:
            logging.error("vm_storage_chaos exception: %s" % e)
            return 1

    def _kill_storage_service(
        self,
        ssh: SSHExecutor,
        storage_targets: list[dict],
        duration: int,
        affected_nodes_status: AffectedNodeStatus,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        for target in storage_targets:
            host = target.get("host", "")
            service = target.get("service", "nfs-server")
            safe_service = shlex.quote(service)

            if not host:
                logging.error("vm_storage_chaos: 'host' is required in storage_targets")
                return 1

            affected_node = AffectedNode(host)
            start_time = time.time()

            logging.info("[%s] Stopping storage service: %s" % (host, service))
            exit_code, _, stderr = ssh.execute(
                host, "sudo systemctl stop %s" % safe_service, timeout=60
            )
            if exit_code != 0:
                logging.error(
                    "[%s] Failed to stop %s: %s" % (host, service, stderr)
                )
                return 1

            logging.info(
                "[%s] Storage service %s stopped. Chaos active for %ds"
                % (host, service, duration)
            )
            threading.Event().wait(timeout=duration)


            logging.info("[%s] Restarting storage service: %s" % (host, service))
            start_exit, _, start_stderr = ssh.execute(
                host, "sudo systemctl start %s" % safe_service, timeout=60
            )
            if start_exit != 0:
                logging.error(
                    "[%s] Failed to restart %s: %s"
                    % (host, service, start_stderr)
                )

            recovery_time = time.time() - start_time
            affected_node.set_affected_node_status("recovered", recovery_time)
            affected_nodes_status.affected_nodes.append(affected_node)
            logging.info(
                "[%s] Storage service %s restored (total disruption: %.1fs)"
                % (host, service, recovery_time)
            )

        scenario_telemetry.affected_nodes.extend(
            affected_nodes_status.affected_nodes
        )
        return 0

    def _io_burst(
        self,
        ssh: SSHExecutor,
        storage_targets: list[dict],
        duration: int,
        config: dict,
        affected_nodes_status: AffectedNodeStatus,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        io_workers = get_yaml_item_value(config, "io_workers", 4)
        io_bytes = shlex.quote(
            str(get_yaml_item_value(config, "io_bytes", "1G"))
        )

        for target in storage_targets:
            host = target.get("host", "")
            target_path = target.get("path", "/var/lib/containers")

            if not host:
                logging.error("vm_storage_chaos: 'host' is required in storage_targets")
                return 1

            affected_node = AffectedNode(host)
            start_time = time.time()

            cmd = (
                "stress-ng --iomix %d --iomix-bytes %s "
                "--temp-path %s --timeout %ds --metrics-brief"
                % (io_workers, io_bytes, shlex.quote(target_path), duration)
            )

            logging.info("[%s] Starting IO burst: %s" % (host, cmd))
            exit_code, stdout, stderr = ssh.execute(
                host, cmd, timeout=duration + 120
            )

            recovery_time = time.time() - start_time
            affected_node.set_affected_node_status("completed", recovery_time)
            affected_nodes_status.affected_nodes.append(affected_node)

            if exit_code != 0:
                logging.error(
                    "[%s] IO burst failed (exit %d): %s" % (host, exit_code, stderr)
                )
                return 1

            logging.info("[%s] IO burst completed (%.1fs)" % (host, recovery_time))

        scenario_telemetry.affected_nodes.extend(
            affected_nodes_status.affected_nodes
        )
        return 0

    def _fill_storage(
        self,
        ssh: SSHExecutor,
        storage_targets: list[dict],
        duration: int,
        config: dict,
        affected_nodes_status: AffectedNodeStatus,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        fill_percentage = get_yaml_item_value(config, "fill_percentage", 90)

        for target in storage_targets:
            host = target.get("host", "")
            target_path = target.get("path", "/var/lib/containers")
            safe_path = shlex.quote(target_path)
            fill_file = "%s/krkn_storage_chaos_fill" % target_path
            safe_fill_file = shlex.quote(fill_file)

            if not host:
                logging.error("vm_storage_chaos: 'host' is required")
                return 1

            affected_node = AffectedNode(host)
            start_time = time.time()

            exit_code, stdout, _ = ssh.execute(
                host,
                "df --output=avail,size -B1 %s | tail -1" % safe_path,
                timeout=30,
            )
            if exit_code != 0:
                logging.error("[%s] Failed to get disk info" % host)
                return 1

            parts = stdout.strip().split()
            avail = int(parts[0])
            total = int(parts[1])
            used = total - avail
            target_used = int(total * fill_percentage / 100)
            fill_bytes = max(0, target_used - used)

            if fill_bytes == 0:
                logging.warning(
                    "[%s] Storage already at or above %d%%" % (host, fill_percentage)
                )
                continue

            logging.info(
                "[%s] Filling %s to %d%% (%d bytes)"
                % (host, target_path, fill_percentage, fill_bytes)
            )
            ssh.execute(
                host,
                "fallocate -l %d %s" % (fill_bytes, safe_fill_file),
                timeout=120,
            )

            logging.info(
                "[%s] Storage fill active for %ds" % (host, duration)
            )
            threading.Event().wait(timeout=duration)


            logging.info("[%s] Cleaning up storage fill" % host)
            ssh.execute(host, "rm -f %s" % safe_fill_file, timeout=30)

            recovery_time = time.time() - start_time
            affected_node.set_affected_node_status("recovered", recovery_time)
            affected_nodes_status.affected_nodes.append(affected_node)

        scenario_telemetry.affected_nodes.extend(
            affected_nodes_status.affected_nodes
        )
        return 0

    def supports_standalone(self) -> bool:
        return True

    def get_scenario_types(self) -> list[str]:
        return ["vm_storage_chaos_scenarios"]
