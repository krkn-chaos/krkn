"""
Functional test for pod disruption scenario (pod crash and recovery).
Equivalent to CI/tests/test_pod.sh with proper before/after assertions.
Each test runs in its own ephemeral namespace with workload deployed automatically.
"""

import copy
import pytest
import yaml

from lib.base import BaseScenarioTest, READINESS_TIMEOUT
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_success,
    assert_pod_count_unchanged,
    get_pods_list,
    load_scenario_base,
    pod_uids,
    restart_counts,
)


def _load_and_patch_pod_disruption_scenario(repo_root, namespace: str) -> list:
    """Load scenario_base.yaml and patch namespace_pattern to match the test namespace."""
    scenario = copy.deepcopy(load_scenario_base(repo_root, "pod_disruption"))
    if scenario and isinstance(scenario, list) and len(scenario) > 0:
        if "config" in scenario[0]:
            scenario[0]["config"]["namespace_pattern"] = f"^{namespace}$"
    return scenario


@pytest.mark.functional
@pytest.mark.pod_disruption
class TestPodDisruption(BaseScenarioTest):
    """Pod disruption scenario: kill pods and verify recovery."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_disruption/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "app=krkn-pod-disruption-target"

    @pytest.mark.order(1)
    def test_pod_crash_and_recovery(
        self, build_config, run_kraken, k8s_core, wait_for_pod_ready, tmp_path, repo_root
    ):
        ns = self.ns
        before = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)
        before_items = before.items
        before_uids = pod_uids(before)
        before_restarts = restart_counts(before)

        scenario_list = _load_and_patch_pod_disruption_scenario(repo_root, ns)
        scenario_path = tmp_path / "pod_disruption_scenario.yml"
        with open(scenario_path, "w") as f:
            yaml.dump(scenario_list, f, default_flow_style=False, sort_keys=False)

        config_path = build_config(
            "pod_disruption_scenarios",
            str(scenario_path),
        )
        result = run_kraken(config_path)
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=tmp_path)

        after = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)
        after_uids = pod_uids(after)
        after_restarts = restart_counts(after)
        uids_changed = set(after_uids) != set(before_uids)
        restarts_increased = after_restarts > before_restarts
        assert uids_changed or restarts_increased, (
            f"Chaos had no effect in namespace={ns}: pod UIDs unchanged and restart count did not increase. "
            f"Before UIDs: {before_uids}, restarts: {before_restarts}. "
            f"After UIDs: {after_uids}, restarts: {after_restarts}."
        )

        wait_for_pod_ready(ns, self.LABEL_SELECTOR, timeout=READINESS_TIMEOUT)

        after_final = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after_final, namespace=ns)
        assert_all_pods_running_and_ready(after_final, namespace=ns)
