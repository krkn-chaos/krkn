"""
Functional tests for the CPU hog scenario (hog_scenarios), migrated from the legacy
CI/tests/test_cpu_hog.sh.

CPU hog targets nodes (not workloads): Krkn deploys a short-lived hog pod (name prefix
"cpu-hog-") onto each selected node, runs it for the configured duration, then deletes the
pod. These tests therefore use @pytest.mark.no_workload (no app deployment is needed) and
verify execution success, node-selector targeting, duration/lifecycle, cleanup, and graceful
failure on invalid selector/config.
"""

import logging
import subprocess

import pytest

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_success,
    schedulable_worker_nodes,
    wait_for_no_pods_by_prefix,
    wait_for_scheduled_pod_by_prefix,
)

logger = logging.getLogger(__name__)

HOG_POD_PREFIX = "cpu-hog-"
HOG_POD_CREATE_TIMEOUT = 120
HOG_POD_CLEANUP_TIMEOUT = 60
KRAKEN_RUN_TIMEOUT = 300


@pytest.mark.functional
@pytest.mark.cpu_hog
class TestCpuHog(BaseScenarioTest):
    """CPU hog scenario: deploy a CPU hog pod on selected node(s), then verify success and cleanup."""

    SCENARIO_NAME = "cpu_hog"
    SCENARIO_TYPE = "hog_scenarios"
    NAMESPACE_KEY_PATH = ["namespace"]
    NAMESPACE_IS_REGEX = False

    def _scenario(self, namespace, overrides):
        """Load scenario_base.yaml, patch namespace, then apply flat-dict overrides (hyphenated keys)."""
        scenario = self.load_and_patch_scenario(self.repo_root, namespace)
        scenario.update(overrides)
        return scenario

    @pytest.mark.no_workload
    @pytest.mark.order(1)
    def test_cpu_hog_success_lifecycle_and_targeting(self):
        """Happy path: a hog pod is created on the node-selector target, the run succeeds, and the pod is cleaned up."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node available for CPU hog targeting")
        node = nodes[0]
        ns = self.ns
        scenario = self._scenario(ns, {
            "node-selector": f"kubernetes.io/hostname={node}",
            "number-of-nodes": 1,
            "duration": 20,
        })
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="cpu_hog_success_config.yaml"
        )
        proc = self.run_kraken_background(config_path)
        try:
            pod = wait_for_scheduled_pod_by_prefix(self.k8s_core, ns, HOG_POD_PREFIX, timeout=HOG_POD_CREATE_TIMEOUT)
            assert pod is not None, (
                f"Expected a CPU hog pod (prefix {HOG_POD_PREFIX!r}) to be created in namespace={ns}"
            )
            assert pod.spec and pod.spec.node_name == node, (
                f"CPU hog pod {pod.metadata.name} scheduled on "
                f"{getattr(pod.spec, 'node_name', None)!r}, expected node-selector target {node!r} "
                f"(namespace={ns})"
            )
            out, err = proc.communicate(timeout=KRAKEN_RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            raise
        except BaseException:
            # Any poll/assert failure before communicate() must still tear down the
            # background Kraken process, otherwise its hog pod keeps stressing the node
            # and races against subsequent --reruns on the same target.
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise
        result = subprocess.CompletedProcess(args=[], returncode=proc.returncode, stdout=out, stderr=err)
        assert_kraken_success(result, context=f"node={node} namespace={ns}", tmp_path=self.tmp_path)
        wait_for_no_pods_by_prefix(self.k8s_core, ns, HOG_POD_PREFIX, timeout=HOG_POD_CLEANUP_TIMEOUT)

    @pytest.mark.no_workload
    @pytest.mark.order(2)
    def test_cpu_hog_invalid_selector_fails(self):
        """Negative: a node-selector matching zero nodes makes Krkn fail (no available nodes to schedule)."""
        ns = self.ns
        scenario = self._scenario(ns, {
            "node-selector": "kubernetes.io/hostname=krkn-nonexistent-node-zzz",
            "number-of-nodes": 1,
            "duration": 20,
        })
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="cpu_hog_invalid_selector_config.yaml"
        )
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_failure(
            result, context=f"invalid node-selector namespace={ns}", tmp_path=self.tmp_path
        )
        wait_for_no_pods_by_prefix(self.k8s_core, ns, HOG_POD_PREFIX, timeout=HOG_POD_CLEANUP_TIMEOUT)

    @pytest.mark.no_workload
    @pytest.mark.order(3)
    def test_cpu_hog_invalid_config_fails(self):
        """Negative: omitting the mandatory hog-type field makes Krkn fail at config parsing."""
        ns = self.ns
        scenario = self._scenario(ns, {"duration": 20})
        scenario.pop("hog-type", None)
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="cpu_hog_invalid_config_config.yaml"
        )
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_failure(
            result, context=f"missing hog-type namespace={ns}", tmp_path=self.tmp_path
        )
