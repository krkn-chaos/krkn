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

"""GPU discovery and mapping from requested pods and identifiers."""

import csv
import json
import os
import subprocess
import xml.etree.ElementTree as ET

from .common import Device, MIB, POD_RESOURCES_SOCKET, WorkerError
from .parameters import csv_values, is_gpu_resource


def normalize_uuid(value):
    """Normalize CUDA/NVML GPU UUID spellings without accepting MIG IDs."""
    text = str(value).strip()
    if text.upper().startswith("MIG-"):
        raise WorkerError(f"MIG device allocation is unsupported: {text}")
    if text.upper().startswith("GPU-"):
        text = text[4:]
    compact = text.replace("-", "").lower()
    if len(compact) != 32 or any(ch not in "0123456789abcdef" for ch in compact):
        raise WorkerError(f"unrecognized GPU device identifier: {value!r}")
    return "GPU-" + "-".join((compact[:8], compact[8:12], compact[12:16], compact[16:20], compact[20:]))


class NvidiaSmi:
    """nvidia-smi discovery and observation using driver-provided utilities."""

    def __init__(self, executable=None, run=subprocess.run):
        self.executable = executable or self._find_executable()
        self.run = run

    @staticmethod
    def _find_executable():
        path = os.environ.get("PATH", "")
        for directory in path.split(os.pathsep):
            candidate = os.path.join(directory, "nvidia-smi")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        for candidate in ("/host-driver/usr/bin/nvidia-smi", "/usr/bin/nvidia-smi"):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        raise WorkerError("nvidia-smi is not available in PATH or /host-driver/usr/bin")

    def _command(self, *args, required=True):
        try:
            result = self.run(
                [self.executable, *args], check=False, capture_output=True, text=True, timeout=10.0,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkerError(f"nvidia-smi timed out: {' '.join(args)}") from exc
        if result.returncode and required:
            raise WorkerError(f"nvidia-smi failed: {result.stderr.strip() or result.returncode}")
        return result.stdout if result.returncode == 0 else ""

    @staticmethod
    def _mib(value):
        try:
            return int(float(value.strip())) * MIB
        except (ValueError, AttributeError):
            raise WorkerError(f"nvidia-smi returned invalid memory value: {value!r}") from None

    def devices(self):
        output = self._command(
            "--query-gpu=uuid,index,memory.total,compute_mode",
            "--format=csv,noheader,nounits",
        )
        rows = list(csv.reader(output.splitlines(), skipinitialspace=True))
        details = {}
        for row in rows:
            if len(row) != 4:
                raise WorkerError(f"unexpected nvidia-smi GPU row: {row!r}")
            uuid = normalize_uuid(row[0])
            try:
                index = int(row[1].strip())
            except ValueError:
                raise WorkerError(f"invalid nvidia-smi GPU index: {row[1]!r}") from None
            mode = row[3].strip()
            details[uuid] = (index, self._mib(row[2]), mode)
        xml = self._command("-q", "-x")
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise WorkerError(f"cannot parse nvidia-smi MIG status: {exc}") from exc
        seen = set()
        for gpu in root.findall("gpu"):
            uuid_node = gpu.find("uuid")
            mig_node = gpu.find("mig_mode/current_mig")
            if uuid_node is None or not uuid_node.text:
                continue
            uuid = normalize_uuid(uuid_node.text)
            if uuid not in details:
                continue
            if mig_node is None or not mig_node.text:
                raise WorkerError(f"cannot determine MIG status for {uuid}")
            status = mig_node.text.strip().lower()
            if status == "enabled":
                raise WorkerError(f"MIG is enabled on {uuid}")
            if status not in ("disabled", "not supported", "n/a"):
                raise WorkerError(f"unknown MIG status on {uuid}: {mig_node.text.strip()}")
            seen.add(uuid)
            virtualization = gpu.find("gpu_virtualization_mode/virtualization_mode")
            if virtualization is None:
                virtualization = gpu.find("virtualization_mode")
            if virtualization is not None and virtualization.text:
                mode = virtualization.text.strip().lower()
                if mode not in ("none", "baremetal", "pass-through", "passthrough", "not supported", "n/a"):
                    raise WorkerError(f"unsupported virtualized GPU mode on {uuid}: {virtualization.text.strip()}")
        missing_mig_status = set(details) - seen
        if missing_mig_status:
            raise WorkerError(f"cannot determine MIG status for {sorted(missing_mig_status)}")
        mps_environment = (
            "CUDA_MPS_PIPE_DIRECTORY",
            "CUDA_MPS_LOG_DIRECTORY",
            "CUDA_MPS_ACTIVE_THREAD_PERCENTAGE",
            "NVIDIA_MPS_PIPE_DIRECTORY",
        )
        if any(os.environ.get(name) for name in mps_environment):
            raise WorkerError("CUDA MPS environment detected; MPS is unsupported")
        apps = self._command("--query-compute-apps=pid,process_name", "--format=csv,noheader", required=False)
        if "nvidia-cuda-mps-server" in apps.lower():
            raise WorkerError("NVIDIA MPS server process detected; MPS is unsupported")
        return details

    def observe(self):
        output = self._command(
            "--query-gpu=uuid,memory.total,memory.free,memory.used",
            "--format=csv,noheader,nounits",
        )
        result = {}
        for row in csv.reader(output.splitlines(), skipinitialspace=True):
            if len(row) != 4:
                raise WorkerError(f"unexpected nvidia-smi observation row: {row!r}")
            uuid = normalize_uuid(row[0])
            result[uuid] = {
                "total_bytes": self._mib(row[1]),
                "free_bytes": self._mib(row[2]),
                "used_bytes": self._mib(row[3]),
            }
        return result


def parse_targets(value):
    """Decode and deduplicate the explicitly selected namespace/pod pairs."""
    if not value:
        return []
    try:
        targets = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise WorkerError(f"GPU_TARGET_PODS must be a JSON list: {exc}") from exc
    if not isinstance(targets, list):
        raise WorkerError("GPU_TARGET_PODS must be a JSON list")
    normalized = []
    seen = set()
    for target in targets:
        if not isinstance(target, dict):
            raise WorkerError("each GPU_TARGET_PODS entry must contain namespace and name")
        namespace, name = target.get("namespace"), target.get("name")
        if not isinstance(namespace, str) or not namespace.strip() or not isinstance(name, str) or not name.strip():
            raise WorkerError("each GPU_TARGET_PODS entry must contain non-empty namespace and name")
        key = (namespace.strip(), name.strip())
        if key not in seen:
            seen.add(key)
            normalized.append(key)
    return normalized


def pod_resource_devices(targets, socket_path=POD_RESOURCES_SOCKET, timeout=10.0, resource_name="nvidia.com/gpu"):
    """Return only GPU IDs allocated to the explicitly requested pods."""
    if not targets:
        return None
    try:
        import grpc
        import podresources_pb2
        import podresources_pb2_grpc
    except ImportError as exc:
        raise WorkerError(f"PodResources gRPC bindings unavailable: {exc}") from exc
    channel = grpc.insecure_channel(f"unix://{socket_path}")
    try:
        stub = podresources_pb2_grpc.PodResourcesListerStub(channel)
        response = stub.List(podresources_pb2.ListPodResourcesRequest(), timeout=timeout)
    except Exception as exc:
        raise WorkerError(f"PodResources List failed: {exc}") from exc
    finally:
        channel.close()
    requested = set(targets)
    found = set()
    identifiers = []
    for pod in response.pod_resources:
        key = (pod.namespace, pod.name)
        if key not in requested:
            continue
        found.add(key)
        pod_identifiers = []
        for container in pod.containers:
            if getattr(container, "dynamic_resources", ()):
                raise WorkerError(f"requested GPU target pod {key} has unresolved DRA resources")
            for device in container.devices:
                if is_gpu_resource(device.resource_name, resource_name):
                    pod_identifiers.extend(device.device_ids)
        if not pod_identifiers:
            raise WorkerError(f"requested GPU target pod {key} has no GPU device allocations")
        identifiers.extend(pod_identifiers)
    missing = requested - found
    if missing:
        raise WorkerError(f"requested GPU target pods missing from PodResources: {sorted(missing)}")
    return identifiers


def _resolve_identifier(identifier, devices, allow_replica=False):
    text = str(identifier).strip()
    if text.isdecimal():
        index = int(text)
        matches = [device for device in devices if device.index == index]
        if len(matches) != 1:
            raise WorkerError(f"GPU index allocation {text!r} does not identify exactly one visible device")
        return matches[0]
    if allow_replica and "::" in text:
        base, replica, *extra = text.split("::")
        if extra or not replica.isdecimal():
            raise WorkerError(f"invalid NVIDIA time-sliced GPU allocation ID: {text!r}")
        text = base
    uuid = normalize_uuid(text)
    matches = [device for device in devices if device.uuid == uuid]
    if len(matches) != 1:
        raise WorkerError(f"GPU allocation {text!r} does not identify exactly one visible device")
    return matches[0]


def select_devices(all_devices: list[Device], gpu_ids: str, target_ids: list[str] | None) -> list[Device]:
    """Resolve requested indices or UUIDs, preserving explicit input order."""
    if not all_devices:
        raise WorkerError("no CUDA devices were discovered")
    canonical = {}
    for device in sorted(all_devices, key=lambda item: item.index):
        canonical.setdefault(device.uuid, device)
    devices = list(canonical.values())
    if target_ids is None:
        eligible = sorted(devices, key=lambda device: device.index)
    else:
        eligible = []
        for identifier in target_ids:
            device = _resolve_identifier(identifier, devices, allow_replica=True)
            if device.uuid not in {candidate.uuid for candidate in eligible}:
                eligible.append(device)
        eligible.sort(key=lambda device: device.index)
        if not eligible:
            raise WorkerError("requested target pods map to no visible GPU devices")
    if gpu_ids.strip().lower() == "all":
        selected = eligible
    else:
        requested = csv_values(gpu_ids)
        selected = []
        seen = set()
        for identifier in requested:
            device = _resolve_identifier(identifier, devices)
            if device.uuid in seen:
                raise WorkerError(f"GPU_IDS contains duplicate physical GPU {device.uuid}")
            seen.add(device.uuid)
            if device.uuid not in {candidate.uuid for candidate in eligible}:
                raise WorkerError(f"GPU {identifier!r} is not allocated to the requested target pods")
            selected.append(device)
    if not selected:
        raise WorkerError("GPU_IDS selected no devices")
    return selected
