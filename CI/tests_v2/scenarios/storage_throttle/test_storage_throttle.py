"""
Functional test for storage throttle scenario (cgroup I/O throttle on PVC-backed volume).

Deploys a PVC + Deployment in an ephemeral namespace, runs the storage_throttle
scenario with the `both` configuration, and verifies:
  - Krkn exits 0 (throttle applied and removed cleanly)
  - Target pods survive (running and ready after scenario)

The `both` config drives the identical _apply_throttle production path as the
former bandwidth/iops-only variants (same code, different value strings), so a
single run preserves the full assertion set of all three. Negative
config-validation paths (bad namespace, invalid throttle_type) are covered by
the pushed unit suite (tests/test_storage_throttle_scenario_plugin.py).

Follows the CI/tests_v2 BaseScenarioTest pattern.
"""

import pytest

from lib.base import BaseScenarioTest, READINESS_TIMEOUT
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_success,
    assert_pod_count_unchanged,
    assert_scenario_executed,
    get_pods_list,
)


@pytest.mark.functional
@pytest.mark.storage_throttle
@pytest.mark.xdist_group("node-resource-chaos")
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

    def test_throttle_and_recovery(self, wait_for_pods_running):
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
