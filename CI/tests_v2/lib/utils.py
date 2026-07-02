"""
Shared helpers for CI/tests_v2 functional tests.
"""

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Union

import pytest
import yaml
from kubernetes.client import V1NetworkPolicy, V1NetworkPolicyList, V1Pod, V1PodList

logger = logging.getLogger(__name__)

# Per-scenario regex markers that prove the scenario actually executed its core logic.
# A scenario exiting rc=0 without one of these lines in its stdout/stderr is a silent
# no-op (e.g. a selector matched nothing) and the happy-path test should fail.
SCENARIO_EXECUTION_MARKERS = {
    "pod_disruption": r"Deleting pod |waiting up to .* seconds for pod recovery",
    "pod_error_scenarios": r"Deleting pod |waiting up to .* seconds for pod recovery",
    "application_outage": r"Creating the network policy|Deleting the network policy",
    "storage_throttle": r"Setting io\.max|Verified blkio settings|Privileged pod deployed",
    "namespace_deletion": r"Delete objects in selected namespace|Deleted all objects in namespace",
}

# nodeid -> {"scenario", "pattern", "verified"}; consumed by conftest to build the
# HTML report evidence line and the GitHub Actions execution-evidence summary table.
# Last-write-wins per nodeid so multi-run tests and reruns report their final state.
EXECUTION_EVIDENCE = {}


def _record_execution_evidence(scenario_name: str, pattern: str, verified: bool) -> None:
    """Record evidence result keyed by the current test nodeid (from PYTEST_CURRENT_TEST)."""
    nodeid = os.environ.get("PYTEST_CURRENT_TEST", "").split(" (")[0]
    if nodeid:
        EXECUTION_EVIDENCE[nodeid] = {
            "scenario": scenario_name,
            "pattern": pattern,
            "verified": verified,
        }


def _pods(pod_list: Union[V1PodList, List[V1Pod]]) -> List[V1Pod]:
    """Normalize V1PodList or list of V1Pod to list of V1Pod."""
    return pod_list.items if hasattr(pod_list, "items") else pod_list


def _policies(
    policy_list: Union[V1NetworkPolicyList, List[V1NetworkPolicy]],
) -> List[V1NetworkPolicy]:
    """Normalize V1NetworkPolicyList or list to list of V1NetworkPolicy."""
    return policy_list.items if hasattr(policy_list, "items") else policy_list


def scenario_dir(repo_root: Path, scenario_name: str) -> Path:
    """Return the path to a scenario folder under CI/tests_v2/scenarios/."""
    return repo_root / "CI" / "tests_v2" / "scenarios" / scenario_name


def load_scenario_base(
    repo_root: Path,
    scenario_name: str,
    filename: str = "scenario_base.yaml",
) -> Union[dict, list]:
    """
    Load and parse the scenario base YAML for a scenario.
    Returns dict or list depending on the YAML structure.
    """
    path = scenario_dir(repo_root, scenario_name) / filename
    text = path.read_text()
    data = yaml.safe_load(text)
    if data is None:
        raise ValueError(f"Empty or invalid YAML in {path}")
    return data


def patch_namespace_in_docs(docs: list, namespace: str) -> list:
    """Override metadata.namespace in each doc so create_from_yaml respects target namespace."""
    for doc in docs:
        if isinstance(doc, dict) and doc.get("metadata") is not None:
            doc["metadata"]["namespace"] = namespace
    return docs


def get_pods_list(k8s_core, namespace: str, label_selector: str) -> V1PodList:
    """Return V1PodList from the Kubernetes API."""
    return k8s_core.list_namespaced_pod(
        namespace=namespace,
        label_selector=label_selector,
    )


def get_pods_or_skip(
    k8s_core,
    namespace: str,
    label_selector: str,
    no_pods_reason: Optional[str] = None,
) -> V1PodList:
    """
    Get pods via Kubernetes API or skip if cluster unreachable or no matching pods.
    Use at test start when prerequisites may be missing.
    no_pods_reason: message when no pods match; if None, a default message is used.
    """
    try:
        pod_list = k8s_core.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector,
        )
    except Exception as e:
        pytest.skip(f"Cluster unreachable: {e}")
    if not pod_list.items or len(pod_list.items) == 0:
        reason = (
            no_pods_reason
            if no_pods_reason
            else f"No pods in {namespace} with label {label_selector}. "
            "Start a KinD cluster with default storage (local-path-provisioner)."
        )
        pytest.skip(reason)
    return pod_list


def pod_uids(pod_list: Union[V1PodList, List[V1Pod]]) -> list:
    """Return list of pod UIDs from V1PodList or list of V1Pod."""
    return [p.metadata.uid for p in _pods(pod_list)]


