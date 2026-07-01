"""
Functional test for storage throttle scenario (cgroup I/O throttle on PVC-backed volume).

Deploys a PVC + Deployment in an ephemeral namespace, runs the storage_throttle
scenario, and verifies:
  - Krkn exits 0 (throttle applied and removed cleanly)
  - Target pods survive (running and ready after scenario)
  - Negative cases: bad namespace and invalid throttle_type fail gracefully

Follows the CI/tests_v2 BaseScenarioTest pattern.
"""

import pytest

from lib.base import BaseScenarioTest, READINESS_TIMEOUT
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_failure,
    assert_kraken_success,
    assert_pod_count_unchanged,
    assert_scenario_executed,
    get_pods_list,
)


@pytest.mark.functional
@pytest.mark.storage_throttle
class TestStorageThrottle(BaseScenarioTest):
    """Storage throttle scenario: apply I/O cgroup limits on a PVC mount and verify recovery."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/storage_throttle/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "app=krkn-throttle-target"
    SCENARIO_NAME = "storage_throttle"
    SCENARIO_TYPE = "storage_throttle_scenarios"
    NAMESPACE_KEY_PATH = ["storage_throttle_scenario", "namespace"]
    NAMESPACE_IS_REGEX = False
    OVERRIDES_KEY_PATH = ["storage_throttle_scenario"]

    @pytest.mark.order(1)
    def test_bandwidth_throttle_and_recovery(self, wait_for_pods_running):
        """Bandwidth throttle: apply read/write bps limits, verify Krkn success and pod recovery."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)

        result = self.run_scenario(self.tmp_path, ns, overrides={
            "throttle_type": "bandwidth",
            "read_bps": "1Mi",
            "write_bps": "512Ki",
            "duration": 15,
        })
        assert_kraken_success(result, context=f"bandwidth namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"bandwidth namespace={ns}", tmp_path=self.tmp_path
        )

        wait_for_pods_running(ns, self.LABEL_SELECTOR, timeout=READINESS_TIMEOUT)
        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)
        assert_all_pods_running_and_ready(after, namespace=ns)

    @pytest.mark.order(2)
    def test_iops_throttle_and_recovery(self, wait_for_pods_running):
        """IOPS throttle: apply read/write iops limits, verify Krkn success and pod recovery."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)

        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={
                "throttle_type": "iops",
                "read_iops": 50,
                "write_iops": 25,
                "duration": 15,
            },
            config_filename="test_iops_config.yaml",
        )
        assert_kraken_success(result, context=f"iops namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"iops namespace={ns}", tmp_path=self.tmp_path
        )

        wait_for_pods_running(ns, self.LABEL_SELECTOR, timeout=READINESS_TIMEOUT)
        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)
        assert_all_pods_running_and_ready(after, namespace=ns)

    @pytest.mark.order(3)
    def test_both_throttle_and_recovery(self, wait_for_pods_running):
        """Combined throttle: apply both bps and iops limits, verify Krkn success and pod recovery."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)

        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={
                "throttle_type": "both",
                "read_bps": "1Mi",
                "write_bps": "512Ki",
                "read_iops": 50,
                "write_iops": 25,
                "duration": 15,
            },
            config_filename="test_both_config.yaml",
        )
        assert_kraken_success(result, context=f"both namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"both namespace={ns}", tmp_path=self.tmp_path
        )

        wait_for_pods_running(ns, self.LABEL_SELECTOR, timeout=READINESS_TIMEOUT)
        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)
        assert_all_pods_running_and_ready(after, namespace=ns)

    @pytest.mark.no_workload
    def test_bad_namespace_fails(self):
        """Scenario targeting non-existent namespace causes Krkn to exit non-zero."""
        scenario = self.load_and_patch_scenario(
            self.repo_root, "nonexistent-namespace-xyz-99999",
            pod_name="nonexistent-pod",
        )
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_bad_ns")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="storage_throttle_bad_ns_config.yaml",
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(
            result, context=f"bad namespace test", tmp_path=self.tmp_path,
        )

    @pytest.mark.no_workload
    def test_invalid_throttle_type_fails(self):
        """Invalid throttle_type causes Krkn to exit non-zero."""
        scenario = self.load_and_patch_scenario(
            self.repo_root, self.ns,
            throttle_type="invalid_type",
            pod_name="doesnt-matter",
        )
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_bad_type")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="storage_throttle_bad_type_config.yaml",
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(
            result, context=f"invalid throttle_type test", tmp_path=self.tmp_path,
        )
