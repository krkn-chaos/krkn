"""
Functional test for pod error / failure-mode coverage.
Migrated from CI/tests/test_pod_error.sh with expected-failure semantics added.
"""

import pytest

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_success,
    assert_scenario_executed,
    get_pods_list,
    pod_uids,
)


@pytest.mark.functional
@pytest.mark.pod_error_scenarios
class TestPodErrorScenarios(BaseScenarioTest):
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_error_scenarios/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "app=krkn-pod-error-target"
    SCENARIO_NAME = "pod_error_scenarios"
    SCENARIO_TYPE = "pod_disruption_scenarios"
    NAMESPACE_KEY_PATH = [0, "config", "namespace_pattern"]
    NAMESPACE_IS_REGEX = True
    OVERRIDES_KEY_PATH = [0, "config"]

    # -- Helper assertions -------------------------------------------

    def assert_failure_logs_contain(self, result, ns, expected_reasons, expected_keywords=None):
        # Timeouts / hangs are caught at the execution level by run_kraken (raises
        # TimeoutExpired) or pytest timeout budgets. Reaching here guarantees the run completed.
        
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        combined_lower = combined.lower()
        
        # Assert namespace is in the logs
        assert ns.lower() in combined_lower, f"Expected namespace '{ns}' not found in logs"
        
        # Assert failure reasons are in the logs
        for reason in expected_reasons:
            assert reason.lower() in combined_lower, f"Expected failure reason '{reason}' not found in logs"
            
        if expected_keywords:
            for kw in expected_keywords:
                assert kw.lower() in combined_lower, f"Expected log keyword '{kw}' not found in logs"

    # -- Happy path --------------------------------------------------

    @pytest.mark.order(1)
    def test_kill_one_pod_recovers(self, wait_for_pods_running):
        ns = self.ns
        result = self.run_scenario(self.tmp_path, ns)
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path)
        wait_for_pods_running(ns, self.LABEL_SELECTOR, timeout=90)

    @pytest.mark.order(2)
    def test_kill_multiple_pods(self, wait_for_pods_running):
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        before_uids = set(pod_uids(before))

        result = self.run_scenario(self.tmp_path, ns, overrides={"kill": 2})
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path)

        wait_for_pods_running(ns, self.LABEL_SELECTOR, timeout=90)
        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        after_uids = set(pod_uids(after))
        assert before_uids.isdisjoint(after_uids), (
            f"Expected both pods replaced (namespace={ns}). before={before_uids} after={after_uids}"
        )

    # -- Negative / failure-mode --------------------------------------

    def test_excessive_kill_count_fails(self):
        ns = self.ns
        result = self.run_scenario(self.tmp_path, ns, overrides={"kill": 100})
        assert_kraken_failure(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        # Expected error text must match the message raised at
        # pod_disruption_scenario_plugin.py:234. Update both together
        # if that message wording changes.
        self.assert_failure_logs_contain(
            result, ns, expected_reasons=["not enough pods match", "expected 100", "found only 2 pods"]
        )

    def test_recovery_timeout_fails(self):
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        before_names = [p.metadata.name for p in before.items]

        result = self.run_scenario(
            self.tmp_path, ns, overrides={"krkn_pod_recovery_time": 1}
        )
        assert_kraken_failure(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        
        # Verify no hang and logs contain namespace and expected timeout/recovery errors
        self.assert_failure_logs_contain(
            result, ns, expected_reasons=["timeout", "recover"]
        )
        
        # Verify at least one target pod name is in the logs
        combined_lower = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
        found_pod = any(name.lower() in combined_lower for name in before_names)
        assert found_pod, f"None of the target pods {before_names} were found in failure logs"

    @pytest.mark.no_workload
    def test_invalid_namespace_pattern_fails(self):
        scenario = self.load_and_patch_scenario(self.repo_root, "nonexistent-ns-xyz")
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_bad_ns")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="pod_error_bad_ns_config.yaml"
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(result, context="invalid namespace pattern", tmp_path=self.tmp_path)
        self.assert_failure_logs_contain(
            result, "nonexistent-ns-xyz", expected_reasons=["not enough pods match", "expected 1", "found only 0 pods"]
        )

    def test_zero_pods_matching_label_fails(self):
        ns = self.ns
        result = self.run_scenario(self.tmp_path, ns, overrides={"label_selector": "app=nonexistent"})
        assert_kraken_failure(result, context=f"namespace={ns}, label mismatch", tmp_path=self.tmp_path)
        self.assert_failure_logs_contain(
            result, ns, expected_reasons=["not enough pods match", "expected 1", "found only 0 pods"]
        )
