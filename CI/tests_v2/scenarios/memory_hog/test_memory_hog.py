"""
Functional test for memory hog scenario.
The hog plugin deploys its own stress pods; no pre-deployed workload. All tests use no_workload.
"""

import copy
import time

import pytest

from lib.base import (
    BaseScenarioTest,
    KRAKEN_PROC_WAIT_TIMEOUT,
    READINESS_TIMEOUT,
    _set_nested,
)
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_success,
    load_scenario_base,
)


def _has_control_plane_taint(node):
    """Return True if node has the control-plane NoSchedule taint (unschedulable for hog pod)."""
    taints = getattr(node.spec, "taints", None) or []
    for t in taints:
        if t and getattr(t, "key", None) == "node-role.kubernetes.io/control-plane":
            return True
    return False


def _get_worker_node(k8s_core):
    """Discover a schedulable worker node. Skips control-plane (NoSchedule taint)."""
    nodes = k8s_core.list_node()
    # Prefer worker-labeled node that is schedulable (no control-plane taint)
    for node in nodes.items or []:
        if not node.metadata or not node.metadata.name:
            continue
        if _has_control_plane_taint(node):
            continue
        if (node.metadata.labels or {}).get("node-role.kubernetes.io/worker"):
            return node.metadata.name
    # Fallback: any node without control-plane taint
    for node in nodes.items or []:
        if not node.metadata or not node.metadata.name:
            continue
        if _has_control_plane_taint(node):
            continue
        return node.metadata.name
    # Single-node / dev: first node with worker label (may be control-plane in old setups)
    for node in nodes.items or []:
        if node.metadata and node.metadata.name and (node.metadata.labels or {}).get("node-role.kubernetes.io/worker"):
            return node.metadata.name
    for node in nodes.items or []:
        if node.metadata and node.metadata.name:
            return node.metadata.name
    raise RuntimeError("No worker or any node found in cluster")


def _find_hog_pods(k8s_core, namespace):
    """Return pods whose name contains '-hog-' (e.g. memory-hog-xxxxx)."""
    pod_list = k8s_core.list_namespaced_pod(namespace=namespace)
    return [p for p in (pod_list.items or []) if p.metadata and "-hog-" in (p.metadata.name or "")]


def _wait_for_hog_pod(k8s_core, namespace, timeout=READINESS_TIMEOUT):
    """Poll until a hog pod appears; return the first one or raise TimeoutError."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pods = _find_hog_pods(k8s_core, namespace)
        if pods:
            return pods[0]
        time.sleep(1)
    raise TimeoutError(
        f"No hog pod appeared in namespace={namespace} within {timeout}s"
    )


def _wait_for_pod_scheduled(k8s_core, namespace, pod_name, timeout=60):
    """Poll until the pod has node_name set (scheduled); return updated pod or raise TimeoutError."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pod = k8s_core.read_namespaced_pod(name=pod_name, namespace=namespace)
        if pod.spec and pod.spec.node_name:
            return pod
        time.sleep(1)
    raise TimeoutError(
        f"Pod {pod_name} in {namespace} was not scheduled within {timeout}s"
    )


