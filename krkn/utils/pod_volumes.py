# Copyright 2026 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Helpers for resolving PVC-backed filesystem and block volumes."""

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
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _text(value: Any, *names: str) -> str:
    for name in names:
        result = _get(value, name, default=None)
        if isinstance(result, str):
            return result
    return ""


def find_pvc_volume(pod: Any, pvc_name: str = "", path: str = "") -> Optional[PodVolumeTarget]:
    """Find a PVC exposed through volumeMounts or volumeDevices."""
    direct_volumes = _get(pod, "volumes", default=None)
    direct_containers = _get(pod, "containers", default=None)
    if isinstance(direct_volumes, (list, tuple)) or isinstance(direct_containers, (list, tuple)):
        volumes, containers = direct_volumes or [], direct_containers or []
    else:
        spec = _get(pod, "spec", default={})
        volumes = _get(spec, "volumes", default=[]) or []
        containers = _get(spec, "containers", default=[]) or []

    for volume in volumes:
        claim_name = _text(volume, "pvcName")
        if not claim_name:
            claim = _get(volume, "persistent_volume_claim", "persistentVolumeClaim", default={})
            claim_name = _text(claim, "claim_name", "claimName")
        if not claim_name or (pvc_name and claim_name != pvc_name):
            continue

        volume_name = _text(volume, "name")
        for container in containers:
            container_name = _text(container, "name")
            mounts = _get(container, "volume_mounts", default=None)
            if not isinstance(mounts, (list, tuple)):
                mounts = _get(container, "volumeMounts", default=[]) or []
            for mount in mounts:
                if _text(mount, "name") == volume_name:
                    mount_path = _text(mount, "mount_path", "mountPath")
                    if not path or path == mount_path:
                        return PodVolumeTarget(claim_name, volume_name, container_name, mount_path, "filesystem")

            devices = _get(container, "volume_devices", default=None)
            if not isinstance(devices, (list, tuple)):
                devices = _get(container, "volumeDevices", default=[]) or []
            for device in devices:
                if _text(device, "name") == volume_name:
                    device_path = _text(device, "device_path", "devicePath")
                    if not path or path == device_path:
                        return PodVolumeTarget(claim_name, volume_name, container_name, device_path, "block")
    return None


def read_raw_pod(lib_k8s: Any, pod_name: str, namespace: str) -> Optional[Any]:
    """Read the raw Kubernetes Pod when krkn-lib's model is insufficient."""
    cli = getattr(lib_k8s, "cli", None)
    if cli is None:
        return None
    try:
        return cli.read_namespaced_pod(name=pod_name, namespace=namespace)
    except Exception:
        return None


def resolve_pvc_volume(lib_k8s: Any, pod: Any, pvc_name: str = "", path: str = "") -> Optional[PodVolumeTarget]:
    target = find_pvc_volume(pod, pvc_name, path)
    if target:
        return target
    raw_pod = read_raw_pod(lib_k8s, pod.name, pod.namespace)
    return find_pvc_volume(raw_pod, pvc_name, path) if raw_pod else None


def resolve_vmi_pod(lib_k8s: Any, vmi_name: str, namespace: str) -> str:
    """Return the active Running virt-launcher Pod for a VMI."""
    vmi = lib_k8s.get_vmi(vmi_name, namespace)
    if not vmi:
        return ""
    status = vmi.get("status", {})
    if status.get("phase") and status["phase"] != "Running":
        return ""
    node_name = status.get("nodeName")
    active_pods = status.get("activePods") or {}
    candidates = []
    for selector in (f"vm.kubevirt.io/name={vmi_name}", f"kubevirt.io/domain={vmi_name}"):
        for pod_name in lib_k8s.list_pods(namespace, label_selector=selector) or []:
            if pod_name not in candidates:
                candidates.append(pod_name)
    for pod_name in candidates:
        pod = read_raw_pod(lib_k8s, pod_name, namespace)
        if not pod:
            continue
        metadata = _get(pod, "metadata", default={})
        pod_status = _get(pod, "status", default={})
        pod_spec = _get(pod, "spec", default={})
        if _get(metadata, "deletion_timestamp", "deletionTimestamp"):
            continue
        if _get(pod_status, "phase") != "Running":
            continue
        if node_name and _get(pod_spec, "node_name", "nodeName") != node_name:
            continue
        if active_pods and _get(metadata, "uid", default="") not in active_pods:
            continue
        return pod_name
    return ""