def restart_counts(pod_list: Union[V1PodList, List[V1Pod]]) -> int:
    """Return total restart count across all containers in V1PodList or list of V1Pod."""
    total = 0
    for p in _pods(pod_list):
        if not p.status or not p.status.container_statuses:
            continue
        for cs in p.status.container_statuses:
            total += getattr(cs, "restart_count", 0)
    return total


def list_pods_by_prefix(k8s_core, namespace: str, name_prefix: str) -> List[V1Pod]:
    """Return pods in the namespace whose name starts with name_prefix."""
    pods = k8s_core.list_namespaced_pod(namespace=namespace)
    return [
        p for p in _pods(pods)
        if p.metadata and p.metadata.name and p.metadata.name.startswith(name_prefix)
    ]


def wait_for_scheduled_pod_by_prefix(
    k8s_core, namespace: str, name_prefix: str, timeout: float
) -> Optional[V1Pod]:
    """
    Poll until a pod with name_prefix exists and is scheduled (spec.node_name set).
    Return it, or the last seen matching pod (may be None) if none get scheduled in time.
    """
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        for p in list_pods_by_prefix(k8s_core, namespace, name_prefix):
            last = p
            if p.spec and p.spec.node_name:
                return p
        time.sleep(0.5)
    return last


def wait_for_no_pods_by_prefix(
    k8s_core, namespace: str, name_prefix: str, timeout: float
) -> None:
    """Assert all pods with name_prefix are removed from the namespace within timeout."""
    deadline = time.monotonic() + timeout
    last = []
    while time.monotonic() < deadline:
        last = list_pods_by_prefix(k8s_core, namespace, name_prefix)
        if not last:
            return
        time.sleep(1)
    raise AssertionError(
        f"Pods with prefix {name_prefix!r} still present in namespace={namespace} "
        f"after {timeout}s: {[p.metadata.name for p in last]}"
    )


def schedulable_worker_nodes(k8s_core) -> List[str]:
    """Return names of Ready nodes that are not control-plane/master and carry no NoSchedule/NoExecute taint.

    The list is sorted by node name so selection is deterministic: the Kubernetes API does not
    guarantee node ordering, and callers rely on a stable order to keep the hog tests (first
    worker) and the destructive node tests (last worker) on separate nodes.
    """
    names = []
    for node in k8s_core.list_node().items:
        labels = (node.metadata.labels or {}) if node.metadata else {}
        if (
            "node-role.kubernetes.io/control-plane" in labels
            or "node-role.kubernetes.io/master" in labels
        ):
            continue
        taints = (node.spec.taints or []) if node.spec else []
        if any(getattr(t, "effect", None) in ("NoSchedule", "NoExecute") for t in taints):
            continue
        ready = any(
            c.type == "Ready" and c.status == "True"
            for c in ((node.status.conditions or []) if node.status else [])
        )
        if ready:
            names.append(node.metadata.name)
    return sorted(names)


