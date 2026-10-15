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
from threading import Thread
from dataclasses import asdict, dataclass, replace

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
    kubeconfig_path: str = ""


def _run_virtctl(
    params: GuestStorageParams, command: str, timeout: int
) -> subprocess.CompletedProcess:
    """Execute a command inside the VMI through virtctl SSH."""
    # Send multiline guest scripts over stdin rather than embedding the full
    # script in SSH's exec request. Some lightweight guest SSH servers reject
    # long or multiline exec requests even though simple commands work.
    remote_command = "sh -s" if "\n" in command else command
    args = [
        "virtctl",
        "ssh",
        "--known-hosts=/dev/null",
        "--namespace",
        params.namespace,
        "--local-ssh-opts=-o StrictHostKeyChecking=no",
        "--local-ssh-opts=-o UserKnownHostsFile=/dev/null",
        "--local-ssh-opts=-o BatchMode=yes",
        "--local-ssh-opts=-o PasswordAuthentication=no",
    ]
    if params.identity_file:
        args.extend(["--identity-file", params.identity_file])
    if params.kubeconfig_path:
        args.extend(["--kubeconfig", params.kubeconfig_path])
    args.extend(
        [
            "--local-ssh-opts=-o IdentitiesOnly=yes",
            "--command",
            remote_command,
            f"{params.username}@vmi/{params.vmi_name}",
        ]
    )

    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_lines = []
    stderr_lines = []

    def read_stream(stream, lines, log_output=False):
        for line in stream:
            lines.append(line)
            if log_output and line.strip():
                logging.info("VMI guest: %s", line.rstrip())

    stdout_reader = Thread(
        target=read_stream, args=(process.stdout, stdout_lines, True), daemon=True
    )
    stderr_reader = Thread(
        target=read_stream, args=(process.stderr, stderr_lines), daemon=True
    )
    stdout_reader.start()
    stderr_reader.start()

    try:
        if remote_command == "sh -s":
            try:
                process.stdin.write(command)
                process.stdin.flush()
            except BrokenPipeError:
                pass
        process.stdin.close()
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        stdout_reader.join()
        stderr_reader.join()
        raise subprocess.TimeoutExpired(
            args,
            timeout,
            output="".join(stdout_lines),
            stderr="".join(stderr_lines),
        ) from exc

    stdout_reader.join()
    stderr_reader.join()
    result = subprocess.CompletedProcess(
        args,
        process.returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )
    if result.returncode != 0:
        informational = (
            "Permanently added",
            "post-quantum key exchange algorithm",
            "store now, decrypt later",
            "openssh.com/pq",
        )
        error_lines = [
            line for line in (result.stderr or result.stdout).splitlines()
            if not any(message in line for message in informational)
        ]
        raise RuntimeError(
            "virtctl guest command failed for VMI %s: %s"
            % (params.vmi_name, "\n".join(error_lines).strip())
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
        fill_percentage = values.get("fill_percentage")
        if fill_percentage is None or (
            isinstance(fill_percentage, str) and not fill_percentage.strip()
        ):
            fill_percentage = 50

        params = GuestStorageParams(
            vmi_name=str(values.get("vmi_name", "")),
            namespace=str(values.get("namespace", "default")),
            device_path=str(values.get("device_path", "")),
            mount_path=str(values.get("mount_path", "/mnt/krkn-data")),
            filesystem=str(values.get("filesystem", "ext4")),
            fill_percentage=int(fill_percentage),
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
    sudo -n rm -f "$fill_file"
    if [ "$mounted_here" -eq 1 ]; then
        sudo -n umount "$mount_path"
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
    echo "Formatting $device with {filesystem} (existing device data will be erased)"
    sudo -n mkfs -t {filesystem} "$device" >/dev/null
fi
sudo -n mkdir -p "$mount_path"
mounted_source="$(findmnt -rn -o SOURCE --mountpoint "$mount_path" || true)"
if [ -n "$mounted_source" ]; then
    mounted_real="$(readlink -f "$mounted_source" 2>/dev/null || true)"
    device_real="$(readlink -f "$device" 2>/dev/null || true)"
    if [ "$mounted_source" != "$device" ] && [ "$mounted_real" != "$device_real" ]; then
        echo "mount path $mount_path belongs to $mounted_source, not $device" >&2
        exit 1
    fi
else
    sudo -n mount -t {filesystem} "$device" "$mount_path"
    mounted_here=1
    : > "$mount_marker"
fi
sudo -n chown "$(id -u):$(id -g)" "$mount_path"

read -r capacity used <<EOF
$(df -P -B1 "$mount_path" | awk 'NR == 2 {{print $2, $3}}')
EOF
target=$((capacity * {params.fill_percentage} / 100))
fill_size=$((target - used))
available=$((capacity - used))
current_percent=$((used * 100 / capacity))
echo "VMI PVC before fill: capacity=${{capacity}}B used=${{used}}B available=${{available}}B utilization=${{current_percent}}%"
if [ "$fill_size" -le 0 ]; then
    echo "filesystem is already at or above the requested fill percentage (target_bytes=$target)" >&2
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
file_size=$(stat -c %s "$fill_file")
file_allocated=$(du -B1 "$fill_file" | awk 'NR == 1 {{print $1}}')
read -r capacity_after used_after <<EOF
$(df -P -B1 "$mount_path" | awk 'NR == 2 {{print $2, $3}}')
EOF
available_after=$((capacity_after - used_after))
utilization_after=$((used_after * 100 / capacity_after))
echo "VMI PVC fill: file=${{file_size}}B allocated=${{file_allocated}}B; capacity=${{capacity_after}}B used=${{used_after}}B available=${{available_after}}B utilization=${{utilization_after}}% target={params.fill_percentage}% hold={params.duration}s"
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
            params = replace(
                params,
                kubeconfig_path=lib_k8s.get_kubeconfig_path(),
            )
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
                "VMI block PVC target: vmi=%s namespace=%s pvc=%s device=%s mount=%s filesystem=%s",
                params.vmi_name,
                params.namespace,
                params.pvc_name,
                params.device_path,
                params.mount_path,
                params.filesystem,
            )
            # Verify guest authentication before registering rollback. If SSH
            # cannot authenticate, there is no guest-side change to clean up.
            _run_virtctl(params, "true", timeout=20)
            self.rollback_handler.set_rollback_callable(
                self.rollback_guest_storage,
                RollbackContent(
                    namespace=params.namespace,
                    resource_identifier=encode_rollback_data(asdict(params)),
                ),
            )
            logging.info(
                "Starting VMI block PVC fill: target=%s%%, duration=%ss",
                params.fill_percentage,
                params.duration,
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
        logging.info(
            "VMI filesystem PVC target: vmi=%s namespace=%s pvc=%s pod=%s mount=%s",
            params.vmi_name or "N/A",
            params.namespace,
            volume_target.pvc_name,
            pod_name,
            volume_target.path,
        )

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
            import base64
            import json
            import logging
            import shlex
            import subprocess

            values = json.loads(
                base64.b64decode(
                    rollback_content.resource_identifier.encode("ascii")
                ).decode("utf-8")
            )
            cleanup = (
                "set -eu; device=%s; mount_path=%s; fill_file=%s; "
                'mounted_source="$(findmnt -rn -o SOURCE --mountpoint "$mount_path" || true)"; '
                'device_real="$(readlink -f "$device" 2>/dev/null || true)"; '
                'mounted_real="$(readlink -f "$mounted_source" 2>/dev/null || true)"; '
                'if [ -n "$mounted_source" ] && { '
                '[ "$mounted_source" = "$device" ] || [ "$mounted_real" = "$device_real" ]; }; then '
                'sudo -n rm -f "$fill_file"; '
                'if [ -f /tmp/krkn-vmi-pvc-fill-mounted ]; then '
                'sudo -n umount "$mount_path"; rm -f /tmp/krkn-vmi-pvc-fill-mounted; fi; fi'
                % (
                    shlex.quote(values["device_path"]),
                    shlex.quote(values["mount_path"]),
                    shlex.quote(f"{values['mount_path']}/krkn-vmi-storage.tmp"),
                )
            )
            args = [
                "virtctl",
                "ssh",
                "--known-hosts=/dev/null",
                "--namespace",
                values["namespace"],
                "--local-ssh-opts=-o StrictHostKeyChecking=no",
                "--local-ssh-opts=-o UserKnownHostsFile=/dev/null",
                "--local-ssh-opts=-o BatchMode=yes",
                "--local-ssh-opts=-o PasswordAuthentication=no",
            ]
            if values.get("identity_file"):
                args.extend(["--identity-file", values["identity_file"]])
            if values.get("kubeconfig_path"):
                args.extend(["--kubeconfig", values["kubeconfig_path"]])
            args.extend(
                [
                    "--local-ssh-opts=-o IdentitiesOnly=yes",
                    "--command",
                    cleanup,
                    f"{values['username']}@vmi/{values['vmi_name']}",
                ]
            )
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=60, check=False
            )
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout).strip())
        except Exception as exc:
            logging.error("VMI guest storage rollback failed: %s", exc)
