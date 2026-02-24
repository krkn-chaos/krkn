"""
Shared helpers for CI/tests_v2 functional tests.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional, Union

import pytest
import yaml
from kubernetes.client import V1NetworkPolicy, V1NetworkPolicyList, V1Pod, V1PodList

logger = logging.getLogger(__name__)


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


def assert_kraken_success(result, context: str = "", tmp_path=None) -> None:
    """
    Assert Kraken run succeeded (returncode 0). On failure, include stdout and stderr
    in the assertion message and optionally write full output to tmp_path.
    """
    if result.returncode == 0:
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
