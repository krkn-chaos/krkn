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
"""
Object State Health Check Plugin

This plugin provides health checking for Kubernetes object states by monitoring
conditions on any Kubernetes resource type (Pods, Deployments, StatefulSets, etc.).

Example configuration in config.yaml:
    object_state_checks:
        interval: 5
        run_during: ["pre", "during", "post"]
        exit_on_failure: False
        config:
            - name: "etcd-pods-ready"
              kind: "Pod"
              object_name: "etcd-.*"        # Regex pattern
              namespace: "kube-system"
              label_selector: ""             # Optional label selector
              condition:
                  type: "Ready"
                  status: "True"

            - name: "deployment-available"
              kind: "Deployment"
              object_name: "my-app"
              namespace: "default"
              condition:
                  type: "Available"
                  status: "True"
"""

import logging
import queue
import re
import time
from datetime import datetime
from typing import Any, Optional

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry.models import ObjectStateCheck

from krkn.health_checks.abstract_health_check_plugin import AbstractHealthCheckPlugin


class ObjectStateHealthCheckPlugin(AbstractHealthCheckPlugin):
    """
    Kubernetes object state health check plugin that monitors object conditions.

    This plugin can monitor any Kubernetes resource type (Pod, Deployment, StatefulSet,
    DaemonSet, etc.) and check specific conditions on those resources.
    """

    CLUSTER_SCOPED_KINDS = {"node", "persistentvolume"}

    def __init__(
        self,
        health_check_type: str = "object_state_health_check",
        iterations: int = 1,
        krkn_lib: KrknKubernetes = None,
        **kwargs
    ):
        """
        Initializes the object state health check plugin.

        :param health_check_type: the health check type identifier
        :param iterations: the number of chaos iterations to monitor
        :param krkn_lib: KrknKubernetes client instance
        :param kwargs: additional keyword arguments
        """
        super().__init__(health_check_type)
        self.iterations = iterations
        self.current_iterations = 0
        self.krkn_lib = krkn_lib

    def get_health_check_types(self) -> list[str]:
        """
        Returns the health check types this plugin handles.

        :return: list of health check type identifiers
        """
        return ["object_state_health_check", "k8s_object_health_check"]

    def get_config_key(self) -> str:
        """
        Returns the top-level config.yaml key this plugin reads from.

        :return: config key string
        """
        return "object_state_checks"

    def _is_check_runnable(self, check: Any) -> bool:
        """
        Determines if a check configuration is runnable.

        A check is runnable if it is a dictionary and either has a non-empty namespace
        or targets a supported cluster-scoped resource kind.
        """
        if not isinstance(check, dict):
            return False
        kind = str(check.get("kind", "")).strip().lower()
        if kind in self.CLUSTER_SCOPED_KINDS:
            return True
        namespace = check.get("namespace", "")
        return bool(isinstance(namespace, str) and namespace.strip())

    def is_configured(self, config: dict[str, Any]) -> bool:
        """Run when at least one object-state check is runnable."""
        checks = config.get("config", [])
        return any(self._is_check_runnable(check) for check in checks)

    def increment_iterations(self) -> None:
        """
        Increments the current iteration counter.

        :return: None
        """
        self.current_iterations += 1

    def _get_objects(
        self,
        kind: str,
        namespace: str,
        object_name: Optional[str] = None,
        label_selector: Optional[str] = None
    ) -> list[dict]:
        """
        Get Kubernetes objects matching the criteria.

        :param kind: Kubernetes resource kind (e.g., "Pod", "Deployment")
        :param namespace: Namespace to search in
        :param object_name: Optional name or regex pattern
        :param label_selector: Optional label selector
        :return: List of matching objects (as dictionaries)
        """
        try:
            # Map kind to appropriate API call
            kind_lower = kind.lower()

            # Use krkn_lib helper methods where available
            if kind_lower == "pod":
                if label_selector:
                    raw_objects = self.krkn_lib.list_pods(namespace, label_selector)
                else:
                    raw_objects = self.krkn_lib.list_pods(namespace)
            elif kind_lower == "deployment":
                raw_objects = self.krkn_lib.list_deployments(namespace)
            elif kind_lower == "statefulset":
                raw_objects = self.krkn_lib.list_statefulsets(namespace)
            elif kind_lower == "daemonset":
                raw_objects = self.krkn_lib.list_daemonsets(namespace)
            elif kind_lower == "replicaset":
                raw_objects = self.krkn_lib.list_replicasets(namespace)

            # Direct Kubernetes API calls for additional resource types
            elif kind_lower == "service":
                result = self.krkn_lib.cli.list_namespaced_service(namespace, label_selector=label_selector)
                raw_objects = result.items if hasattr(result, 'items') else []
            elif kind_lower == "persistentvolumeclaim":
                result = self.krkn_lib.cli.list_namespaced_persistent_volume_claim(namespace, label_selector=label_selector)
                raw_objects = result.items if hasattr(result, 'items') else []
            elif kind_lower == "job":
                result = self.krkn_lib.batch_cli.list_namespaced_job(namespace, label_selector=label_selector)
                raw_objects = result.items if hasattr(result, 'items') else []
            elif kind_lower == "cronjob":
                result = self.krkn_lib.batch_cli.list_namespaced_cron_job(namespace, label_selector=label_selector)
                raw_objects = result.items if hasattr(result, 'items') else []

            # Cluster-scoped resources
            elif kind_lower == "node":
                raw_objects = self.krkn_lib.list_nodes(label_selector)
            elif kind_lower == "persistentvolume":
                result = self.krkn_lib.cli.list_persistent_volume(label_selector=label_selector)
                raw_objects = result.items if hasattr(result, 'items') else []

            else:
                # For other kinds, try to get via dynamic client
                logging.warning(
                    f"Kind '{kind}' may not be fully supported. "
                    f"Attempting to retrieve with generic API call."
                )
                raw_objects = []

            # Handle case where API returns strings (names) instead of objects
            objects = []
            if raw_objects:
                for item in raw_objects:
                    if isinstance(item, str):
                        # API returned just names, need to get full object
                        obj = self._get_object_by_name(kind, namespace, item)
                        if obj:
                            objects.append(obj)
                    elif isinstance(item, dict):
                        # Already a full object
                        objects.append(item)
                    else:
                        # Kubernetes API object - convert to dict
                        try:
                            obj_dict = self.krkn_lib.api_client.sanitize_for_serialization(item)
                            objects.append(obj_dict)
                        except AttributeError:
                            # If sanitize_for_serialization fails, try vars() for dataclasses
                            try:
                                obj_dict = vars(item)
                                objects.append(obj_dict)
                            except (TypeError, AttributeError) as e:
                                logging.warning(
                                    f"Could not convert {type(item)} to dict for {kind} in {namespace}: {e}"
                                )

            # Filter by name pattern if provided
            if object_name and objects:
                pattern = re.compile(object_name)
                filtered_objects = []
                for obj in objects:
                    # Ensure obj is a dict before trying to access it
                    if not isinstance(obj, dict):
                        logging.warning(f"Skipping non-dict object during filtering: {type(obj)}")
                        continue
                    obj_name = obj.get("metadata", {}).get("name", "")
                    if pattern.match(obj_name):
                        filtered_objects.append(obj)
                objects = filtered_objects

            return objects if objects else []

        except Exception as e:
            ns_msg = f" in namespace {namespace}" if namespace else ""
            logging.error(
                f"Error getting {kind} objects{ns_msg}: {e}"
            )
            return []

    def _get_object_by_name(
        self,
        kind: str,
        namespace: str,
        name: str
    ) -> Optional[dict]:
        """
        Get a single Kubernetes object by name.

        Delegates to krkn_lib's universal get_object_by_name() helper method.

        :param kind: Kubernetes resource kind
        :param namespace: Namespace
        :param name: Object name
        :return: Object dictionary or None
        """
        try:
            return self.krkn_lib.get_object_by_name(kind, name, namespace)
        except Exception as e:
            ns_msg = f" {namespace}/{name}" if namespace else f" {name}"
            logging.debug(f"Error getting {kind}{ns_msg}: {e}")
            return None

    def _check_object_condition(
        self,
        obj: dict,
        condition_type: str,
        condition_status: str
    ) -> tuple[bool, str]:
        """
        Check if an object has the specified condition.

        :param obj: Kubernetes object (dict or Kubernetes API object)
        :param condition_type: Condition type to check (e.g., "Ready", "Available")
        :param condition_status: Expected status (e.g., "True", "False")
        :return: Tuple of (passed, message)
        """
        # Convert Kubernetes API object to dict if needed
        if not isinstance(obj, dict):
            try:
                # Try Kubernetes client serialization first
                obj = self.krkn_lib.api_client.sanitize_for_serialization(obj)
            except AttributeError:
                # If that fails, try converting with vars() for dataclasses/simple objects
                try:
                    obj = vars(obj)
                except (TypeError, AttributeError) as e:
                    logging.error(f"Failed to convert object to dict: {e}")
                    return False, f"Failed to convert object to dict: {e}"

        kind = obj.get("kind", "Unknown")
        obj_name = obj.get("metadata", {}).get("name", "unknown")
        namespace = obj.get("metadata", {}).get("namespace")
        obj_id = f"{kind} {namespace}/{obj_name}" if namespace else f"{kind} {obj_name}"

        # 1. Check conditions list (Pod, Node, Deployment, Job, etc.)
        conditions = obj.get("status", {}).get("conditions", [])
        if conditions:
            for condition in conditions:
                if condition.get("type") == condition_type:
                    actual_status = condition.get("status", "Unknown")
                    if actual_status == condition_status:
                        return True, f"{obj_id} condition {condition_type}={condition_status}"
                    else:
                        reason = condition.get("reason", "")
                        message = condition.get("message", "")
                        return False, (
                            f"{obj_id} condition {condition_type}={actual_status} "
                            f"(expected {condition_status}). Reason: {reason}. Message: {message}"
                        )

        # 2. Check status.phase (for resources like PersistentVolume that use phase instead of conditions)
        status_obj = obj.get("status", {})
        phase = status_obj.get("phase")
        if phase:
            if condition_type.lower() == "phase":
                if str(phase).lower() == str(condition_status).lower():
                    return True, f"{obj_id} phase={phase}"
                return False, f"{obj_id} phase={phase} (expected {condition_status})"
            elif condition_type.lower() == str(phase).lower():
                if str(condition_status).lower() in ("true", "yes", "1"):
                    return True, f"{obj_id} phase={phase}"
                return False, f"{obj_id} phase={phase} (expected {condition_status})"

        if not conditions and not phase:
            return False, f"{obj_id} has no conditions or phase"

        # Condition type not found
        available = []
        if conditions:
            available.extend([c.get("type") for c in conditions])
        if phase:
            available.append(f"Phase={phase}")
        return False, (
            f"{obj_id} does not have condition type '{condition_type}'. "
            f"Available: {available}"
        )

    def _check_single_config(self, check_config: dict) -> dict[str, Any]:
        """
        Check a single object state configuration.

        :param check_config: Configuration for one check
        :return: Dictionary with check results
        """
        check_name = check_config.get("name", "unnamed-check")
        kind = check_config.get("kind", "")
        object_name = check_config.get("object_name", None)
        label_selector = check_config.get("label_selector", None)
        condition = check_config.get("condition", {})
        condition_type = condition.get("type", "Ready")
        condition_status = condition.get("status", "True")

        is_cluster_scoped = str(kind).strip().lower() in self.CLUSTER_SCOPED_KINDS
        if is_cluster_scoped:
            namespace = ""
        else:
            raw_namespace = check_config.get("namespace")
            namespace = raw_namespace if raw_namespace is not None else "default"

        if not kind:
            return {
                "check_name": check_name,
                "passed": False,
                "message": "No 'kind' specified in configuration"
            }

        if not self._is_check_runnable(check_config):
            return {
                "check_name": check_name,
                "passed": True,
                "skipped": True,
                "message": "Namespace is not specified, skipping object state check"
            }

        # Get matching objects
        objects = self._get_objects(kind, namespace, object_name, label_selector)

        if not objects:
            ns_msg = f" in namespace {namespace}" if namespace else ""
            return {
                "check_name": check_name,
                "passed": False,
                "message": f"No {kind} objects found matching criteria{ns_msg}"
            }

        # Check condition on all matching objects
        # Requires ALL objects to pass - if ANY object fails, the check fails
        all_passed = True
        objects_failed = 0
        failed_objects = []

        for obj in objects:
            passed, message = self._check_object_condition(obj, condition_type, condition_status)
            if not passed:
                all_passed = False  # If ANY object fails, overall check fails
                objects_failed += 1
                # Extract namespace/name from the object for failed objects list
                if isinstance(obj, dict):
                    obj_name = obj.get("metadata", {}).get("name", "unknown")
                    obj_namespace = obj.get("metadata", {}).get("namespace", "")
                    if obj_namespace:
                        failed_objects.append(f"{obj_namespace}/{obj_name}")
                    else:
                        failed_objects.append(obj_name)

        # Message only contains names of failed objects
        message = "; ".join(failed_objects) if failed_objects else "All objects passed"

        return {
            "check_name": check_name,
            "passed": all_passed,  # True only if ALL objects passed
            "objects_checked": len(objects),
            "objects_failed": objects_failed,
            "message": message
        }

    def run_once(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue = None,
        phase: str = None
    ) -> dict[str, Any]:
        """
        Runs a one-time object state health check for all configured checks.

        When telemetry_queue is provided, creates ObjectStateCheck telemetry records
        with the specified phase for each check configuration.

        :param config: the health check configuration dictionary
        :param telemetry_queue: optional queue to put telemetry data for collection
        :param phase: optional phase indicator ("pre", "post"); defaults to None
        :return: dictionary with results:
                 {
                   "passed": bool,
                   "failures": list of failure details,
                   "details": dict with per-check status
                 }
        """
        if not config or not config.get("config"):
            logging.debug("Object state health check config is not defined, skipping one-time check")
            return {"passed": True, "failures": [], "details": {}}

        run_during = config.get("run_during")
        if (
            (isinstance(run_during, str) and not run_during.strip())
            or (isinstance(run_during, list) and not run_during)
        ):
            logging.debug("Object state health check run_during is blank, skipping one-time check")
            return {"passed": True, "failures": [], "details": {}}

        failures = []
        details = {}
        only_failures = config.get("only_failures", False)

        for check_config in config.get("config", []):
            if not self._is_check_runnable(check_config):
                if isinstance(check_config, dict):
                    logging.debug(
                        "Object state check '%s' has no namespace and is not cluster-scoped, skipping",
                        check_config.get("name", "unnamed-check")
                    )
                continue

            kind = check_config.get("kind", "")
            is_cluster_scoped = str(kind).strip().lower() in self.CLUSTER_SCOPED_KINDS

            result = self._check_single_config(check_config)
            check_name = result["check_name"]
            details[check_name] = result

            # Create telemetry if queue provided
            # Only include if: not only_failures OR check failed
            if telemetry_queue is not None and (not only_failures or not result["passed"]):
                start_dt = datetime.now()
                cfg = check_config
                condition = cfg.get("condition", {})

                telemetry_record = {
                    "check_name": check_name,
                    "kind": cfg.get("kind", ""),
                    "namespace": "" if is_cluster_scoped else cfg.get("namespace", ""),
                    "object_name": cfg.get("object_name", ""),
                    "condition_type": condition.get("type", ""),
                    "condition_status": condition.get("status", ""),
                    "passed": result["passed"],
                    "objects_checked": result.get("objects_checked", 0),
                    "objects_failed": result.get("objects_failed", 0),
                    "start_timestamp": start_dt.isoformat(),
                    "end_timestamp": start_dt.isoformat(),  # Same time for instant checks
                    "duration": 0.0,  # Instant check
                    "message": result["message"],
                    "phase": phase if phase else "during"  # Default to "during" if not specified
                }
                telemetry_queue.put(ObjectStateCheck(telemetry_record))

            if not result["passed"]:
                failures.append({
                    "check_name": check_name,
                    "message": result["message"]
                })

        passed = len(failures) == 0
        return {
            "passed": passed,
            "failures": failures,
            "details": details
        }

    def run_health_check(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue,
    ) -> None:
        """
        Runs the object state health check monitoring loop.

        Continuously monitors the configured object states until the specified
        number of iterations is complete. Tracks status changes and collects
        telemetry data.

        :param config: the health check configuration dictionary
        :param telemetry_queue: a queue to put telemetry data for collection
        :return: None
        """
        if not config or not config.get("config"):
            logging.debug("Object state health check config is not defined, skipping")
            return

        run_during = config.get("run_during")
        if (
            (isinstance(run_during, str) and not run_during.strip())
            or (isinstance(run_during, list) and not run_during)
        ):
            logging.debug("Object state health check run_during is blank, skipping")
            return

        check_configs = [
            cfg for cfg in config.get("config", [])
            if self._is_check_runnable(cfg)
        ]
        if len(check_configs) != len(config.get("config", [])):
            logging.debug("Skipping object state checks that are not runnable")
        if not check_configs:
            return

        # Ensure all check configs have a consistent name to prevent KeyError on lookup
        for i, cfg in enumerate(check_configs):
            if not cfg.get("name"):
                cfg["name"] = f"check-{i}"

        health_check_telemetry = []
        health_check_tracker = {}
        interval = config.get("interval", 5)
        exit_on_failure = config.get("exit_on_failure", False)
        only_failures = config.get("only_failures", False)

        # Track current status for each check
        status_tracker = {
            cfg["name"]: True
            for cfg in check_configs
        }

        # Store check configs by name for telemetry
        check_configs_by_name = {
            cfg["name"]: cfg
            for cfg in check_configs
        }

        while self.current_iterations < self.iterations and not self._stop_event.is_set():
            for check_config in check_configs:
                check_name = check_config.get("name", "unnamed-check")

                result = self._check_single_config(check_config)

                if check_name not in health_check_tracker:
                    # First time seeing this check
                    start_timestamp = datetime.now()
                    health_check_tracker[check_name] = {
                        "passed": result["passed"],
                        "start_timestamp": start_timestamp,
                        "message": result["message"],
                        "objects_checked": result.get("objects_checked", 0),
                        "objects_failed": result.get("objects_failed", 0)
                    }
                    if not result["passed"]:
                        if status_tracker[check_name] != False:
                            status_tracker[check_name] = False
                        if exit_on_failure and self.ret_value == 0:
                            self.ret_value = 3
                else:
                    # Check if status changed
                    if result["passed"] != health_check_tracker[check_name]["passed"]:
                        end_timestamp = datetime.now()
                        start_timestamp = health_check_tracker[check_name]["start_timestamp"]
                        previous_passed = health_check_tracker[check_name]["passed"]
                        duration = (end_timestamp - start_timestamp).total_seconds()

                        # Get check config details for telemetry
                        cfg = check_configs_by_name.get(check_name, {})
                        condition = cfg.get("condition", {})

                        # Record the status change period
                        change_record = {
                            "check_name": check_name,
                            "kind": cfg.get("kind", ""),
                            "namespace": cfg.get("namespace", ""),
                            "object_name": cfg.get("object_name", ""),
                            "condition_type": condition.get("type", ""),
                            "condition_status": condition.get("status", ""),
                            "passed": previous_passed,
                            "objects_checked": health_check_tracker[check_name]["objects_checked"],
                            "objects_failed": health_check_tracker[check_name]["objects_failed"],
                            "start_timestamp": start_timestamp.isoformat(),
                            "end_timestamp": end_timestamp.isoformat(),
                            "duration": duration,
                            "message": health_check_tracker[check_name]["message"],
                            "phase": "during"
                        }

                        # Only include if: not only_failures OR check failed
                        if not only_failures or not previous_passed:
                            health_check_telemetry.append(ObjectStateCheck(change_record))

                        if status_tracker[check_name] != result["passed"]:
                            status_tracker[check_name] = result["passed"]

                        # Apply exit_on_failure if transitioning to failed
                        if not result["passed"] and exit_on_failure and self.ret_value == 0:
                            self.ret_value = 3

                        # Reset tracker with new status
                        del health_check_tracker[check_name]
                        health_check_tracker[check_name] = {
                            "passed": result["passed"],
                            "start_timestamp": end_timestamp,
                            "message": result["message"],
                            "objects_checked": result.get("objects_checked", 0),
                            "objects_failed": result.get("objects_failed", 0)
                        }

            time.sleep(interval)

        # Record final status for all tracked checks
        health_check_end_timestamp = datetime.now()
        for check_name in health_check_tracker.keys():
            duration = (
                health_check_end_timestamp
                - health_check_tracker[check_name]["start_timestamp"]
            ).total_seconds()

            # Get check config details for telemetry
            cfg = check_configs_by_name.get(check_name, {})
            condition = cfg.get("condition", {})

            final_record = {
                "check_name": check_name,
                "kind": cfg.get("kind", ""),
                "namespace": cfg.get("namespace", ""),
                "object_name": cfg.get("object_name", ""),
                "condition_type": condition.get("type", ""),
                "condition_status": condition.get("status", ""),
                "passed": health_check_tracker[check_name]["passed"],
                "objects_checked": health_check_tracker[check_name]["objects_checked"],
                "objects_failed": health_check_tracker[check_name]["objects_failed"],
                "start_timestamp": health_check_tracker[check_name][
                    "start_timestamp"
                ].isoformat(),
                "end_timestamp": health_check_end_timestamp.isoformat(),
                "duration": duration,
                "message": health_check_tracker[check_name]["message"],
                "phase": "during"
            }
            # Only include if: not only_failures OR check failed
            if not only_failures or not health_check_tracker[check_name]["passed"]:
                health_check_telemetry.append(ObjectStateCheck(final_record))

        # Put telemetry data in the queue
        telemetry_queue.put(health_check_telemetry)
