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
import copy
import logging
import os
import queue
import random
import re
import shlex
import threading
import time


import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.krkn import  HogConfig, HogType
from krkn_lib.models.k8s import NodeResources
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.utils import get_random_string

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.node_actions.ssh_node_scenarios import SSHExecutor
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator


class HogsScenarioPlugin(AbstractScenarioPlugin):
    
    @set_rollback_context_decorator
    def run(self, run_uuid: str, scenario: str, lib_telemetry: KrknTelemetryOpenshift,
            scenario_telemetry: ScenarioTelemetry) -> int:
        try:
            with open(scenario, "r") as f:
                scenario = yaml.safe_load(f)

            targets = scenario.get("targets", [])
            if targets:
                return self._run_standalone(scenario, targets)

            if lib_telemetry.get_lib_kubernetes() is None:
                logging.error(
                    "hog_scenarios requires 'targets' field in standalone mode"
                )
                return 1

            scenario_config = HogConfig.from_yaml_dict(scenario)

            # Get node-name if provided
            node_name = scenario.get('node-name')

            has_selector = True
            if not scenario_config.node_selector or not re.match("^.+=.*$", scenario_config.node_selector):
                if scenario_config.node_selector:
                    logging.warning(f"node selector {scenario_config.node_selector} not in right format (key=value)")
                node_selector = ""
            else:
                node_selector = scenario_config.node_selector

            if node_name:
                logging.info(f"Using specific node: {node_name}")
                all_nodes = lib_telemetry.get_lib_kubernetes().list_nodes("")
                if node_name not in all_nodes:
                    raise Exception(f"Specified node {node_name} not found or not available")
                available_nodes = [node_name]
            else:
                available_nodes = lib_telemetry.get_lib_kubernetes().list_nodes(node_selector)
                if len(available_nodes) == 0:
                    raise Exception("no available nodes to schedule workload")

                if not has_selector:
                    available_nodes = [available_nodes[random.randint(0, len(available_nodes) - 1)]]

            if scenario_config.number_of_nodes and len(available_nodes) > scenario_config.number_of_nodes:
                available_nodes = random.sample(available_nodes, scenario_config.number_of_nodes)

            exception_queue = queue.Queue()
            self.run_scenario(scenario_config, lib_telemetry.get_lib_kubernetes(), available_nodes, exception_queue)
            return 0
        except Exception as e:
            logging.error(f"scenario exception: {e}")
            return 1

    def _run_standalone(self, scenario: dict, targets: list[str]) -> int:
        """Run hog scenario on standalone targets via SSH + stress-ng."""
        if not targets:
            raise ValueError("targets list cannot be empty for standalone hog scenario")
        scenario_config = HogConfig.from_yaml_dict(scenario)
        ssh_executor = SSHExecutor(
            ssh_user=scenario.get("ssh_user", "root"),
            ssh_private_key=os.path.expanduser(
                scenario.get("ssh_private_key", "~/.ssh/id_rsa")
            ),
            ssh_port=scenario.get("ssh_port", 22),
            connect_timeout=scenario.get("ssh_connect_timeout", 30),
        )

        exit_code, stdout, _ = ssh_executor.execute(
            targets[0], "which stress-ng", timeout=10
        )
        if exit_code != 0:
            raise Exception(
                "stress-ng not found on %s. Install: "
                "apt-get install stress-ng / yum install stress-ng" % targets[0]
            )
        logging.info("stress-ng found on %s: %s" % (targets[0], stdout.strip()))

        if scenario_config.number_of_nodes and len(targets) > scenario_config.number_of_nodes:
            targets = random.sample(targets, scenario_config.number_of_nodes)

        exception_queue = queue.Queue()
        workers = []
        logging.info(f"running {scenario_config.type.value} hog scenario (standalone SSH)")
        logging.info(f"targeting hosts: [{','.join(targets)}]")
        for target in targets:
            config_copy = copy.deepcopy(scenario_config)
            worker = threading.Thread(
                target=self._run_standalone_worker,
                args=(config_copy, ssh_executor, target, exception_queue),
            )
            worker.daemon = True
            worker.start()
            workers.append(worker)

        for worker in workers:
            worker.join()

        errors = []
        while not exception_queue.empty():
            errors.append(exception_queue.get_nowait())
        if errors:
            for err in errors:
                logging.error("standalone hog failure: %s" % err)
            raise errors[0]

        return 0

    def _run_standalone_worker(
        self, config: HogConfig, ssh: SSHExecutor, host: str,
        exception_queue: queue.Queue,
    ) -> None:
        """Execute stress-ng on a remote host via SSH."""
        try:
            if not config.workers:
                exit_code, stdout, _ = ssh.execute(host, "nproc", timeout=10)
                try:
                    config.workers = int(stdout.strip()) if exit_code == 0 and stdout.strip() else 1
                except ValueError:
                    config.workers = 1
                logging.info(f"[{host}] detected {config.workers} cpus")

            cmd = self._build_stress_command(config)
            logging.info(f"[{host}] executing: {cmd}")
            exit_code, stdout, stderr = ssh.execute(
                host, cmd, timeout=config.duration + 120
            )
            if exit_code != 0:
                raise Exception(f"[{host}] stress-ng failed (exit {exit_code}): {stderr}")
            logging.info(f"[{host}] stress-ng completed successfully")
        except Exception as e:
            exception_queue.put(e)

    @staticmethod
    def _build_stress_command(config: HogConfig) -> str:
        """Build stress-ng command from HogConfig."""
        if config.type == HogType.cpu:
            return (
                "stress-ng --cpu %d --cpu-load %d --timeout %ds --metrics-brief"
                % (config.workers, config.cpu_load_percentage, config.duration)
            )
        elif config.type == HogType.memory:
            return (
                "stress-ng --vm %d --vm-bytes %s --vm-keep --timeout %ds --metrics-brief"
                % (config.workers, shlex.quote(str(config.memory_vm_bytes)), config.duration)
            )
        elif config.type == HogType.io:
            return (
                "stress-ng --iomix %d --iomix-bytes %s --timeout %ds --metrics-brief"
                % (config.workers, shlex.quote(str(config.io_write_bytes)), config.duration)
            )

    def supports_standalone(self) -> bool:
        return True

    def get_scenario_types(self) -> list[str]:
        return ["hog_scenarios"]

    def run_scenario_worker(self, config: HogConfig,
                            lib_k8s: KrknKubernetes, node: str,
                            exception_queue: queue.Queue):
        try:
            if not config.workers:
                config.workers = lib_k8s.get_node_cpu_count(node)
                logging.info(f"[{node}] detected {config.workers} cpus for node {node}")

            logging.info(f"[{node}] workers number: {config.workers}")

            # using kubernetes.io/hostname = <node_name> selector to
            # precisely deploy each workload on each selected node
            config.node_selector = f"kubernetes.io/hostname={node}"
            pod_name = f"{config.type.value}-hog-{get_random_string(5)}"
            node_resources_start = lib_k8s.get_node_resources_info(node)
            self.rollback_handler.set_rollback_callable(
                self.rollback_hog_pod,
                RollbackContent(
                    namespace=config.namespace,
                    resource_identifier=pod_name,
                ),
            )
            lib_k8s.deploy_hog(pod_name, config)
            start = time.time()
            # waiting 3 seconds before starting sample collection
            time.sleep(3)
            node_resources_end = lib_k8s.get_node_resources_info(node)

            samples: list[NodeResources] = []
            avg_node_resources = NodeResources()

            while time.time() - start < config.duration-1:
                samples.append(lib_k8s.get_node_resources_info(node))

            max_wait = 30
            wait = 0
            logging.info(f"[{node}] waiting {max_wait} up to seconds pod: {pod_name} namespace: {config.namespace} to finish")
            while lib_k8s.is_pod_running(pod_name, config.namespace):
                if wait >= max_wait:
                    raise Exception(f"[{node}] hog workload pod: {pod_name} namespace: {config.namespace} "
                                    f"didn't finish after {max_wait}")
                time.sleep(1)
                wait += 1
                continue

            logging.info(f"[{node}] deleting pod: {pod_name} namespace: {config.namespace}")
            lib_k8s.delete_pod(pod_name, config.namespace)

            for resource in samples:
                avg_node_resources.cpu += resource.cpu
                avg_node_resources.memory += resource.memory
                avg_node_resources.disk_space += resource.disk_space

            avg_node_resources.cpu = avg_node_resources.cpu/len(samples)
            avg_node_resources.memory = avg_node_resources.memory / len(samples)
            avg_node_resources.disk_space = avg_node_resources.disk_space / len(samples)

            if config.type == HogType.cpu:
                logging.info(f"[{node}] detected cpu consumption: "
                             f"{(avg_node_resources.cpu / (config.workers * 1000000000)) * 100} %")
            if config.type == HogType.memory:
                logging.info(f"[{node}] detected memory increase: "
                             f"{avg_node_resources.memory / node_resources_start.memory * 100} %")
            if config.type == HogType.io:
                logging.info(f"[{node}] detected disk space allocated: "
                             f"{(node_resources_start.disk_space - avg_node_resources.disk_space) / 1024 / 1024} MB")
        except Exception as e:
            exception_queue.put(e)

    def run_scenario(self, config: HogConfig,
                     lib_k8s: KrknKubernetes,
                     available_nodes: list[str],
                     exception_queue: queue.Queue):
        workers = []
        logging.info(f"running {config.type.value} hog scenario")
        logging.info(f"targeting nodes: [{','.join(available_nodes)}]")
        for node in available_nodes:
            config_copy = copy.deepcopy(config)
            worker = threading.Thread(target=self.run_scenario_worker,
                                      args=(config_copy, lib_k8s, node, exception_queue))
            worker.daemon = True
            worker.start()
            workers.append(worker)

        for worker in workers:
            worker.join()

        try:
            while True:
                exception = exception_queue.get_nowait()
                raise exception
        except queue.Empty:
            pass

    @staticmethod
    def rollback_hog_pod(rollback_content: RollbackContent, lib_telemetry: KrknTelemetryOpenshift):
        """
        Rollback function to delete hog pod.

        :param rollback_content: Rollback content containing namespace and resource_identifier.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations
        """
        try:
            namespace = rollback_content.namespace
            pod_name = rollback_content.resource_identifier
            logging.info(
                f"Rolling back hog pod: {pod_name} in namespace: {namespace}"
            )
            lib_telemetry.get_lib_kubernetes().delete_pod(pod_name, namespace)
            logging.info("Rollback of hog pod completed successfully.")
        except Exception as e:
            logging.error(f"Failed to rollback hog pod: {e}")
