"""
Functional test for CPU hog scenario.
Verifies Krkn hog scenario plugin executes correctly: spawns stress pods on target nodes and cleans up.
Equivalent to CI/tests/test_cpu_hog.sh with proper assertions.
"""

import time
from types import SimpleNamespace

import pytest

from lib.base import BaseScenarioTest, POLICY_WAIT_TIMEOUT
from lib.utils import assert_kraken_failure, assert_kraken_success


def _get_hog_pods(k8s_core, namespace: str, prefix: str = "cpu-hog-"):
    """Return list of pods in namespace whose name starts with prefix."""
    pod_list = k8s_core.list_namespaced_pod(namespace=namespace)
    return [p for p in pod_list.items if p.metadata and p.metadata.name.startswith(prefix)]


def _wait_for_hog_pod(k8s_core, namespace: str, prefix: str = "cpu-hog-", timeout: int = 30):
    """Poll until a pod with name starting with prefix exists. Return the pod list."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pods = _get_hog_pods(k8s_core, namespace, prefix)
        if pods:
            return pods
        time.sleep(1)
    raise TimeoutError(f"No hog pod with prefix {prefix!r} in {namespace} within {timeout}s")


@pytest.mark.functional
@pytest.mark.cpu_hog
@pytest.mark.no_workload
class TestCpuHog(BaseScenarioTest):
    """CPU hog scenario: spawn stress pods on target nodes and verify cleanup."""

    WORKLOAD_MANIFEST = None
    SCENARIO_NAME = "cpu_hog"
    SCENARIO_TYPE = "hog_scenarios"
    NAMESPACE_KEY_PATH = ["namespace"]
    HOG_POD_PREFIX = "cpu-hog-"

    @pytest.mark.order(1)
    def test_cpu_hog_success_and_lifecycle(self):
        """Krkn runs CPU hog scenario; hog pod appears during run, then exit 0 and no hog pods remain."""
        ns = self.ns
        scenario = self.load_and_patch_scenario(self.repo_root, ns)
        scenario["duration"] = 10
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_lifecycle")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="cpu_hog_lifecycle.yaml",
        )
        proc = self.run_kraken_background(config_path)
        try:
            pods = _wait_for_hog_pod(
                self.k8s_core, ns, self.HOG_POD_PREFIX, timeout=POLICY_WAIT_TIMEOUT
            )
            assert len(pods) >= 1, f"Expected at least one hog pod in namespace={ns}"
        finally:
            # duration=10 + pod wait (30s) + cleanup; allow 90s for Krkn to exit.
            stdout, stderr = proc.communicate(timeout=90)
        result = SimpleNamespace(
            returncode=proc.returncode,
            stdout=stdout or "",
            stderr=stderr or "",
        )
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        hog_pods_after = _get_hog_pods(self.k8s_core, ns, self.HOG_POD_PREFIX)
        assert len(hog_pods_after) == 0, (
            f"Expected no hog pods after scenario in namespace={ns}, found: "
            f"{[p.metadata.name for p in hog_pods_after]}"
        )

    def test_node_selector_and_duration(self):
        """Scenario targets nodes with selector and respects duration; run succeeds and takes ~duration."""
        ns = self.ns
        scenario = self.load_and_patch_scenario(self.repo_root, ns)
        scenario["node-selector"] = "kubernetes.io/os=linux"
        scenario["duration"] = 10
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_node_selector_duration")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="cpu_hog_node_selector_duration.yaml",
        )
        start = time.monotonic()
        result = self.run_kraken(config_path, timeout=90)
        elapsed = time.monotonic() - start
        assert_kraken_success(
            result,
            context=f"namespace={ns} node-selector=kubernetes.io/os=linux duration=10",
            tmp_path=self.tmp_path,
        )
        assert elapsed >= 8, f"Scenario should run at least ~8s (duration=10), elapsed={elapsed:.1f}s"
        assert elapsed < 90, f"Scenario should complete within 90s, elapsed={elapsed:.1f}s"

    def test_invalid_node_selector_fails(self):
        """Krkn fails gracefully when node selector matches no nodes."""
        ns = self.ns
        scenario = self.load_and_patch_scenario(self.repo_root, ns)
        scenario["node-selector"] = "nonexistent-label=nonexistent-value"
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_invalid_selector")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="cpu_hog_invalid_selector.yaml",
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(result, context=f"namespace={ns}", tmp_path=self.tmp_path)

    def test_invalid_scenario_fails(self):
        """Krkn fails gracefully with invalid scenario YAML."""
        invalid_scenario_path = self.tmp_path / "invalid_cpu_hog.yaml"
        invalid_scenario_path.write_text("foo: bar\n")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(invalid_scenario_path),
            filename="invalid_cpu_hog_config.yaml",
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(result, context="invalid scenario", tmp_path=self.tmp_path)
