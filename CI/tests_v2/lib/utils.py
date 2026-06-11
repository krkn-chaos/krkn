"""
Shared helpers for CI/tests_v2 functional tests.
"""

import logging
import os
import re
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
    "application_outage": r"Creating the network policy|Deleting the network policy",
    "storage_throttle": r"Setting io\.max|Verified blkio settings|Privileged pod deployed",
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
    raise AssertionError(
        f"Scenario {scenario_name!r} exited {result.returncode} but no execution evidence found"
        f"{context_str}.\nExpected pattern: {pattern}\n"
        f"--- krkn output (last 30 lines) ---\n{tail}"
    )
