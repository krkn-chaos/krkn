"""
Functional test for container disruption scenario.
Migrated from CI/tests/test_container.sh.
Each test runs in its own ephemeral namespace with workload deployed automatically.
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
    pod_uids,
    restart_counts,
)


@pytest.mark.functional
@pytest.mark.container_scenarios
class TestContainerScenarios(BaseScenarioTest):
    """Container disruption scenario: kill containers and verify recovery."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/container_scenarios/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "scenario=container"
    SCENARIO_NAME = "container_scenarios"
    SCENARIO_TYPE = "container_scenarios"
    NAMESPACE_KEY_PATH = ["scenarios", 0, "namespace"]
    NAMESPACE_IS_REGEX = False
    OVERRIDES_KEY_PATH = ["scenarios", 0]

    @pytest.mark.order(1)
    def test_container_kill_and_recovery(self, wait_for_pods_running):
        """Happy path: target container is killed and the workload recovers."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        before_uids = pod_uids(before)
        before_restarts = restart_counts(before)

        result = self.run_scenario(self.tmp_path, ns, overrides={
            "container_name": "fedtools",
            "expected_recovery_time": 30,
        })
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path
        )

        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        after_uids = pod_uids(after)
        after_restarts = restart_counts(after)
        uids_changed = set(after_uids) != set(before_uids)
        restarts_increased = after_restarts > before_restarts
        assert uids_changed or restarts_increased, (
            f"Container chaos had no effect in namespace={ns}: pod UIDs unchanged and "
            f"restart count did not increase. Before UIDs: {before_uids}, "
            f"restarts: {before_restarts}. After UIDs: {after_uids}, restarts: {after_restarts}."
        )

        wait_for_pods_running(ns, self.LABEL_SELECTOR, timeout=READINESS_TIMEOUT)
        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)
        assert_all_pods_running_and_ready(after, namespace=ns)

    @pytest.mark.order(2)
    def test_container_label_selector_targeting(self, wait_for_pods_running):
        """Label selector and namespace filtering target the expected workload."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)

        result = self.run_scenario(self.tmp_path, ns, overrides={
            "container_name": "fedtools",
            "label_selector": "scenario=container",
            "expected_recovery_time": 30,
        })
        assert_kraken_success(
            result, context=f"label_selector namespace={ns}", tmp_path=self.tmp_path
        )
        assert_scenario_executed(
            result, self.SCENARIO_NAME,
            context=f"label_selector namespace={ns}", tmp_path=self.tmp_path,
        )

        wait_for_pods_running(ns, self.LABEL_SELECTOR, timeout=READINESS_TIMEOUT)
        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)
        assert_all_pods_running_and_ready(after, namespace=ns)

    @pytest.mark.order(3)
    def test_container_dry_run_behavior(self):
        """Dry-run: scenario must not kill containers."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        before_restarts = restart_counts(before)

        result = self.run_scenario(self.tmp_path, ns, overrides={
            "container_name": "fedtools",
            "dry_run": True,
            "expected_recovery_time": 30,
        })
        assert_kraken_success(result, context=f"dry_run namespace={ns}", tmp_path=self.tmp_path)

        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        after_restarts = restart_counts(after)

        assert after_restarts == before_restarts, (
            f"Dry-run affected containers: before restarts={before_restarts}, "
            f"after restarts={after_restarts} (namespace={ns})"
        )

    @pytest.mark.order(4)
    def test_invalid_container_name_fails(self):
        """Negative: invalid container name must fail when kill count exceeds matches."""
        ns = self.ns
        result = self.run_scenario(self.tmp_path, ns, overrides={
            "container_name": "nonexistent-container",
            "count": 2,
        })
        assert_kraken_failure(
            result, context=f"invalid_container namespace={ns}", tmp_path=self.tmp_path
        )

    @pytest.mark.no_workload
    @pytest.mark.order(5)
    def test_invalid_label_selector_fails(self):
        """Negative: label selector matching no pods must fail gracefully."""
        ns = self.ns
        result = self.run_scenario(self.tmp_path, ns, overrides={
            "container_name": "fedtools",
            "label_selector": "nonexistent=label",
        })
        assert_kraken_failure(
            result, context=f"invalid_selector namespace={ns}", tmp_path=self.tmp_path
        )
