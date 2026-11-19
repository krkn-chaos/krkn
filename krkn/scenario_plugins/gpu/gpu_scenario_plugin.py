# Copyright 2026 The Krkn Authors
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

import concurrent.futures
import json
from functools import partial
import logging
import math
import os
import random
import threading
import time
import uuid

import yaml
from kubernetes.client import NodeV1Api
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream as k8s_stream
from krkn_lib.gpu import (
    GpuInjectorResult,
    GpuObservation,
    GpuScenarioTelemetry,
    GpuWorkerTelemetry,
    list_gpu_nodes,
    list_gpu_pod_candidates,
)
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.gpu.runtime.parameters import (
    compute_duty_cycle_values, csv_values, memory_bytes, validate_fault,
)

_INJECTOR_METRICS = (
    "requested_bytes",
    "actual_bytes",
    "freed_bytes",
    "small_allocation_bytes",
    "free_delta_within_tolerance",
    "post_release_cuda_free_bytes",
    "post_release_cuda_total_bytes",
    "compute_duty_cycle",
    "batches_completed",
    "loop_iterations_completed",
    "batches_per_second",
    "launch_wait_seconds",
)


class GpuScenarioPlugin(AbstractScenarioPlugin):
    """Run a coordinated GPU pressure fault on each selected node."""

    def __init__(self, scenario_type: str = "gpu_scenarios"):
        super().__init__(scenario_type=scenario_type)

    def get_scenario_types(self) -> list[str]:
        """Return the GPU scenario configuration key."""
        return ["gpu_scenarios"]

    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        """Deploy, coordinate, and clean up GPU pressure workers."""
        gpu_run = None
        workers = {}
        observations = {}
        pods: list[tuple[str, str]] = []
        lib_k8s = None
        result = 1
        try:
            with open(scenario, encoding="utf-8") as scenario_file:
                config = self._load_config(yaml.safe_load(scenario_file))
            lib_k8s = lib_telemetry.get_lib_kubernetes()
            namespace = str(config.get("namespace") or "default")
            image = config.get("image")
            if not image:
                raise ValueError("GPU worker image must be configured with image or GPU_IMAGE")
            fault = validate_fault(str(config.get("fault-type") or ""))
            gpu_run = scenario_telemetry.gpu = GpuScenarioTelemetry(fault_type=fault)
            duration = self._positive_seconds(config.get("duration"), "duration")
            setup_timeout = self._positive_seconds(config.get("setup-timeout", 120), "setup-timeout")
            recovery_timeout = self._positive_seconds(config.get("recovery-timeout", 30), "recovery-timeout")
            node_count = config.get("number-of-nodes")
            if node_count is not None:
                node_count = self._positive_int(node_count, "number-of-nodes")

            node_selector = config.get("node-selector")
            pod_selector = config.get("pod-label-selector")
            if bool(node_selector) == bool(pod_selector):
                raise ValueError("specify exactly one of node-selector or pod-label-selector")
            if node_selector:
                nodes = self._select_nodes(lib_k8s, node_selector, config)
                targets = {node: [] for node in nodes}
            else:
                target_namespace = str(config.get("target-namespace") or "").strip()
                if not target_namespace:
                    raise ValueError("target-namespace is required with pod-label-selector")
                targets = self._select_pods(lib_k8s, target_namespace, pod_selector, config)
                nodes = list(targets)
                if not nodes:
                    raise ValueError("no matching GPU pods found")
                if node_count is not None:
                    if len(nodes) < node_count:
                        raise ValueError(f"requested {node_count} GPU nodes but only {len(nodes)} are available")
                    if len(nodes) > node_count:
                        nodes = random.sample(nodes, node_count)
                        targets = {node: targets[node] for node in nodes}

            ids = csv_values(str(config.get("gpu-ids", "all")))
            gpu_ids = ",".join(ids)
            if fault == "vram-pressure":
                values = csv_values(str(config.get("gpu-vram") or ""))
                for value in values:
                    memory_bytes(value, 1 << 63)
                if ids != ["all"] and len(values) not in (1, len(ids)):
                    raise ValueError("gpu-vram must be a scalar or contain one value per GPU ID")
                reserve = str(config.get("memory-reserve", "64Mi"))
                if reserve.endswith("%"):
                    raise ValueError("memory-reserve must use a binary memory unit")
                memory_bytes(reserve, 1 << 63)
                fault_env = {"GPU_VRAM": ",".join(values), "GPU_MEMORY_RESERVE": reserve}
            else:
                duty_cycles = compute_duty_cycle_values(config.get("gpu-compute-duty-cycle"))
                if gpu_ids.lower() != "all" and len(duty_cycles) not in (1, len(ids)):
                    raise ValueError("gpu-compute-duty-cycle must be a scalar or contain one value per GPU ID")
                fault_env = {"GPU_COMPUTE_DUTY_CYCLE": ",".join(map(str, duty_cycles))}
            worker_config = dict(config)
            worker_config["runtime-class-name"] = self._resolve_runtime_class(lib_k8s, config)

            manifests = []
            for node in nodes:
                pod_name = "krkn-gpu-" + uuid.uuid4().hex[:10]
                manifests.append(self._worker_pod(
                    pod_name, node, namespace, image, fault, gpu_ids,
                    duration, setup_timeout, recovery_timeout, worker_config, targets[node], fault_env,
                ))
                if not self._register_rollback(pod_name, namespace):
                    raise RuntimeError(f"failed to register rollback for {pod_name}")
                pods.append((pod_name, namespace))
                workers[node] = GpuWorkerTelemetry(node_name=node)
            self._deploy_workers(lib_k8s, pods, manifests, setup_timeout)
            self._coordinate(
                lib_k8s, pods, nodes, targets, setup_timeout, duration, recovery_timeout,
                workers, observations,
            )
            result = 0
        except Exception as exc:
            logging.error("GPU scenario failed: %s", exc)
        finally:
            if gpu_run is not None:
                gpu_run.workers = list(workers.values())
                gpu_run.observations.extend(
                    observations[node, phase]
                    for node in workers
                    for phase in ("baseline", "holding", "after_release")
                    if (node, phase) in observations
                )
            if lib_k8s is not None:
                for worker, (name, pod_namespace) in zip(workers.values(), pods, strict=True):
                    worker.pod_deleted = self._delete_bounded(lib_k8s.cli, name, pod_namespace)
                    if not worker.pod_deleted:
                        result = 1
        return result

    @staticmethod
    def _load_config(raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("GPU scenario configuration must be a mapping")
        keys = {
            "node-selector": "NODE_SELECTOR", "number-of-nodes": "NUMBER_OF_NODES",
            "pod-label-selector": "POD_LABEL_SELECTOR", "target-namespace": "TARGET_NAMESPACE",
            "namespace": "NAMESPACE", "gpu-ids": "GPU_IDS", "gpu-vram": "GPU_VRAM",
            "gpu-compute-duty-cycle": "GPU_COMPUTE_DUTY_CYCLE",
            "duration": "GPU_DURATION", "fault-type": "GPU_FAULT_TYPE", "image": "GPU_IMAGE",
            "setup-timeout": "GPU_SETUP_TIMEOUT", "recovery-timeout": "GPU_RECOVERY_TIMEOUT",
            "memory-reserve": "GPU_MEMORY_RESERVE", "runtime-class-name": "GPU_RUNTIME_CLASS_NAME",
            "driver-root": "GPU_DRIVER_ROOT", "service-account": "GPU_SERVICE_ACCOUNT",
            "image-pull-secrets": "GPU_IMAGE_PULL_SECRETS", "tolerations": "GPU_TOLERATIONS",
            "gpu-resource-name": "GPU_RESOURCE_NAME",
        }
        result = dict(raw)
        for key, env_name in keys.items():
            if env_name in os.environ:
                result[key] = os.environ[env_name]
        return result

    @staticmethod
    def _resolve_runtime_class(lib_k8s, config):
        if config.get("runtime-class-name"):
            return str(config["runtime-class-name"])
        try:
            NodeV1Api(api_client=lib_k8s.cli.api_client).read_runtime_class(
                "nvidia", _request_timeout=10
            )
        except ApiException as exc:
            if exc.status == 404:
                logging.info("No NVIDIA RuntimeClass found; using the default runtime")
                return None
            raise RuntimeError(
                "Cannot discover NVIDIA RuntimeClass: "
                "allow get on node.k8s.io/runtimeclasses or set runtime-class-name explicitly; "
                f"{exc}"
            ) from exc
        logging.info("Using detected NVIDIA RuntimeClass: nvidia")
        return "nvidia"

    @staticmethod
    def _positive_int(value, name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a positive integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a positive integer") from exc
        if parsed <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return parsed

    @staticmethod
    def _positive_seconds(value, name: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be positive seconds")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be positive seconds") from exc
        if not math.isfinite(parsed) or parsed <= 0:
            raise ValueError(f"{name} must be positive seconds")
        return parsed

    def _select_nodes(self, lib_k8s, selector: str, config: dict) -> list[str]:
        resource = str(config.get("gpu-resource-name") or "nvidia.com/gpu")
        available = list_gpu_nodes(lib_k8s.cli, selector, resource_name=resource)
        if not available:
            raise ValueError("no available GPU nodes match node-selector")
        count_value = config.get("number-of-nodes")
        if count_value is None:
            return available
        count = self._positive_int(count_value, "number-of-nodes")
        if len(available) < count:
            raise ValueError(f"requested {count} GPU nodes but only {len(available)} are available")
        if len(available) > count:
            available = random.sample(available, count)
        return available

    def _select_pods(self, lib_k8s, namespace: str, selector: str, config: dict) -> dict:
        resource = str(config.get("gpu-resource-name") or "nvidia.com/gpu")
        pods = list_gpu_pod_candidates(lib_k8s.cli, namespace, selector, resource_name=resource)
        grouped: dict[str, list[dict]] = {}
        seen = set()
        for pod in pods:
            identity = (pod.namespace, pod.name)
            if identity in seen:
                continue
            seen.add(identity)
            if pod.phase != "Running" or not pod.node_name:
                raise ValueError(f"matching pod {pod.namespace}/{pod.name} is not Running on a node")
            if not pod.requests_gpu:
                raise ValueError(f"matching pod {pod.namespace}/{pod.name} has no NVIDIA GPU resource")
            grouped.setdefault(pod.node_name, []).append({
                "namespace": pod.namespace, "name": pod.name, "uid": pod.uid,
            })
        return grouped

    def _worker_pod(
        self, name, node, namespace, image, fault, gpu_ids, duration,
        setup_timeout, recovery_timeout, config, targets, fault_env,
    ) -> dict:
        env = [
            {"name": "GPU_FAULT_TYPE", "value": fault},
            {"name": "GPU_IDS", "value": gpu_ids},
            {"name": "GPU_DURATION", "value": str(duration)},
            {"name": "GPU_SETUP_TIMEOUT", "value": str(setup_timeout)},
            {"name": "GPU_RECOVERY_TIMEOUT", "value": str(recovery_timeout)},
            {"name": "GPU_TARGET_PODS", "value": json.dumps(targets)},
            {"name": "GPU_RESOURCE_NAME", "value": str(config.get("gpu-resource-name") or "nvidia.com/gpu")},
            {"name": "NVIDIA_VISIBLE_DEVICES", "value": "all"},
            {"name": "NVIDIA_DRIVER_CAPABILITIES", "value": "compute,utility"},
        ]
        env.extend({"name": key, "value": value} for key, value in fault_env.items())
        volumes = [{"name": "dev", "hostPath": {"path": "/dev", "type": "Directory"}}]
        mounts = [{"name": "dev", "mountPath": "/dev"}]
        if targets:
            volumes.append({"name": "pod-resources", "hostPath": {
                "path": "/var/lib/kubelet/pod-resources", "type": "Directory",
            }})
            mounts.append({"name": "pod-resources", "mountPath": "/var/lib/kubelet/pod-resources", "readOnly": True})
        driver_root = config.get("driver-root")
        if driver_root:
            volumes.append({"name": "host-driver", "hostPath": {"path": str(driver_root), "type": "Directory"}})
            mounts.append({"name": "host-driver", "mountPath": "/host-driver", "readOnly": True})
            env.extend([
                {"name": "PATH", "value": "/opt/venv/bin:/usr/local/bin:/usr/local/nvidia/bin:/usr/local/cuda/bin:/usr/bin:/bin:/host-driver/usr/bin"},
                {"name": "LD_LIBRARY_PATH", "value": "/host-driver/usr/lib64:/host-driver/usr/lib/x86_64-linux-gnu:/host-driver/usr/lib/aarch64-linux-gnu:/host-driver/lib64:/host-driver/lib/x86_64-linux-gnu:/host-driver/lib/aarch64-linux-gnu:/usr/local/nvidia/lib:/usr/local/nvidia/lib64"},
            ])
        spec = {
            "restartPolicy": "Never",
            "terminationGracePeriodSeconds": 10,
            "activeDeadlineSeconds": math.ceil(setup_timeout + duration + recovery_timeout + 60),
            "automountServiceAccountToken": False,
            "nodeName": node,
            "containers": [{
                "name": "gpu-worker", "image": image, "imagePullPolicy": "IfNotPresent",
                "env": env, "securityContext": {"privileged": True},
                "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}},
                "volumeMounts": mounts,
            }],
            "volumes": volumes,
        }
        if config.get("runtime-class-name"):
            spec["runtimeClassName"] = str(config["runtime-class-name"])
        if config.get("service-account"):
            spec["serviceAccountName"] = str(config["service-account"])
        if config.get("image-pull-secrets"):
            secrets = config["image-pull-secrets"]
            secrets = csv_values(secrets) if isinstance(secrets, str) else secrets
            if not isinstance(secrets, list) or any(not isinstance(item, str) or not item for item in secrets):
                raise ValueError("image-pull-secrets must be a list of names or comma-separated names")
            spec["imagePullSecrets"] = [{"name": item} for item in secrets]
        if config.get("tolerations"):
            tolerations = config["tolerations"]
            if isinstance(tolerations, str):
                tolerations = yaml.safe_load(tolerations)
            if not isinstance(tolerations, list):
                raise ValueError("tolerations must be a YAML list")
            spec["tolerations"] = tolerations
        return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name}, "spec": spec}

    def _register_rollback(self, name: str, namespace: str) -> bool:
        return self.rollback_handler.set_rollback_callable(
            self.rollback_gpu_pod,
            RollbackContent(namespace=namespace, resource_identifier=name),
        )

    @staticmethod
    def rollback_gpu_pod(rollback_content: RollbackContent, lib_telemetry: KrknTelemetryOpenshift):
        """Gracefully delete a worker with bounded, verified rollback."""
        import time
        from kubernetes.client.exceptions import ApiException

        cli = lib_telemetry.get_lib_kubernetes().cli
        name = rollback_content.resource_identifier
        namespace = rollback_content.namespace
        try:
            cli.delete_namespaced_pod(
                name, namespace, grace_period_seconds=10, _request_timeout=10,
            )
        except ApiException as exc:
            if exc.status == 404:
                return
            raise
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                cli.read_namespaced_pod(name, namespace, _request_timeout=10)
            except ApiException as exc:
                if exc.status == 404:
                    return
                raise
            time.sleep(0.25)
        raise TimeoutError(f"timed out rolling back GPU worker {namespace}/{name}")

    def _deploy_workers(self, lib_k8s, pods, manifests, setup_timeout):
        errors = []
        cancelled = threading.Event()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(pods))) as pool:
            futures = [
                pool.submit(self._start_worker, lib_k8s, body, namespace, setup_timeout, cancelled)
                for (_, namespace), body in zip(pods, manifests)
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    cancelled.set()
                    errors.append(exc)
        if errors:
            raise RuntimeError("GPU worker deployment failed: " + "; ".join(map(str, errors)))

    @staticmethod
    def _start_worker(lib_k8s, body, namespace, setup_timeout, cancelled):
        cli = lib_k8s.cli
        name = body["metadata"]["name"]
        deadline = time.monotonic() + setup_timeout
        # Keep krkn-lib's signature verification, without its Running-only wait.
        lib_k8s.create_obj(
            body, namespace, partial(cli.create_namespaced_pod, _request_timeout=10)
        )
        pod = None
        try:
            while True:
                if cancelled.is_set():
                    raise RuntimeError("startup cancelled after another worker failed")
                pod = cli.read_namespaced_pod(name, namespace, _request_timeout=10)
                phase = pod.status.phase
                terminated = any(
                    getattr(getattr(status, "state", None), "terminated", None) is not None
                    for status in pod.status.container_statuses or []
                )
                if phase in ("Failed", "Succeeded") or terminated:
                    raise RuntimeError(f"worker exited during startup ({phase})")
                if phase == "Running":
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError("startup timed out")
                time.sleep(1)
        except Exception as exc:
            try:
                logs = GpuScenarioPlugin._read_worker_logs(
                    cli, name, namespace, tail_lines=100
                )
            except Exception as log_error:
                logs = f"unavailable: {log_error}"
            status = pod.status if pod is not None else "unavailable"
            raise RuntimeError(
                f"GPU worker {namespace}/{name}: {exc}\n"
                f"Pod status: {status}\nWorker logs:\n{logs or '(empty)'}"
            ) from exc

    def _coordinate(
        self, lib_k8s, pods, nodes, targets, setup_timeout, duration, recovery_timeout,
        workers, observations,
    ):
        cli = lib_k8s.cli
        pod_map = dict(zip(nodes, pods))
        ready = set()
        deadline = time.monotonic() + setup_timeout
        while len(ready) < len(pods):
            for node, (name, namespace) in pod_map.items():
                if node in ready:
                    continue
                event = self._last_event(cli, name, namespace)
                if event:
                    self._record_event(workers[node], observations, event)
                if event and event.get("phase") == "ready":
                    ready.add(node)
                    logging.info("GPU worker ready on %s: %s", node, json.dumps(event.get("gpus", [])))
                elif event and event.get("phase") == "error":
                    logging.error("GPU worker setup error on %s: %s", node, json.dumps(event))
                    raise RuntimeError(f"GPU worker on {node} setup failed: {event.get('message')}")
                self._check_pod(cli, name, namespace, require_running=True)
            if time.monotonic() >= deadline:
                raise TimeoutError("GPU workers did not all reach the ready barrier")
            time.sleep(1)


        for node, (name, namespace) in pod_map.items():
            for target in targets[node]:
                current = cli.read_namespaced_pod(
                    target["name"], target["namespace"], _request_timeout=10
                )
                if (
                    current.metadata.uid != target["uid"]
                    or getattr(current.spec, "node_name", None) != node
                    or getattr(current.status, "phase", None) != "Running"
                ):
                    raise RuntimeError(
                        f"target pod {target['namespace']}/{target['name']} changed or is no longer Running"
                    )
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(pods)) as pool:
            releases = [
                pool.submit(
                    k8s_stream,
                    cli.connect_post_namespaced_pod_exec,
                    name,
                    namespace,
                    command=["touch", "/tmp/krkn-gpu-start"],
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _request_timeout=10,
                )
                for name, namespace in pods
            ]
            for release in concurrent.futures.as_completed(releases):
                release.result()

        deadline = time.monotonic() + duration + recovery_timeout
        completed = set()
        observed = {}
        while len(completed) < len(pods):
            for node, (name, namespace) in pod_map.items():
                if node in completed:
                    continue
                event = self._last_event(cli, name, namespace)
                if event and event != observed.get(node):
                    observed[node] = event
                    self._record_event(workers[node], observations, event)
                    phase = event.get("phase")
                    fault = "compute" if event.get("fault_type") == "compute-pressure" else "VRAM"
                    if phase == "holding":
                        logging.info("GPU %s pressure on %s: %s", fault, node, json.dumps(event.get("gpus", [])))
                    elif phase == "error":
                        logging.error("GPU worker error on %s: %s", node, json.dumps(event))
                        raise RuntimeError(f"GPU worker on {node} failed: {event.get('message')}")
                    elif phase == "complete":
                        logging.info("GPU %s pressure recovery on %s: %s", fault, node, json.dumps(event.get("gpus", [])))
                        completed.add(node)
                self._check_pod(cli, name, namespace, require_running=node not in completed)
            if time.monotonic() >= deadline:
                raise TimeoutError("GPU workers did not complete within the hold/recovery deadline")
            time.sleep(1)
        success_deadline = time.monotonic() + recovery_timeout
        for name, namespace in pods:
            self._wait_success(cli, name, namespace, success_deadline=success_deadline)

    @staticmethod
    def _record_event(worker, observations, event):
        phase = event["phase"]
        if phase not in ("ready", "holding", "complete", "error"):
            return
        worker.phase = phase
        snapshots = event.get("observations")
        if isinstance(snapshots, dict):
            for label in ("baseline", "holding", "after_release"):
                snapshot = snapshots.get(label)
                if isinstance(snapshot, dict):
                    try:
                        observations[worker.node_name, label] = GpuObservation.from_dict({
                            "node_name": worker.node_name,
                            "phase": label,
                            "snapshot": snapshot,
                        })
                    except (AttributeError, KeyError, TypeError, ValueError):
                        logging.warning("Ignoring invalid GPU %s snapshot on %s", label, worker.node_name)
        devices = {device.device_uuid: device for device in worker.devices}
        records = event.get("gpus", [])
        if phase == "error":
            cleanup = event.get("cleanup", {})
            if not isinstance(cleanup, dict):
                return
            records = [
                {**stats, "uuid": device_uuid}
                for device_uuid, stats in cleanup.items()
                if isinstance(stats, dict)
            ]
        if not isinstance(records, list):
            return
        for record in records:
            device_uuid = record.get("uuid") if isinstance(record, dict) else None
            if not isinstance(device_uuid, str) or not device_uuid:
                continue
            device = devices.get(device_uuid)
            if device is None:
                device = GpuInjectorResult(device_uuid=device_uuid)
                devices[device_uuid] = device
                worker.devices.append(device)
            for key in _INJECTOR_METRICS:
                value = record.get(key)
                if type(value) in (int, bool) or (type(value) is float and math.isfinite(value)):
                    device.metrics[key] = value

    @staticmethod
    def _read_worker_logs(cli, name, namespace, tail_lines):
        # Avoid the SDK decoding JSON log text into Python objects.
        with cli.read_namespaced_pod_log(
            name, namespace, tail_lines=tail_lines, _request_timeout=10,
            _preload_content=False,
        ) as response:
            return response.read().decode("utf-8", errors="replace")

    @staticmethod
    def _last_event(cli, name, namespace):
        try:
            output = GpuScenarioPlugin._read_worker_logs(cli, name, namespace, tail_lines=1)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise
        if not output:
            return None
        try:
            event = json.loads(output.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise RuntimeError(f"GPU worker emitted invalid JSON: {output!r}") from exc
        if not isinstance(event, dict) or "phase" not in event:
            raise RuntimeError(f"GPU worker emitted malformed event: {output!r}")
        return event

    @staticmethod
    def _check_pod(cli, name, namespace, require_running=False):
        pod = cli.read_namespaced_pod(name, namespace, _request_timeout=10)
        phase = getattr(pod.status, "phase", None)
        if phase == "Failed":
            raise RuntimeError(f"GPU worker pod {namespace}/{name} failed")
        for status in getattr(pod.status, "container_statuses", None) or []:
            terminated = getattr(getattr(status, "state", None), "terminated", None)
            if terminated and terminated.exit_code != 0:
                raise RuntimeError(f"GPU worker pod {namespace}/{name} exited {terminated.exit_code}")
        if require_running and phase not in ("Running", "Pending"):
            raise RuntimeError(f"GPU worker pod {namespace}/{name} exited before completion ({phase})")

    def _wait_success(self, cli, name, namespace, timeout=None, success_deadline=None):
        deadline = success_deadline or time.monotonic() + timeout
        while time.monotonic() < deadline:
            pod = cli.read_namespaced_pod(name, namespace, _request_timeout=10)
            if pod.status.phase == "Succeeded":
                statuses = getattr(pod.status, "container_statuses", None) or []
                if not statuses or any(
                    getattr(getattr(status.state, "terminated", None), "exit_code", None) != 0
                    for status in statuses
                ):
                    raise RuntimeError(f"GPU worker pod {namespace}/{name} did not exit successfully")
                return
            if pod.status.phase == "Failed":
                raise RuntimeError(f"GPU worker pod {namespace}/{name} failed")
            time.sleep(1)
        raise TimeoutError(f"GPU worker pod {namespace}/{name} did not terminate successfully")

    @staticmethod
    def _delete_bounded(cli, name, namespace):
        try:
            cli.delete_namespaced_pod(name, namespace, grace_period_seconds=10, _request_timeout=10)
        except ApiException as exc:
            if exc.status == 404:
                return True
            logging.warning("Unable to delete GPU worker pod %s/%s: %s", namespace, name, exc)
            return False
        except Exception as exc:
            logging.warning("Unable to delete GPU worker pod %s/%s: %s", namespace, name, exc)
            return False
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                cli.read_namespaced_pod(name, namespace, _request_timeout=10)
            except ApiException as exc:
                if exc.status == 404:
                    return True
                logging.warning("Unable to verify GPU worker pod deletion: %s", exc)
                return False
            except Exception as exc:
                logging.warning("Unable to verify GPU worker pod deletion: %s", exc)
                return False
            time.sleep(0.25)
        logging.warning("Timed out deleting GPU worker pod %s/%s", namespace, name)
        return False
