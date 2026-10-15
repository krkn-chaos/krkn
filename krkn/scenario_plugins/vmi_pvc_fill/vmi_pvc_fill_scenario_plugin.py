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

"""Fill VMI-backed PVCs through filesystem or guest-level access."""

import logging
import base64
import json
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass

import yaml
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator
from krkn.utils.filesystem_pvc import (
    encode_rollback_data,
    fill_filesystem_pvc,
    rollback_filesystem_fill,
)
from krkn.utils.pod_volumes import read_raw_pod, resolve_pvc_volume, resolve_vmi_pod


@dataclass(frozen=True)
class GuestStorageParams:
    """Validated configuration for the guest storage scenario."""

    vmi_name: str
    namespace: str
    device_path: str
    mount_path: str
    filesystem: str
    fill_percentage: int
    duration: int
    format_device: bool
    username: str
    identity_file: str
    pvc_name: str = ""
    pod_name: str = ""


def _run_virtctl(
    params: GuestStorageParams, command: str, timeout: int
) -> subprocess.CompletedProcess:
    """Execute a command inside the VMI through virtctl SSH."""
    args = [
        "virtctl",
        "ssh",
        f"{params.username}@vmi/{params.vmi_name}",
        "--namespace",
        params.namespace,
        "--command",
        command,
    ]
    if params.identity_file:
        args.extend(["--identity-file", params.identity_file])

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "virtctl guest command failed for VMI %s: %s"
            % (params.vmi_name, (result.stderr or result.stdout).strip())
        )
    return result


