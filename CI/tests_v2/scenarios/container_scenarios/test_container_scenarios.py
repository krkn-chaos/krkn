"""
Functional test for container chaos scenario (kill target container and verify restart).
Equivalent to CI/tests/test_container.sh with proper before/after assertions.
Each test runs in its own ephemeral namespace with workload deployed automatically.
"""

import pytest

from lib.base import BaseScenarioTest, READINESS_TIMEOUT, _set_nested
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_failure,
    assert_kraken_success,
    assert_scenario_executed,
    get_pods_list,
    restart_counts,
)


@pytest.mark.functional
@pytest.mark.container_scenarios
class TestContainerScenarios(BaseScenarioTest):
    """Container chaos scenario: kill a target container and verify restart."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/container_scenarios/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "scenario=container"
    SCENARIO_NAME = "container_scenarios"
    SCENARIO_TYPE = "container_scenarios"
    NAMESPACE_KEY_PATH = ["scenarios", 0, "namespace"]
    NAMESPACE_IS_REGEX = True

    @pytest.mark.order(1)
    def test_container_kill_and_restart(self, wait_for_pods_running):
        """Execute container chaos scenario and verify target container restart count increased."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        before_restarts = restart_counts(before)

        result = self.run_scenario(self.tmp_path, ns)
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path
        )

        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        after_restarts = restart_counts(after)
        assert after_restarts > before_restarts, (
            f"Container restart count did not increase in namespace={ns}: "
            f"before={before_restarts}, after={after_restarts}"
        )

        wait_for_pods_running(ns, self.LABEL_SELECTOR, timeout=READINESS_TIMEOUT)
        after_final = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        assert_all_pods_running_and_ready(after_final, namespace=ns)

    @pytest.mark.no_workload
    def test_invalid_container_name_fails(self):
        """Invalid container name causes Kraken to exit non-zero."""
        ns = self.ns
        scenario = self.load_and_patch_scenario(self.repo_root, ns)
        _set_nested(scenario, ["scenarios", 0, "container_name"], "nonexistent-container-xyz-12345")
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="invalid_container_config.yaml",
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(result, context=f"namespace={ns}", tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    def test_invalid_label_selector_fails(self):
        """Invalid label selector causes Kraken to exit non-zero."""
        ns = self.ns
        scenario = self.load_and_patch_scenario(self.repo_root, ns)
        _set_nested(scenario, ["scenarios", 0, "label_selector"], "nonexistent-label=xyz-12345")
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_bad_selector")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="invalid_selector_config.yaml",
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
