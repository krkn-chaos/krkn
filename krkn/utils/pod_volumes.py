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

"""Helpers for resolving PVC-backed pod filesystem and block volumes."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class PodVolumeTarget:
    """A PVC exposed to a container as a filesystem or raw block device."""

    pvc_name: str
    volume_name: str
    container_name: str
    path: str
    mode: str


def _get(value: Any, *names: str, default: Any = None) -> Any:
    """Read either Kubernetes client attributes or dictionary fields."""
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _get_text(value: Any, *names: str, default: str = "") -> str:
    """Read the first string-valued field, ignoring unset mock attributes."""
    for name in names:
        candidate = _get(value, name, default=None)
        if isinstance(candidate, str):
            return candidate
    return default


def find_pvc_volume(
    pod: Any, pvc_name: str = "", path: str = ""
) -> Optional[PodVolumeTarget]:
    """Find a PVC exposed through a pod mount or container block device.

    Supports both the krkn-lib ``Pod`` model and raw Kubernetes Pod objects.
    Raw objects are needed for KubeVirt ``volumeDevices`` because that field is
    not represented by the krkn-lib Pod model.
    """
    direct_volumes = _get(pod, "volumes", default=None)
    direct_containers = _get(pod, "containers", default=None)
    if isinstance(direct_volumes, (list, tuple)) or isinstance(
        direct_containers, (list, tuple)
    ):
        volumes = direct_volumes or []
        containers = direct_containers or []
    else:
        spec = _get(pod, "spec")
        volumes = _get(spec, "volumes", default=[]) if spec is not None else []
        containers = _get(spec, "containers", default=[]) if spec is not None else []

    for volume in volumes or []:
        model_claim_name = _get_text(volume, "pvcName", default="")
        if model_claim_name:
            claim_name = model_claim_name
        else:
            claim = _get(volume, "persistent_volume_claim", "persistentVolumeClaim")
            claim_name = _get_text(claim, "claim_name", "claimName")
        if not claim_name or (pvc_name and claim_name != pvc_name):
            continue

        volume_name = _get_text(volume, "name")
        for container in containers or []:
            container_name = _get_text(container, "name")

            mounts = _get(container, "volume_mounts", default=None)
            if not isinstance(mounts, (list, tuple)):
                mounts = _get(container, "volumeMounts", default=[])
            for mount in mounts or []:
                if _get_text(mount, "name") != volume_name:
                    continue
                mount_path = _get_text(mount, "mount_path", "mountPath")
                if path and mount_path != path:
                    continue
                return PodVolumeTarget(
                    pvc_name=claim_name,
                    volume_name=volume_name,
                    container_name=container_name,
                    path=mount_path,
                    mode="filesystem",
                )

            devices = _get(container, "volume_devices", default=None)
            if not isinstance(devices, (list, tuple)):
                devices = _get(container, "volumeDevices", default=[])
            for device in devices or []:
                if _get_text(device, "name") != volume_name:
                    continue
                device_path = _get_text(device, "device_path", "devicePath")
                if path and device_path != path:
                    continue
                return PodVolumeTarget(
                    pvc_name=claim_name,
                    volume_name=volume_name,
                    container_name=container_name,
                    path=device_path,
                    mode="block",
                )

    return None


def resolve_pvc_volume(
    lib_k8s: Any, pod: Any, pvc_name: str = "", path: str = ""
) -> Optional[PodVolumeTarget]:
    """Resolve a PVC from the simplified pod model or its raw API object."""
    target = find_pvc_volume(pod, pvc_name, path)
    if target is not None:
        return target

    raw_pod = read_raw_pod(lib_k8s, pod.name, pod.namespace)
    if raw_pod is None:
        return None
    return find_pvc_volume(raw_pod, pvc_name, path)


def read_raw_pod(lib_k8s: Any, pod_name: str, namespace: str) -> Optional[Any]:
    """Read a Pod directly when the simplified krkn-lib model is insufficient."""
    cli = getattr(lib_k8s, "cli", None)
    if cli is None:
        return None
    try:
        return cli.read_namespaced_pod(name=pod_name, namespace=namespace)
    except Exception:
        return None


def resolve_vmi_pod(lib_k8s: Any, vmi_name: str, namespace: str) -> str:
    """Resolve the active, running virt-launcher pod for a VMI."""
    vmi = lib_k8s.get_vmi(vmi_name, namespace)
    if not vmi:
        return ""

    status = vmi.get("status", {})
    if status.get("phase") and status["phase"] != "Running":
        return ""
    node_name = status.get("nodeName")
    active_pods = status.get("activePods") or {}

    candidates = []
    for selector in (
        f"vm.kubevirt.io/name={vmi_name}",
        f"kubevirt.io/domain={vmi_name}",
    ):
        pod_names = lib_k8s.list_pods(namespace, label_selector=selector)
        for pod_name in pod_names or []:
            if pod_name not in candidates:
                candidates.append(pod_name)

    for pod_name in candidates:
        pod = read_raw_pod(lib_k8s, pod_name, namespace)
        if pod is None:
            continue
        metadata = _get(pod, "metadata", default={})
        pod_status = _get(pod, "status", default={})
        pod_spec = _get(pod, "spec", default={})
        pod_uid = _get(metadata, "uid", default="")
        deletion_timestamp = _get(metadata, "deletion_timestamp", "deletionTimestamp")
        phase = _get(pod_status, "phase", default="")
        pod_node = _get(pod_spec, "node_name", "nodeName", default="")
        if deletion_timestamp or phase != "Running":
            continue
        if node_name and pod_node != node_name:
            continue
        if active_pods and pod_uid not in active_pods:
            continue
        return pod_name
    return ""