class VmiPvcFillScenarioPlugin(AbstractScenarioPlugin):
    """Fill a VMI PVC through its filesystem mount or guest block device."""

    def __init__(self, scenario_type: str = None):
        super().__init__(scenario_type or "vmi_pvc_fill_scenarios")

    def get_scenario_types(self) -> list[str]:
        return ["vmi_pvc_fill_scenarios"]

    def _parse_config(self, scenario: str) -> GuestStorageParams:
        with open(scenario, "r") as scenario_file:
            config = yaml.safe_load(scenario_file) or {}
        values = config.get("vmi_pvc_fill_scenario", {})

        params = GuestStorageParams(
            vmi_name=str(values.get("vmi_name", "")),
            namespace=str(values.get("namespace", "default")),
            device_path=str(values.get("device_path", "")),
            mount_path=str(values.get("mount_path", "/mnt/krkn-data")),
            filesystem=str(values.get("filesystem", "ext4")),
            fill_percentage=int(values.get("fill_percentage", 50)),
            duration=int(values.get("duration", 60)),
            format_device=values.get("format_device", False),
            username=str(values.get("username", "root")),
            identity_file=str(values.get("identity_file", "")),
            pvc_name=str(values.get("pvc_name", "")),
            pod_name=str(values.get("pod_name", "")),
        )

        if not params.namespace or not (
            params.vmi_name or params.pod_name or params.pvc_name
        ):
            raise ValueError("namespace and one target are required")
        if params.device_path and not re.fullmatch(
            r"/dev/[A-Za-z0-9._/-]+", params.device_path
        ):
            raise ValueError("device_path must be a safe absolute /dev path")
        if (
            params.mount_path
            and (
                ".." in params.mount_path
                or not re.fullmatch(r"/[A-Za-z0-9._/-]+", params.mount_path)
            )
        ):
            raise ValueError("mount_path must be a safe absolute path")
        if params.filesystem not in ("ext4", "xfs"):
            raise ValueError("filesystem must be ext4 or xfs")
        if not 1 <= params.fill_percentage <= 99:
            raise ValueError("fill_percentage must be between 1 and 99")
        if params.duration <= 0:
            raise ValueError("duration must be positive")
        if not isinstance(params.format_device, bool):
            raise ValueError("format_device must be boolean")
        return params

    @staticmethod
    def _guest_command(params: GuestStorageParams) -> str:
        """Build the guest-side format, fill, wait, and cleanup command."""
        device = shlex.quote(params.device_path)
        mount = shlex.quote(params.mount_path)
        fill_file = shlex.quote(f"{params.mount_path}/krkn-vmi-storage.tmp")
        filesystem = shlex.quote(params.filesystem)
        format_flag = "1" if params.format_device else "0"

        return f"""set -eu
device={device}
mount_path={mount}
fill_file={fill_file}
mount_marker=/tmp/krkn-vmi-pvc-fill-mounted
mounted_here=0
cleanup() {{
    rm -f "$fill_file"
    if [ "$mounted_here" -eq 1 ]; then
        umount "$mount_path"
    fi
    rm -f "$mount_marker"
}}
trap cleanup EXIT

if [ ! -b "$device" ]; then
    echo "block device $device was not found" >&2
    exit 1
fi
if [ "{format_flag}" -eq 1 ]; then
    if findmnt -rn -S "$device" >/dev/null 2>&1; then
        echo "refusing to format already-mounted device $device" >&2
        exit 1
    fi
    mkfs -t {filesystem} "$device"
fi
mkdir -p "$mount_path"
mounted_source="$(findmnt -rn -o SOURCE --target "$mount_path" || true)"
if [ -n "$mounted_source" ]; then
    mounted_real="$(readlink -f "$mounted_source" 2>/dev/null || true)"
    device_real="$(readlink -f "$device" 2>/dev/null || true)"
    if [ "$mounted_source" != "$device" ] && [ "$mounted_real" != "$device_real" ]; then
        echo "mount path $mount_path belongs to $mounted_source, not $device" >&2
        exit 1
    fi
else
    mount "$device" "$mount_path"
    mounted_here=1
    : > "$mount_marker"
fi

read -r capacity used <<EOF
$(df -P -B1 "$mount_path" | awk 'NR == 2 {{print $2, $3}}')
EOF
target=$((capacity * {params.fill_percentage} / 100))
fill_size=$((target - used))
if [ "$fill_size" -le 0 ]; then
    echo "filesystem is already at or above the requested fill percentage" >&2
    exit 1
fi
if command -v fallocate >/dev/null 2>&1; then
    fallocate -l "$fill_size" "$fill_file"
else
    full_blocks=$((fill_size / 1048576))
    remainder=$((fill_size % 1048576))
    if [ "$full_blocks" -gt 0 ]; then
        dd if=/dev/zero of="$fill_file" bs=1M count="$full_blocks" status=none
    fi
    if [ "$remainder" -gt 0 ]; then
        dd if=/dev/zero of="$fill_file" bs=1 count="$remainder" oflag=append conv=notrunc status=none
    fi
fi
sleep {params.duration}
"""

    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry,
        scenario_telemetry,
    ) -> int:
        """Run filesystem PVC fill directly or fill a block disk in the guest."""
        try:
            params = self._parse_config(scenario)
            lib_k8s = lib_telemetry.get_lib_kubernetes()
            pod_name = self._resolve_pod_name(lib_k8s, params)
            raw_pod = read_raw_pod(lib_k8s, pod_name, params.namespace)
            if raw_pod is None:
                raise RuntimeError("unable to read target VMI Pod")
            target = resolve_pvc_volume(lib_k8s, raw_pod, params.pvc_name)
            if target is None:
                raise RuntimeError("target PVC was not found on the VMI Pod")

            if target.mode == "filesystem":
                result = self._run_filesystem_pvc(
                    run_uuid, scenario, lib_telemetry, scenario_telemetry,
                    params, pod_name, target, raw_pod,
                )
                if result == 0:
                    logging.info("VMI filesystem PVC fill completed (exit code: 0)")
                else:
                    logging.error("VMI filesystem PVC fill failed (exit code: 1)")
                return result
            if not params.vmi_name:
                raise ValueError("vmi_name is required for block PVCs")
            if not params.device_path:
                raise ValueError(
                    "device_path is required for block PVCs and must be the "
                    "path inside the VMI guest, not the virt-launcher Pod"
                )

            logging.info(
                "VMI block PVC target: vmi=%s namespace=%s device=%s mount=%s",
                params.vmi_name,
                params.namespace,
                params.device_path,
                params.mount_path,
            )
            self.rollback_handler.set_rollback_callable(
                self.rollback_guest_storage,
                RollbackContent(
                    namespace=params.namespace,
                    resource_identifier=yaml.safe_dump(asdict(params)),
                ),
            )
            _run_virtctl(
                params,
                self._guest_command(params),
                timeout=params.duration + 120,
            )
            logging.info("VMI block PVC fill completed (exit code: 0)")
            return 0
        except Exception as exc:
            logging.error(
                "VMI guest storage scenario failed (exit code: 1): %s", exc
            )
            return 1

    @staticmethod
    def _resolve_pod_name(lib_k8s, params: GuestStorageParams) -> str:
        if params.vmi_name:
            pod_name = resolve_vmi_pod(lib_k8s, params.vmi_name, params.namespace)
        elif params.pod_name:
            pod_name = params.pod_name
        else:
            pvc = lib_k8s.get_pvc_info(params.pvc_name, params.namespace)
            pod_name = pvc.podNames[0] if pvc and pvc.podNames else ""
        if not pod_name:
            raise RuntimeError("unable to resolve a target Pod")
        return pod_name

    def _run_filesystem_pvc(
        self, run_uuid, scenario, lib_telemetry, scenario_telemetry,
        params, pod_name, volume_target, pod,
    ) -> int:
        """Fill filesystem-backed PVCs through the shared filesystem service."""
        def register_rollback(data):
            self.rollback_handler.set_rollback_callable(
                rollback_filesystem_fill,
                RollbackContent(
                    namespace=params.namespace,
                    resource_identifier=encode_rollback_data(data),
                ),
            )

        result, _ = fill_filesystem_pvc(
            lib_telemetry.get_lib_kubernetes(),
            pod_name,
            params.namespace,
            params.pvc_name,
            params.fill_percentage,
            params.duration,
            volume_target=volume_target,
            on_file_created=register_rollback,
            pod=pod,
        )
        return result

    @staticmethod
    def rollback_guest_storage(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ) -> None:
        """Best-effort cleanup for an interrupted guest storage scenario."""
        try:
            values = json.loads(
                base64.b64decode(
                    rollback_content.resource_identifier.encode("ascii")
                ).decode("utf-8")
            )
            params = GuestStorageParams(**values)
            cleanup = (
                "set -eu; rm -f %s; "
                "if [ -f /tmp/krkn-vmi-pvc-fill-mounted ]; then "
                "umount %s; rm -f /tmp/krkn-vmi-pvc-fill-mounted; fi"
                % (
                    shlex.quote(f"{params.mount_path}/krkn-vmi-storage.tmp"),
                    shlex.quote(params.mount_path),
                )
            )
            _run_virtctl(params, cleanup, timeout=60)
        except Exception as exc:
            logging.error("VMI guest storage rollback failed: %s", exc)
