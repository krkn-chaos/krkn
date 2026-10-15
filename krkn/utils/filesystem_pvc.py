# Copyright 2026 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Shared filesystem PVC fill operations."""

import base64
import json
import logging
import time
from typing import Any, Callable, Optional

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.utils.pod_volumes import PodVolumeTarget, resolve_pvc_volume


def encode_rollback_data(data: dict) -> str:
    """Encode rollback data safely for generated rollback Python modules."""
    return base64.b64encode(
        json.dumps(data, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def decode_rollback_data(value: str) -> dict:
    """Decode rollback data stored in a resource identifier."""
    return json.loads(base64.b64decode(value.encode("ascii")).decode("utf-8"))


def fill_filesystem_pvc(
    kubecli,
    pod_name: str,
    namespace: str,
    pvc_name: str = "",
    target_fill_percentage: float = 50,
    duration: int = 60,
    block_size: int = 102400,
    volume_target: Optional[PodVolumeTarget] = None,
    on_file_created: Optional[Callable[[dict], None]] = None,
    pod: Any = None,
):
    """Fill a filesystem-backed PVC and return ``(status, rollback_data)``."""
    pod = pod or kubecli.get_pod_info(name=pod_name, namespace=namespace)
    if pod is None:
        logging.error("Pod '%s' doesn't exist in namespace '%s'", pod_name, namespace)
        return 1, None

    target = volume_target or resolve_pvc_volume(kubecli, pod, pvc_name)
    if target is None:
        logging.error("Pod '%s' does not use the requested PVC", pod_name)
        return 1, None
    if target.mode != "filesystem":
        logging.error("PVC '%s' is not exposed as a filesystem", target.pvc_name)
        return 1, None

    pvc_name = target.pvc_name
    container_name = target.container_name
    mount_path = target.path

    shell = kubecli.get_pod_shell(pod_name, namespace, container_name)
    if shell is None:
        logging.error(
            "Container '%s' in pod '%s' has no usable shell",
            container_name,
            pod_name,
        )
        return 1, None

    command_output = kubecli.exec_cmd_in_pod(
        ["df %s -B 1024 | sed 1d" % mount_path],
        pod_name,
        namespace,
        container_name,
    ).split()
    pvc_used_kb = int(command_output[2])
    pvc_capacity_kb = pvc_used_kb + int(command_output[3])
    current_fill_percentage = pvc_used_kb / pvc_capacity_kb
    if not current_fill_percentage * 100 < float(target_fill_percentage) <= 99:
        logging.error(
            "Target fill percentage (%.2f%%) is lower than current fill "
            "percentage (%.2f%%) or higher than 99%%",
            target_fill_percentage,
            current_fill_percentage * 100,
        )
        return 1, None

    file_size_kb = int(
        (float(target_fill_percentage / 100) * float(pvc_capacity_kb))
        - float(pvc_used_kb)
    )
    file_name = "kraken.tmp"
    full_path = "%s/%s" % (mount_path, file_name)

    fallocate = kubecli.exec_cmd_in_pod(
        ["command -v fallocate"], pod_name, namespace, container_name
    )
    dd = kubecli.exec_cmd_in_pod(
        ["command -v dd"], pod_name, namespace, container_name
    )
    if fallocate:
        command = "fallocate -l $((%s*1024)) %s" % (file_size_kb, full_path)
    elif dd is not None:
        blocks = int(file_size_kb / int(int(block_size) / 1024))
        logging.warning("fallocate not found, using dd; this may take longer")
        command = (
            "dd if=/dev/urandom of=%s bs=%s count=%s oflag=direct"
            % (full_path, block_size, blocks)
        )
    else:
        logging.error("Unable to find fallocate or dd in the target container")
        return 1, None

    kubecli.exec_cmd_in_pod([command], pod_name, namespace, container_name)
    response = kubecli.exec_cmd_in_pod(
        ["ls -lh %s" % mount_path], pod_name, namespace, container_name
    )
    if file_name.lower() not in str(response).lower():
        logging.error("Failed to create temporary file with %s KB", file_size_kb)
        remove_filesystem_fill(kubecli, pod_name, namespace, container_name, mount_path, file_name)
        return 1, None

    rollback_data = {
        "pod_name": pod_name,
        "namespace": namespace,
        "container_name": container_name,
        "mount_path": mount_path,
        "file_name": file_name,
        "full_path": full_path,
    }
    if on_file_created:
        on_file_created(rollback_data)
    time.sleep(duration)
    remove_filesystem_fill(kubecli, pod_name, namespace, container_name, mount_path, file_name)
    return 0, rollback_data


def remove_filesystem_fill(
    kubecli, pod_name: str, namespace: str, container_name: str,
    mount_path: str, file_name: str,
) -> None:
    """Remove and verify the shared PVC fill file."""
    full_path = "%s/%s" % (mount_path, file_name)
    kubecli.exec_cmd_in_pod(
        ["rm -f %s" % full_path], pod_name, namespace, container_name
    )
    response = kubecli.exec_cmd_in_pod(
        ["ls -lh %s" % mount_path], pod_name, namespace, container_name
    )
    if file_name.lower() in str(response).lower():
        raise RuntimeError("Failed to delete temporary PVC fill file")


def rollback_filesystem_fill(
    rollback_data: str, lib_telemetry: KrknTelemetryOpenshift
) -> None:
    """Best-effort rollback for a filesystem PVC fill."""
    try:
        rollback_data = decode_rollback_data(rollback_data)
        kubecli = lib_telemetry.get_lib_kubernetes()
        remove_filesystem_fill(
            kubecli,
            rollback_data["pod_name"],
            rollback_data["namespace"],
            rollback_data["container_name"],
            rollback_data["mount_path"],
            rollback_data["file_name"],
        )
    except Exception as exc:
        logging.error("Failed to rollback filesystem PVC fill: %s", exc)
