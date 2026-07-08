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
import shutil
import subprocess
import threading
import time

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor


class VmMigrationChaosScenarioPlugin(AbstractScenarioPlugin):

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

            scenario_config = config.get("vm_migration_chaos", config)
            kubecli = lib_telemetry.get_lib_kubernetes()

            if kubecli is None:
                logging.error(
                    "vm_migration_chaos requires Kubernetes API access"
                )
                return 1

            action = get_yaml_item_value(
                scenario_config, "migration_action", "trigger_and_disrupt"
            )
            vm_name = get_yaml_item_value(scenario_config, "vm_name", "")
            vm_namespace = get_yaml_item_value(
                scenario_config, "vm_namespace", "default"
            )
            fault_type = get_yaml_item_value(
                scenario_config, "fault_type", "network_latency"
            )
            fault_params = get_yaml_item_value(
                scenario_config, "fault_params", {}
            )
            timeout = get_yaml_item_value(scenario_config, "timeout", 600)
            verify_no_dual_pods = get_yaml_item_value(
                scenario_config, "verify_no_dual_pods", True
            )

            if not vm_name:
                logging.error("vm_migration_chaos: 'vm_name' is required")
                return 1

            if action == "trigger_and_disrupt":
                return self._trigger_and_disrupt(
                    kubecli, vm_name, vm_namespace, fault_type,
                    fault_params, timeout, verify_no_dual_pods,
                    scenario_config, scenario_telemetry,
                )
            elif action == "drain_node":
                return self._drain_node(
                    kubecli, vm_name, vm_namespace, timeout,
                    verify_no_dual_pods, scenario_telemetry,
                )
            else:
                logging.error(
                    "Unknown migration_action: %s. "
                    "Supported: trigger_and_disrupt, drain_node" % action
                )
                return 1

        except Exception as e:
            logging.error("vm_migration_chaos exception: %s" % e)
            return 1

    def _create_vmim(
        self, kubecli: KrknKubernetes, vm_name: str, vm_namespace: str,
    ) -> bool:
        """Create a VirtualMachineInstanceMigration object."""
        vmim_body = {
            "apiVersion": "kubevirt.io/v1",
            "kind": "VirtualMachineInstanceMigration",
            "metadata": {
                "name": "krkn-migration-%s" % vm_name,
                "namespace": vm_namespace,
            },
            "spec": {"vmiName": vm_name},
        }
        try:
            kubecli.custom_object_client.create_namespaced_custom_object(
                group="kubevirt.io", version="v1",
                namespace=vm_namespace,
                plural="virtualmachineinstancemigrations",
                body=vmim_body,
            )
            return True
        except Exception as e:
            logging.error("Failed to create VMIM: %s" % e)
            return False

    def _trigger_and_disrupt(
        self,
        kubecli: KrknKubernetes,
        vm_name: str,
        vm_namespace: str,
        fault_type: str,
        fault_params: dict,
        timeout: int,
        verify_no_dual_pods: bool,
        config: dict,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        vmi = kubecli.get_vmi(vm_name, vm_namespace)
        if not vmi:
            logging.error("VMI %s not found in namespace %s" % (vm_name, vm_namespace))
            return 1

        source_node = vmi.get("status", {}).get("nodeName", "")
        logging.info("VMI %s running on node %s" % (vm_name, source_node))

        affected_node = AffectedNode(vm_name)
        start_time = time.time()

        if not self._create_vmim(kubecli, vm_name, vm_namespace):
            return 1
        logging.info("VMIM created. Waiting for migration to start...")
        time.sleep(5)

        fault_thread = threading.Thread(
            target=self._inject_fault,
            args=(config, source_node, fault_type, fault_params),
        )
        fault_thread.start()

        migration_success = self._wait_for_migration(
            kubecli, vm_name, vm_namespace, timeout
        )
        fault_duration = int(fault_params.get("duration", 30))
        fault_thread.join(timeout=fault_duration + 60)

        if verify_no_dual_pods and self._check_dual_pods(kubecli, vm_name, vm_namespace):
            logging.error(
                "CRITICAL: Two virt-launcher pods detected for VMI %s "
                "(reproduces CNV-89391)" % vm_name
            )
            return 1

        recovery_time = time.time() - start_time
        vmi_post = kubecli.get_vmi(vm_name, vm_namespace)
        post_node = vmi_post.get("status", {}).get("nodeName", "") if vmi_post else "unknown"

        if migration_success:
            affected_node.set_affected_node_status("migrated", recovery_time)
            logging.info("VMI %s migrated %s→%s (%.1fs)" % (vm_name, source_node, post_node, recovery_time))
        else:
            affected_node.set_affected_node_status("migration_failed", recovery_time)
            logging.error("VMI %s migration failed or timed out" % vm_name)

        scenario_telemetry.affected_nodes.append(affected_node)
        self._cleanup_vmim(kubecli, vm_name, vm_namespace)

        return 0 if migration_success else 1

    def _drain_node(
        self,
        kubecli: KrknKubernetes,
        vm_name: str,
        vm_namespace: str,
        timeout: int,
        verify_no_dual_pods: bool,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        vmi = kubecli.get_vmi(vm_name, vm_namespace)
        if not vmi:
            logging.error("VMI %s not found" % vm_name)
            return 1

        source_node = vmi.get("status", {}).get("nodeName", "")
        affected_node = AffectedNode(vm_name)
        start_time = time.time()

        logging.info(
            "Cordoning and draining node %s (VMI %s should migrate)"
            % (source_node, vm_name)
        )

        kubectl_bin = shutil.which("oc") or shutil.which("kubectl")
        if not kubectl_bin:
            logging.error(
                "Neither 'oc' nor 'kubectl' found in PATH"
            )
            return 1

        try:
            subprocess.run(
                [kubectl_bin, "adm", "cordon", source_node],
                check=True, capture_output=True, text=True,
                timeout=60,
            )
            subprocess.run(
                [kubectl_bin, "adm", "drain", source_node,
                 "--ignore-daemonsets", "--delete-emptydir-data",
                 "--timeout=%ds" % timeout],
                check=True, capture_output=True, text=True,
                timeout=timeout + 60,
            )
        except subprocess.CalledProcessError as e:
            logging.warning(
                "Node drain encountered issue: %s" % e.stderr
            )
        except Exception as e:
            logging.warning("Node drain encountered issue: %s" % e)

        migration_success = self._wait_for_migration(
            kubecli, vm_name, vm_namespace, timeout
        )

        recovery_time = time.time() - start_time

        try:
            subprocess.run(
                [kubectl_bin, "adm", "uncordon", source_node],
                check=True, capture_output=True, text=True,
                timeout=60,
            )
        except Exception:
            pass

        if migration_success:
            affected_node.set_affected_node_status("evacuated", recovery_time)
            logging.info(
                "VMI %s evacuated from %s (%.1fs)" % (vm_name, source_node, recovery_time)
            )
        else:
            affected_node.set_affected_node_status("evacuation_failed", recovery_time)
            logging.error(
                "VMI %s NOT evacuated from %s (reproduces CNV-81533)"
                % (vm_name, source_node)
            )

        scenario_telemetry.affected_nodes.append(affected_node)
        return 0 if migration_success else 1

    def _inject_fault(
        self,
        config: dict,
        source_node: str,
        fault_type: str,
        fault_params: dict,
    ) -> None:
        duration = fault_params.get("duration", 30)

        ssh_executor = SSHExecutor(
            ssh_user=get_yaml_item_value(config, "ssh_user", "core"),
            ssh_private_key=os.path.expanduser(
                get_yaml_item_value(config, "ssh_private_key", "~/.ssh/id_rsa")
            ),
            ssh_port=get_yaml_item_value(config, "ssh_port", 22),
        )

        try:
            if fault_type == "network_latency":
                latency = shlex.quote(
                    str(fault_params.get("latency", "500ms"))
                )
                iface = shlex.quote(
                    str(fault_params.get("interface", "br-ex"))
                )
                logging.info(
                    "[%s] Injecting %s network latency on %s for %ds"
                    % (source_node, latency, iface, duration)
                )
                ssh_executor.execute(
                    source_node,
                    "sudo tc qdisc add dev %s root netem delay %s"
                    % (iface, latency),
                    timeout=30,
                )
                time.sleep(duration)
                ssh_executor.execute(
                    source_node,
                    "sudo tc qdisc del dev %s root" % iface,
                    timeout=30,
                )

            elif fault_type == "network_partition":
                target_ip = shlex.quote(
                    str(fault_params.get("target_ip", ""))
                )
                logging.info(
                    "[%s] Blocking traffic to %s for %ds"
                    % (source_node, target_ip, duration)
                )
                ssh_executor.execute(
                    source_node,
                    "sudo iptables -A OUTPUT -d %s -j DROP" % target_ip,
                    timeout=30,
                )
                time.sleep(duration)
                ssh_executor.execute(
                    source_node,
                    "sudo iptables -D OUTPUT -d %s -j DROP" % target_ip,
                    timeout=30,
                )

            elif fault_type == "node_cpu_stress":
                logging.info(
                    "[%s] Injecting CPU stress for %ds" % (source_node, duration)
                )
                ssh_executor.execute(
                    source_node,
                    "stress-ng --cpu 0 --cpu-load 95 --timeout %ds" % duration,
                    timeout=duration + 60,
                )

            else:
                logging.warning("Unknown fault_type: %s" % fault_type)

        except Exception as e:
            logging.error(
                "[%s] Fault injection failed: %s" % (source_node, e)
            )

    def _wait_for_migration(
        self,
        kubecli: KrknKubernetes,
        vm_name: str,
        vm_namespace: str,
        timeout: int,
    ) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            vmi = kubecli.get_vmi(vm_name, vm_namespace)
            if not vmi:
                logging.warning("VMI %s disappeared" % vm_name)
                return False

            phase = vmi.get("status", {}).get("phase", "")
            migration_state = vmi.get("status", {}).get("migrationState", {})

            if migration_state:
                completed = migration_state.get("completed", False)
                failed = migration_state.get("failed", False)

                if completed:
                    logging.info("Migration completed for VMI %s" % vm_name)
                    return True
                if failed:
                    logging.error("Migration failed for VMI %s" % vm_name)
                    return False

            if phase == "Running":
                pass
            elif phase in ("Failed", "Succeeded"):
                logging.error(
                    "VMI %s entered %s state during migration" % (vm_name, phase)
                )
                return False

            time.sleep(10)

        logging.error("Migration timed out for VMI %s" % vm_name)
        return False

    def _check_dual_pods(
        self, kubecli: KrknKubernetes, vm_name: str, vm_namespace: str
    ) -> bool:
        pods = kubecli.list_pods(
            vm_namespace,
            label_selector="kubevirt.io/domain=%s" % vm_name,
        )
        if len(pods) > 1:
            logging.error(
                "Dual virt-launcher pods detected: %s" % pods
            )
            return True
        return False

    def _cleanup_vmim(
        self, kubecli: KrknKubernetes, vm_name: str, vm_namespace: str
    ) -> None:
        try:
            kubecli.custom_object_client.delete_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=vm_namespace,
                plural="virtualmachineinstancemigrations",
                name="krkn-migration-%s" % vm_name,
            )
        except Exception:
            pass

    def supports_standalone(self) -> bool:
        return False

    def get_scenario_types(self) -> list[str]:
        return ["vm_migration_chaos_scenarios"]