def _wait_for_pod_running(k8s_core, namespace, pod_name, timeout=60):
    """Poll until the pod phase is Running; return updated pod or raise TimeoutError."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pod = k8s_core.read_namespaced_pod(name=pod_name, namespace=namespace)
        if pod.status and pod.status.phase == "Running":
            return pod
        time.sleep(1)
    raise TimeoutError(
        f"Pod {pod_name} in {namespace} did not reach Running within {timeout}s (phase={getattr(pod.status, 'phase', None)})"
    )


@pytest.mark.functional
@pytest.mark.memory_hog
@pytest.mark.no_workload
class TestMemoryHog(BaseScenarioTest):
    """Memory hog scenario: plugin deploys stress pods; tests verify execution and cleanup."""

    WORKLOAD_MANIFEST = None
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = None
    SCENARIO_NAME = "memory_hog"
    SCENARIO_TYPE = "hog_scenarios"
    NAMESPACE_KEY_PATH = ["namespace"]
    NAMESPACE_IS_REGEX = False
    OVERRIDES_KEY_PATH = []

    def load_and_patch_scenario(self, repo_root, namespace, **overrides):
        """Flat YAML: patch namespace and apply overrides at root."""
        scenario = copy.deepcopy(load_scenario_base(repo_root, self.SCENARIO_NAME))
        ns_value = f"^{namespace}$" if self.NAMESPACE_IS_REGEX else namespace
        if self.NAMESPACE_KEY_PATH:
            _set_nested(scenario, self.NAMESPACE_KEY_PATH, ns_value)
        for key, value in overrides.items():
            scenario[key] = value
        return scenario

    @pytest.mark.order(1)
    def test_scenario_execution_success(self):
        """Scenario runs successfully and cleans up (no hog pods left)."""
        ns = self.ns
        worker = _get_worker_node(self.k8s_core)
        overrides = {"node-selector": f"kubernetes.io/hostname={worker}"}

        result = self.run_scenario(self.tmp_path, ns, overrides=overrides)
        assert_kraken_success(
            result, context=f"namespace={ns}", tmp_path=self.tmp_path
        )

        hog_pods = _find_hog_pods(self.k8s_core, ns)
        assert len(hog_pods) == 0, (
            f"Expected no hog pods after scenario in namespace={ns}, found {[p.metadata.name for p in hog_pods]}"
        )

    def test_stress_pod_lifecycle(self):
        """Hog pod is created during run and removed after completion."""
        ns = self.ns
        worker = _get_worker_node(self.k8s_core)
        scenario = self.load_and_patch_scenario(
            self.repo_root, ns,
            **{"duration": 20, "node-selector": f"kubernetes.io/hostname={worker}"},
        )
        scenario_path = self.write_scenario(
            self.tmp_path, scenario, suffix="_lifecycle"
        )
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="memory_hog_lifecycle.yaml",
        )
        proc = self.run_kraken_background(config_path)
        try:
            pod = _wait_for_hog_pod(
                self.k8s_core, ns, timeout=READINESS_TIMEOUT
            )
            pod = _wait_for_pod_running(
                self.k8s_core, ns, pod.metadata.name, timeout=60
            )
            assert pod.status.phase == "Running", (
                f"Hog pod {pod.metadata.name} not Running: {pod.status} (namespace={ns})"
            )
        finally:
            proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)

        hog_pods = _find_hog_pods(self.k8s_core, ns)
        assert len(hog_pods) == 0, (
            f"Expected no hog pods after completion in namespace={ns}, found {[p.metadata.name for p in hog_pods]}"
        )

    def test_node_selector_targeting(self):
        """Hog pod is scheduled on the node specified by node-selector."""
        ns = self.ns
        worker = _get_worker_node(self.k8s_core)
        scenario = self.load_and_patch_scenario(
            self.repo_root, ns,
            **{"duration": 20, "node-selector": f"kubernetes.io/hostname={worker}"},
        )
        scenario_path = self.write_scenario(
            self.tmp_path, scenario, suffix="_targeting"
        )
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="memory_hog_targeting.yaml",
        )
        proc = self.run_kraken_background(config_path)
        try:
            pod = _wait_for_hog_pod(
                self.k8s_core, ns, timeout=READINESS_TIMEOUT
            )
            pod = _wait_for_pod_scheduled(
                self.k8s_core, ns, pod.metadata.name, timeout=60
            )
            assert pod.spec.node_name == worker, (
                f"Hog pod scheduled on {pod.spec.node_name}, expected {worker} (namespace={ns})"
            )
        finally:
            proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)

    def test_duration_configuration(self):
        """Scenario respects configured duration (elapsed time within budget)."""
        ns = self.ns
        worker = _get_worker_node(self.k8s_core)
        duration = 15
        overrides = {
            "node-selector": f"kubernetes.io/hostname={worker}",
            "duration": duration,
        }
        start = time.monotonic()
        result = self.run_scenario(
            self.tmp_path, ns, overrides=overrides,
            config_filename="memory_hog_duration.yaml",
        )
        elapsed = time.monotonic() - start
        assert_kraken_success(
            result, context=f"namespace={ns}", tmp_path=self.tmp_path
        )
        assert elapsed >= duration, (
            f"Run finished in {elapsed:.1f}s, expected at least duration={duration}s (namespace={ns})"
        )
        assert elapsed <= duration + 60, (
            f"Run took {elapsed:.1f}s, expected duration ~{duration}s + overhead (namespace={ns})"
        )

    def test_memory_size_configuration(self):
        """Scenario accepts memory-vm-bytes override and completes successfully."""
        ns = self.ns
        worker = _get_worker_node(self.k8s_core)
        overrides = {
            "node-selector": f"kubernetes.io/hostname={worker}",
            "memory-vm-bytes": "50%",
        }
        result = self.run_scenario(
            self.tmp_path, ns, overrides=overrides,
            config_filename="memory_hog_memory_config.yaml",
        )
        assert_kraken_success(
            result, context=f"namespace={ns}", tmp_path=self.tmp_path
        )

    def test_invalid_node_selector_fails(self):
        """Invalid node selector (no matching nodes) causes Krkn to exit non-zero."""
        ns = self.ns
        overrides = {
            "node-selector": "kubernetes.io/hostname=nonexistent-node-xyz-99999",
        }
        result = self.run_scenario(
            self.tmp_path, ns, overrides=overrides,
            config_filename="memory_hog_invalid_node.yaml",
        )
        assert_kraken_failure(
            result, context=f"namespace={ns}", tmp_path=self.tmp_path
        )

    def test_invalid_scenario_fails(self):
        """Invalid scenario YAML causes Krkn to exit non-zero."""
        invalid_path = self.tmp_path / "invalid_scenario.yaml"
        invalid_path.write_text("completely: invalid\n")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(invalid_path),
            filename="invalid_memory_hog_config.yaml",
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(
            result, context=f"namespace={self.ns}", tmp_path=self.tmp_path
        )