def wait_node_ready(k8s_core, node: str, timeout: float) -> bool:
    """Poll until the node reports Ready=True. Return True if it does within timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            n = k8s_core.read_node(node)
        except Exception:  # noqa: BLE001 - node may be mid-restart / API briefly unreachable
            time.sleep(2)
            continue
        conditions = (n.status.conditions or []) if n.status else []
        if any(c.type == "Ready" and c.status == "True" for c in conditions):
            return True
        time.sleep(2)
    return False


def container_runtime() -> Optional[str]:
    """Return the container runtime backing the KinD cluster, or None if none is on PATH.

    A KinD node is a container. KinD's provider is selected by ``KIND_EXPERIMENTAL_PROVIDER``;
    when it is set to ``podman`` we must inspect/start with ``podman`` (and vice versa), otherwise
    we'd point the wrong CLI at the node container. Honor that env var first, then fall back to
    whichever runtime is available, preferring ``docker`` (KinD's default provider).
    """
    preferred = (os.environ.get("KIND_EXPERIMENTAL_PROVIDER") or "").strip().lower()
    order = ("podman", "docker") if preferred == "podman" else ("docker", "podman")
    for runtime in order:
        if shutil.which(runtime):
            return runtime
    return None


def container_started_at(node: str) -> Optional[str]:
    """Return the node container's State.StartedAt string, or None if it cannot be read.

    A KinD node is a container, so a successful stop/start or restart advances StartedAt. This
    gives a deterministic, runtime-level proof that a destructive action actually cycled the
    node -- independent of Kubernetes node-status timing and of Krkn's in-process kube_check.
    """
    runtime = container_runtime()
    if not runtime:
        return None
    try:
        proc = subprocess.run(
            [runtime, "inspect", "-f", "{{.State.StartedAt}}", node],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not inspect container %s via %s: %s", node, runtime, e)
        return None
    if proc.returncode != 0:
        logger.warning(
            "'%s inspect %s' exited %s: %s", runtime, node, proc.returncode,
            (proc.stderr or "").strip(),
        )
        return None
    return (proc.stdout or "").strip() or None


def assert_container_cycled(node: str, started_before, action: str) -> None:
    """Assert the node container was actually restarted (StartedAt advanced).

    No-op when the container runtime is unavailable or StartedAt could not be read on either
    side, so the check never yields a false negative off-cluster; on KinD (a runtime is always
    present) it deterministically proves the action disrupted the node.
    """
    started_after = container_started_at(node)
    if started_before is None or started_after is None:
        logger.warning(
            "Skipping container-cycle check for %s (%s): StartedAt unavailable "
            "(before=%r, after=%r)", node, action, started_before, started_after,
        )
        return
    assert started_after != started_before, (
        f"Node container {node} StartedAt did not advance ({started_before!r}); "
        f"{action} did not actually cycle the container"
    )


def ensure_node_container_running(node, k8s_core=None, timeout: float = 180) -> None:
    """Best-effort restore of a KinD node container after a destructive test (finalizer).

    Starts the container and, when ``k8s_core`` is given, waits for the node to report Ready so
    a later rerun (``--reruns``) never picks up an unrecovered node. Never raises -- a non-zero
    ``start`` exit and any exception are logged so the finalizer cannot mask the test result.
    """
    runtime = container_runtime()
    if not runtime:
        logger.warning("No container runtime on PATH; cannot ensure node %s is running", node)
        return
    try:
        running = subprocess.run(
            [runtime, "inspect", "-f", "{{.State.Running}}", node],
            capture_output=True, text=True, timeout=30,
        )
        if running.returncode == 0 and (running.stdout or "").strip() == "true":
            # Already running (e.g. after a reboot scenario) -- nothing to restore, stay quiet.
            pass
        else:
            proc = subprocess.run([runtime, "start", node], capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                logger.warning(
                    "'%s start %s' exited %s: %s", runtime, node, proc.returncode,
                    (proc.stderr or "").strip(),
                )
    except Exception as e:  # noqa: BLE001 - a finalizer must never raise
        logger.warning("Failed to start container for node %s via %s: %s", node, runtime, e)
        return
    if k8s_core is not None and not wait_node_ready(k8s_core, node, timeout):
        logger.warning(
            "Node %s did not report Ready within %ss during finalizer restore", node, timeout
        )


def assert_kraken_marker(result, marker: str, context: str = "", tmp_path=None) -> None:
    """Assert Krkn stdout/stderr contains a literal action marker (real execution evidence, not a silent no-op)."""
    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    if re.search(re.escape(marker), combined):
        return
    if tmp_path is not None:
        try:
            (tmp_path / "kraken_stdout.log").write_text(result.stdout or "")
            (tmp_path / "kraken_stderr.log").write_text(result.stderr or "")
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not write Kraken logs to tmp_path: %s", e)
    tail = "\n".join(combined.splitlines()[-30:]) or "(empty)"
    raise AssertionError(
        f"Expected marker {marker!r} in Krkn output ({context}) but it was missing.\n"
        f"--- krkn output (last 30 lines) ---\n{tail}"
    )


def get_network_policies_list(k8s_networking, namespace: str) -> V1NetworkPolicyList:
    """Return V1NetworkPolicyList from the Kubernetes API."""
    return k8s_networking.list_namespaced_network_policy(namespace=namespace)


def find_network_policy_by_prefix(
    policy_list: Union[V1NetworkPolicyList, List[V1NetworkPolicy]],
    name_prefix: str,
) -> Optional[V1NetworkPolicy]:
    """Return the first NetworkPolicy whose name starts with name_prefix, or None."""
    for policy in _policies(policy_list):
        if (
            policy.metadata
            and policy.metadata.name
            and policy.metadata.name.startswith(name_prefix)
        ):
            return policy
    return None


def assert_all_pods_running_and_ready(
    pod_list: Union[V1PodList, List[V1Pod]],
    namespace: str = "",
) -> None:
    """
    Assert all pods are Running and all containers Ready.
    Include namespace in assertion messages for debugging.
    """
    ns_suffix = f" (namespace={namespace})" if namespace else ""
    for pod in _pods(pod_list):
        assert pod.status and pod.status.phase == "Running", (
            f"Pod {pod.metadata.name} not Running after scenario: {pod.status}{ns_suffix}"
        )
        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                assert getattr(cs, "ready", False) is True, (
                    f"Container {getattr(cs, 'name', '?')} not ready in pod {pod.metadata.name}{ns_suffix}"
                )


def assert_pod_count_unchanged(
    before: Union[V1PodList, List[V1Pod]],
    after: Union[V1PodList, List[V1Pod]],
    namespace: str = "",
) -> None:
    """Assert pod count is unchanged; include namespace in failure message."""
    before_items = _pods(before)
    after_items = _pods(after)
    ns_suffix = f" (namespace={namespace})" if namespace else ""
    assert len(after_items) == len(before_items), (
        f"Pod count changed after scenario: expected {len(before_items)}, got {len(after_items)}.{ns_suffix}"
    )


def assert_kraken_success(result, context: str = "", tmp_path=None, allowed_codes=(0,)) -> None:
    """
    Assert Kraken run succeeded (returncode in allowed_codes). On failure, include stdout and stderr
    in the assertion message and optionally write full output to tmp_path.
    Default allowed_codes=(0,). For alert-aware tests, use allowed_codes=(0, 2).
    """
    if result.returncode in allowed_codes:
        return
    if tmp_path is not None:
        try:
            (tmp_path / "kraken_stdout.log").write_text(result.stdout or "")
            (tmp_path / "kraken_stderr.log").write_text(result.stderr or "")
        except Exception as e:
            logger.warning("Could not write Kraken logs to tmp_path: %s", e)
    lines = (result.stdout or "").splitlines()
    tail_stdout = "\n".join(lines[-20:]) if lines else "(empty)"
    context_str = f" {context}" if context else ""
    path_hint = f"\nFull logs: {tmp_path}/kraken_stdout.log, {tmp_path}/kraken_stderr.log" if tmp_path else ""
    raise AssertionError(
        f"Krkn failed (rc={result.returncode}){context_str}.{path_hint}\n"
        f"--- stderr ---\n{result.stderr or '(empty)'}\n"
        f"--- stdout (last 20 lines) ---\n{tail_stdout}"
    )


def assert_kraken_failure(result, context: str = "", tmp_path=None) -> None:
    """
    Assert Kraken run failed (returncode != 0). On failure (Kraken unexpectedly succeeded),
    raise AssertionError with stdout/stderr and optional tmp_path log files for diagnostics.
    """
    if result.returncode != 0:
        return
    if tmp_path is not None:
        try:
            (tmp_path / "kraken_stdout.log").write_text(result.stdout or "")
            (tmp_path / "kraken_stderr.log").write_text(result.stderr or "")
        except Exception as e:
            logger.warning("Could not write Kraken logs to tmp_path: %s", e)
    lines = (result.stdout or "").splitlines()
    tail_stdout = "\n".join(lines[-20:]) if lines else "(empty)"
    context_str = f" {context}" if context else ""
    path_hint = f"\nFull logs: {tmp_path}/kraken_stdout.log, {tmp_path}/kraken_stderr.log" if tmp_path else ""
    raise AssertionError(
        f"Expected Krkn to fail but it succeeded (rc=0){context_str}.{path_hint}\n"
        f"--- stderr ---\n{result.stderr or '(empty)'}\n"
        f"--- stdout (last 20 lines) ---\n{tail_stdout}"
    )


def assert_scenario_executed(result, scenario_name: str, context: str = "", tmp_path=None) -> None:
    """
    Assert that Krkn actually executed the scenario's core logic by matching a
    scenario-specific marker in stdout/stderr. Guards against false positives where
    Krkn exits 0 but silently did nothing (e.g. a selector that matches no targets).

    Skipped when KRKN_TEST_DRY_RUN=1. Negative tests must not call this helper.
    """
    if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
        return
    pattern = SCENARIO_EXECUTION_MARKERS.get(scenario_name)
    if pattern is None:
        raise AssertionError(
            f"No execution-evidence marker defined for scenario {scenario_name!r}. "
            "Add one to SCENARIO_EXECUTION_MARKERS in CI/tests_v2/lib/utils.py."
        )
    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    found = re.search(pattern, combined) is not None
    _record_execution_evidence(scenario_name, pattern, found)
    if found:
        return
    if tmp_path is not None:
        try:
            (tmp_path / "kraken_stdout.log").write_text(result.stdout or "")
            (tmp_path / "kraken_stderr.log").write_text(result.stderr or "")
        except Exception as e:
            logger.warning("Could not write Kraken logs to tmp_path: %s", e)
    lines = combined.splitlines()
    tail = "\n".join(lines[-30:]) if lines else "(empty)"
    context_str = f" {context}" if context else ""
    path_hint = f"\nFull logs: {tmp_path}/kraken_stdout.log, {tmp_path}/kraken_stderr.log" if tmp_path else ""
    raise AssertionError(
        f"Scenario {scenario_name!r} exited {result.returncode} but no execution evidence found"
        f"{context_str}.{path_hint}\nExpected pattern: {pattern}\n"
        f"--- krkn output (last 30 lines) ---\n{tail}"
    )
