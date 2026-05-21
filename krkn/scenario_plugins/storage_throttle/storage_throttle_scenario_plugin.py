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
import base64
import json
import logging
import random
import time
import traceback
from dataclasses import dataclass
from typing import Optional

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator
from krkn.scenario_plugins.storage_throttle.storage_throttle_utils import (
    parse_byte_value,
    parse_duration_value,
    validate_cgroup_path,
    validate_container_id,
    validate_maj_min,
    validate_mount_path,
)

# Backward-compatible aliases so existing imports of the underscore-prefixed
# names from this module continue to work (e.g. in tests).
_validate_mount_path = validate_mount_path
_validate_cgroup_path = validate_cgroup_path
_validate_container_id = validate_container_id
_validate_maj_min = validate_maj_min
_parse_byte_value = parse_byte_value
_parse_duration_value = parse_duration_value


@dataclass(frozen=True)
class ThrottleParams:
    """Parsed and validated scenario configuration for storage throttle."""
    pvc_name: str
    pod_name: str
    namespace: str
    throttle_type: str
    read_iops: int
    write_iops: int
    read_bps: int
    write_bps: int
    duration: int
    mount_path: str
    image: str


class StorageThrottleScenarioPlugin(AbstractScenarioPlugin):
    """Chaos scenario that throttles I/O on PVC-backed volumes via Linux cgroups (v1/v2)."""

    DEFAULT_IMAGE = "quay.io/krkn-chaos/krkn:tools"
    _V1_BLKIO_FILES = [
        "blkio.throttle.read_bps_device",
        "blkio.throttle.write_bps_device",
        "blkio.throttle.read_iops_device",
        "blkio.throttle.write_iops_device",
    ]

    def __init__(self, scenario_type: str = None):
        super().__init__(scenario_type="storage_throttle_scenarios")

    # ------------------------------------------------------------------
    # Config parsing
    # ------------------------------------------------------------------

    def _parse_scenario_config(
        self, scenario: str
    ) -> Optional[ThrottleParams]:
        """Parse and validate the scenario YAML file.

        Returns a ThrottleParams on success or None on validation failure
        (errors are logged).
        """
        with open(scenario, "r") as f:
            config_yaml = yaml.safe_load(f)

        scenario_config = config_yaml["storage_throttle_scenario"]
        pvc_name = get_yaml_item_value(scenario_config, "pvc_name", "")
        pod_name = get_yaml_item_value(scenario_config, "pod_name", "")
        namespace = get_yaml_item_value(scenario_config, "namespace", "")
        throttle_type = get_yaml_item_value(
            scenario_config, "throttle_type", "bandwidth"
        )
        try:
            read_iops = int(
                get_yaml_item_value(scenario_config, "read_iops", 100)
            )
            write_iops = int(
                get_yaml_item_value(scenario_config, "write_iops", 50)
            )
            read_bps = parse_byte_value(
                get_yaml_item_value(scenario_config, "read_bps", 1048576)
            )
            write_bps = parse_byte_value(
                get_yaml_item_value(scenario_config, "write_bps", 524288)
            )
            duration = parse_duration_value(
                get_yaml_item_value(scenario_config, "duration", 60)
            )
        except (ValueError, TypeError) as exc:
            logging.error("Invalid numeric config value: %s", exc)
            return None
        mount_path = get_yaml_item_value(
            scenario_config, "mount_path", ""
        )
        image = get_yaml_item_value(
            scenario_config, "image", self.DEFAULT_IMAGE
        )

        if not namespace:
            logging.error("You must specify the namespace")
            return None
        if not pvc_name and not pod_name:
            logging.error("You must specify pvc_name or pod_name")
            return None
        if throttle_type not in ("iops", "bandwidth", "both"):
            logging.error(
                "throttle_type must be 'iops', 'bandwidth', or 'both', "
                "got '%s'" % throttle_type
            )
            return None
        if mount_path and not validate_mount_path(str(mount_path)):
            logging.error(
                "mount_path contains invalid characters or format: %r. "
                "Use an absolute path with only letters, digits, "
                "._/- (e.g. /data)" % mount_path
            )
            return None
        for name, val in [
            ("read_iops", read_iops), ("write_iops", write_iops),
            ("read_bps", read_bps), ("write_bps", write_bps),
            ("duration", duration),
        ]:
            if val <= 0:
                logging.error(
                    "%s must be a positive value, got %d" % (name, val)
                )
                return None

        return ThrottleParams(
            pvc_name=pvc_name,
            pod_name=pod_name,
            namespace=namespace,
            throttle_type=throttle_type,
            read_iops=read_iops,
            write_iops=write_iops,
            read_bps=read_bps,
            write_bps=write_bps,
            duration=duration,
            mount_path=mount_path,
            image=image,
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            params = self._parse_scenario_config(scenario)
            if params is None:
                return 1

            lib_k8s = lib_telemetry.get_lib_kubernetes()

            pod_name = self._resolve_pod_name(
                lib_k8s, params.pvc_name, params.pod_name, params.namespace
            )
            if not pod_name:
                return 1

            pod = lib_k8s.get_pod_info(
                name=pod_name, namespace=params.namespace
            )
            if pod is None:
                logging.error(
                    "Pod '%s' doesn't exist in namespace '%s'"
                    % (pod_name, params.namespace)
                )
                return 1

            container_name, vol_mount_path = self._find_pvc_mount(
                pod, params.mount_path, params.pvc_name
            )
            if not container_name:
                logging.error(
                    "Pod '%s' has no PVC volume mount" % pod_name
                )
                return 1
            if not validate_mount_path(vol_mount_path):
                logging.error(
                    "Resolved mount path is invalid or unsafe: %r"
                    % vol_mount_path
                )
                return 1

            logging.info(
                "Target: pod=%s container=%s mount=%s namespace=%s"
                % (pod_name, container_name, vol_mount_path, params.namespace)
            )

            maj_min = self._get_device_maj_min(
                lib_k8s, pod_name, params.namespace,
                container_name, vol_mount_path,
            )
            if not maj_min:
                logging.error(
                    "Could not determine major:minor for mount %s"
                    % vol_mount_path
                )
                return 1
            if not validate_maj_min(maj_min):
                logging.error(
                    "Device major:minor from mountinfo is invalid: %r"
                    % maj_min
                )
                return 1
            logging.info("Block device major:minor = %s" % maj_min)

            node_name = pod.nodeName
            if not node_name:
                logging.error(
                    "Pod '%s' has no nodeName yet (still pending?)"
                    % pod_name
                )
                return 1
            logging.info("Target node: %s" % node_name)

            container_id = self._get_container_id(pod, container_name)
            if not container_id:
                logging.error(
                    "Could not get container ID for %s" % pod_name
                )
                return 1
            logging.info("Container ID: %s" % container_id)

            # Deploy privileged pod — all subsequent work is guarded by
            # try/finally so the pod is always cleaned up.
            priv_pod_name = lib_k8s.deploy_io_throttle_pod(
                node_name=node_name,
                image=params.image,
                namespace=params.namespace,
            )
            logging.info("Privileged pod deployed: %s" % priv_pod_name)

            throttle_applied = False
            cgroup_path = ""
            cgroup_version = "v1"
            try:
                cgroup_version = self._detect_cgroup_version(
                    lib_k8s, priv_pod_name, params.namespace
                )
                logging.info("Detected cgroups %s" % cgroup_version)

                cgroup_path = self._find_host_cgroup_path(
                    lib_k8s, priv_pod_name, container_id,
                    cgroup_version, params.namespace,
                )
                if not cgroup_path:
                    logging.error(
                        "Could not find host cgroup path for container %s"
                        % container_id
                    )
                    return 1
                if not validate_cgroup_path(cgroup_path):
                    logging.error(
                        "Discovered cgroup path is invalid or unsafe: %r"
                        % cgroup_path
                    )
                    return 1
                logging.info("Host cgroup path: %s" % cgroup_path)

                self._register_rollback(
                    priv_pod_name, maj_min, cgroup_path,
                    cgroup_version, params.namespace,
                )

                self._apply_throttle(
                    lib_k8s, priv_pod_name, cgroup_path,
                    cgroup_version, maj_min, params, params.namespace,
                )
                throttle_applied = True
                logging.info(
                    "I/O throttle applied (type=%s) for %ds"
                    % (params.throttle_type, params.duration)
                )

                self._wait_with_progress(params.duration)

                self._remove_throttle(
                    lib_k8s, priv_pod_name, cgroup_path,
                    cgroup_version, maj_min, params.namespace,
                )
                throttle_applied = False
                logging.info("I/O throttle removed")
            finally:
                if throttle_applied:
                    try:
                        self._remove_throttle(
                            lib_k8s, priv_pod_name, cgroup_path,
                            cgroup_version, maj_min, params.namespace,
                        )
                        logging.info("I/O throttle removed during cleanup")
                    except Exception as e:
                        logging.warning(
                            "Best-effort throttle removal failed: %s. "
                            "I/O limits may persist on device %s at "
                            "cgroup path %s (%s). To clear manually, "
                            "run a privileged pod on the node and reset "
                            "the cgroup: %s"
                            % (
                                e, maj_min, cgroup_path, cgroup_version,
                                "echo '%s rbps=max wbps=max riops=max wiops=max'"
                                " > /sys/fs/cgroup%s/io.max" % (maj_min, cgroup_path)
                                if cgroup_version == "v2"
                                else "echo '%s 0' > /sys/fs/cgroup/blkio%s/"
                                     "<blkio.throttle.*_device>" % (maj_min, cgroup_path),
                            )
                        )
                self._cleanup_privileged_pod(
                    lib_k8s, priv_pod_name, params.namespace
                )
                logging.info("Privileged pod cleaned up")

        except Exception as e:
            logging.error("Stack trace:\n%s", traceback.format_exc())
            logging.error(
                "StorageThrottleScenarioPlugin exception: %s" % e
            )
            return 1
        else:
            return 0

    def get_scenario_types(self) -> list[str]:
        return ["storage_throttle_scenarios"]

    def _resolve_pod_name(
        self,
        lib_k8s: KrknKubernetes,
        pvc_name: str,
        pod_name: str,
        namespace: str,
    ) -> str:
        if pvc_name:
            if pod_name:
                logging.info(
                    "pod_name '%s' will be overridden by pod from PVC" % pod_name
                )
            pvc = lib_k8s.get_pvc_info(pvc_name, namespace)
            if pvc is None or not pvc.podNames:
                logging.error(
                    "No pod associated with PVC '%s' in namespace '%s'"
                    % (pvc_name, namespace)
                )
                return ""
            pod_name = random.choice(pvc.podNames)  # nosec
            logging.info("Resolved pod from PVC: %s" % pod_name)
        return pod_name

    @staticmethod
    def _find_pvc_mount(pod, mount_path: str, pvc_name: str = ""):
        """Find the container name and mount path for a PVC volume.

        When *pvc_name* is set, only volumes backed by that PVC are considered.
        """
        for volume in pod.volumes:
            if volume.pvcName is None:
                continue
            if pvc_name and volume.pvcName != pvc_name:
                continue
            vol_name = volume.name
            for container in pod.containers:
                for vol_mount in container.volumeMounts:
                    if vol_mount.name == vol_name:
                        if mount_path and vol_mount.mountPath != mount_path:
                            continue
                        return container.name, vol_mount.mountPath
        return None, None

    @staticmethod
    def _get_device_maj_min(
        lib_k8s: KrknKubernetes,
        pod_name: str,
        namespace: str,
        container_name: str,
        mount_path: str,
    ) -> str:
        """Extract device major:minor from /proc/self/mountinfo."""
        if not _validate_mount_path(mount_path):
            logging.error("Refusing to exec with invalid mount_path: %r", mount_path)
            return ""
        cmd = "grep -F ' %s ' /proc/self/mountinfo | awk '{print $3}' | head -1"
        output = lib_k8s.exec_cmd_in_pod(
            [cmd % mount_path], pod_name, namespace, container_name
        )
        if output:
            return output.strip()
        return ""

    @staticmethod
    def _get_container_id(pod, container_name: str) -> str:
        """Get the container ID from krkn_lib Pod.containers, stripping runtime prefix."""
        if pod is None:
            return ""
        for c in pod.containers:
            if c.name == container_name:
                cid = c.containerId or ""
                if not cid:
                    return ""
                if "://" in cid:
                    cid = cid.split("://", 1)[1]
                if not validate_container_id(cid):
                    logging.warning("Container ID is not valid hex: %r", cid)
                    return ""
                return cid
        return ""

    def _cleanup_privileged_pod(
        self, lib_k8s: KrknKubernetes, priv_pod_name: str, namespace: str
    ):
        """Delete the privileged pod."""
        try:
            lib_k8s.delete_pod(priv_pod_name, namespace)
        except Exception as e:
            logging.warning("Failed to delete privileged pod %s: %s" % (priv_pod_name, e))

    def _detect_cgroup_version(
        self, lib_k8s: KrknKubernetes, priv_pod_name: str, namespace: str
    ) -> str:
        """Detect whether the node uses cgroups v1 or v2."""
        output = lib_k8s.exec_cmd_in_pod(
            ["/host", "stat", "-f", "-c", "%T", "/sys/fs/cgroup"],
            priv_pod_name,
            namespace,
            base_command="chroot",
        )
        if output and "cgroup2fs" in output:
            return "v2"
        return "v1"

    def _find_host_cgroup_path(
        self,
        lib_k8s: KrknKubernetes,
        priv_pod_name: str,
        container_id: str,
        cgroup_version: str,
        namespace: str,
    ) -> str:
        """
        Find the real cgroup path on the host for the target container.
        Excludes conmon (CRI-O container monitor) paths.
        """
        short_id = container_id[:12]

        if cgroup_version == "v2":
            search_base = "/sys/fs/cgroup"
            strip_prefix = "/sys/fs/cgroup"
        else:
            search_base = "/sys/fs/cgroup/blkio"
            strip_prefix = "/sys/fs/cgroup/blkio"

        # Search for the container's scope directory, excluding conmon
        find_cmd = (
            "find %s -name '*.scope' -path '*%s*' ! -name '*conmon*' 2>/dev/null | head -1"
            % (search_base, short_id)
        )
        output = lib_k8s.exec_cmd_in_pod(
            ["/host", "bash", "-c", find_cmd],
            priv_pod_name,
            namespace,
            base_command="chroot",
        )
        if output and output.strip():
            return output.strip().replace(strip_prefix, "", 1)

        # Fallback: search directories (containerd doesn't use .scope files)
        find_cmd = (
            "find %s -type d -name '*%s*' ! -name '*conmon*' 2>/dev/null | head -1"
            % (search_base, short_id)
        )
        output = lib_k8s.exec_cmd_in_pod(
            ["/host", "bash", "-c", find_cmd],
            priv_pod_name,
            namespace,
            base_command="chroot",
        )
        if output and output.strip():
            return output.strip().replace(strip_prefix, "", 1)

        return ""

    # ------------------------------------------------------------------
    # Rollback registration
    # ------------------------------------------------------------------

    def _register_rollback(
        self,
        priv_pod_name: str,
        maj_min: str,
        cgroup_path: str,
        cgroup_version: str,
        namespace: str,
    ):
        """Register rollback data so throttle can be undone on failure."""
        rollback_data = {
            "priv_pod_name": priv_pod_name,
            "maj_min": maj_min,
            "cgroup_path": cgroup_path,
            "cgroup_version": cgroup_version,
        }
        encoded_data = base64.b64encode(
            json.dumps(rollback_data).encode("utf-8")
        ).decode("utf-8")
        self.rollback_handler.set_rollback_callable(
            self.rollback_throttle,
            RollbackContent(
                namespace=namespace,
                resource_identifier=encoded_data,
            ),
        )

    # ------------------------------------------------------------------
    # Duration hold
    # ------------------------------------------------------------------

    @staticmethod
    def _wait_with_progress(duration: int, interval: int = 30):
        """Sleep for *duration* seconds, logging progress every *interval*."""
        elapsed = 0
        while elapsed < duration:
            chunk = min(interval, duration - elapsed)
            time.sleep(chunk)
            elapsed += chunk
            logging.info(
                "Throttle active: %d/%ds elapsed" % (elapsed, duration)
            )

    # ------------------------------------------------------------------
    # Throttle apply / remove
    # ------------------------------------------------------------------

    def _apply_throttle(
        self,
        lib_k8s: KrknKubernetes,
        priv_pod_name: str,
        cgroup_path: str,
        cgroup_version: str,
        maj_min: str,
        params: ThrottleParams,
        namespace: str,
    ):
        """Apply I/O throttle via cgroup writes."""
        if cgroup_version == "v2":
            self._apply_throttle_v2(
                lib_k8s, priv_pod_name, cgroup_path, maj_min,
                params, namespace,
            )
        else:
            self._apply_throttle_v1(
                lib_k8s, priv_pod_name, cgroup_path, maj_min,
                params, namespace,
            )

    def _apply_throttle_v2(
        self, lib_k8s, priv_pod_name, cgroup_path, maj_min,
        params: ThrottleParams, namespace,
    ):
        io_max_path = "/sys/fs/cgroup%s/io.max" % cgroup_path

        if params.throttle_type == "iops":
            value = "%s riops=%d wiops=%d" % (
                maj_min, params.read_iops, params.write_iops,
            )
        elif params.throttle_type == "bandwidth":
            value = "%s rbps=%d wbps=%d" % (
                maj_min, params.read_bps, params.write_bps,
            )
        else:  # both
            value = "%s rbps=%d wbps=%d riops=%d wiops=%d" % (
                maj_min, params.read_bps, params.write_bps,
                params.read_iops, params.write_iops,
            )

        logging.info("Setting io.max: %s" % value)
        self._chroot_exec(
            lib_k8s, priv_pod_name,
            "echo '%s' > %s" % (value, io_max_path),
            namespace,
        )

        result = self._chroot_exec(
            lib_k8s, priv_pod_name, "cat %s" % io_max_path, namespace
        )
        logging.info("Verified io.max: %s" % result)
        if result and maj_min not in result:
            logging.warning(
                "Throttle may not have been applied; io.max readback: %s"
                % result
            )

    def _apply_throttle_v1(
        self, lib_k8s, priv_pod_name, cgroup_path, maj_min,
        params: ThrottleParams, namespace,
    ):
        blkio_path = "/sys/fs/cgroup/blkio%s" % cgroup_path

        if params.throttle_type in ("iops", "both"):
            self._chroot_exec(
                lib_k8s, priv_pod_name,
                "echo '%s %d' > %s/blkio.throttle.read_iops_device"
                % (maj_min, params.read_iops, blkio_path),
                namespace,
            )
            self._chroot_exec(
                lib_k8s, priv_pod_name,
                "echo '%s %d' > %s/blkio.throttle.write_iops_device"
                % (maj_min, params.write_iops, blkio_path),
                namespace,
            )

        if params.throttle_type in ("bandwidth", "both"):
            self._chroot_exec(
                lib_k8s, priv_pod_name,
                "echo '%s %d' > %s/blkio.throttle.read_bps_device"
                % (maj_min, params.read_bps, blkio_path),
                namespace,
            )
            self._chroot_exec(
                lib_k8s, priv_pod_name,
                "echo '%s %d' > %s/blkio.throttle.write_bps_device"
                % (maj_min, params.write_bps, blkio_path),
                namespace,
            )

        logging.info("Verified blkio settings:")
        for f in self._V1_BLKIO_FILES:
            result = self._chroot_exec(
                lib_k8s, priv_pod_name,
                "cat %s/%s 2>/dev/null" % (blkio_path, f),
                namespace,
            )
            if result:
                logging.info("  %s: %s" % (f, result.strip()))
                if maj_min not in result:
                    logging.warning(
                        "Throttle may not be active for %s; readback: %s"
                        % (f, result.strip())
                    )

    @staticmethod
    def _remove_throttle(
        lib_k8s: KrknKubernetes,
        priv_pod_name: str,
        cgroup_path: str,
        cgroup_version: str,
        maj_min: str,
        namespace: str,
    ):
        """Remove the I/O throttle by resetting cgroup values."""
        if cgroup_version == "v2":
            io_max_path = "/sys/fs/cgroup%s/io.max" % cgroup_path
            reset_value = "%s rbps=max wbps=max riops=max wiops=max" % maj_min
            StorageThrottleScenarioPlugin._chroot_exec(
                lib_k8s, priv_pod_name,
                "echo '%s' > %s" % (reset_value, io_max_path),
                namespace,
            )
        else:
            blkio_path = "/sys/fs/cgroup/blkio%s" % cgroup_path
            for f in StorageThrottleScenarioPlugin._V1_BLKIO_FILES:
                StorageThrottleScenarioPlugin._chroot_exec(
                    lib_k8s, priv_pod_name,
                    "echo '%s 0' > %s/%s" % (maj_min, blkio_path, f),
                    namespace,
                )

    @staticmethod
    def _chroot_exec(
        lib_k8s: KrknKubernetes, priv_pod_name: str, cmd: str,
        namespace: str,
    ) -> str:
        """Execute a command inside the privileged pod via chroot /host."""
        return lib_k8s.exec_cmd_in_pod(
            ["/host", "bash", "-c", cmd],
            priv_pod_name,
            namespace,
            base_command="chroot",
        )

    @staticmethod
    def rollback_throttle(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        """
        Rollback: remove any applied throttle and delete the privileged pod.

        :param rollback_content: Contains namespace and encoded rollback data.
        :param lib_telemetry: KrknTelemetryOpenshift instance.
        """
        try:
            namespace = rollback_content.namespace
            decoded = base64.b64decode(
                rollback_content.resource_identifier.encode("utf-8")
            ).decode("utf-8")
            data = json.loads(decoded)
            priv_pod_name = data["priv_pod_name"]
            maj_min = data["maj_min"]

            lib_k8s = lib_telemetry.get_lib_kubernetes()
            logging.info(
                "Rolling back storage throttle: removing limits and "
                "deleting pod %s" % priv_pod_name
            )

            if not _validate_maj_min(maj_min):
                logging.warning(
                    "Invalid maj_min during rollback, skipping throttle removal"
                )
            else:
                cgroup_path = data.get("cgroup_path")
                cgroup_version = data.get("cgroup_version")
                if cgroup_path and cgroup_version in ("v1", "v2"):
                    try:
                        StorageThrottleScenarioPlugin._remove_throttle(
                            lib_k8s,
                            priv_pod_name,
                            cgroup_path,
                            cgroup_version,
                            maj_min,
                            namespace,
                        )
                        logging.info("Throttle limits removed during rollback")
                    except Exception as rem_exc:
                        logging.warning(
                            "Rollback throttle removal failed: %s" % rem_exc
                        )
                else:
                    logging.warning(
                        "Rollback data missing cgroup_path or cgroup_version, "
                        "cannot remove throttle"
                    )

            lib_k8s.delete_pod(priv_pod_name, namespace)
            logging.info("Privileged pod deleted during rollback")

        except Exception as e:
            logging.error("Failed to rollback storage throttle: %s" % e)
