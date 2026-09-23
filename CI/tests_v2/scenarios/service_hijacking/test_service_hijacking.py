"""Service hijacking plan and rollback integration tests."""
import pytest

from lib.base import BaseScenarioTest
from lib.utils import assert_kraken_failure, assert_kraken_success, assert_scenario_executed

@pytest.mark.functional
@pytest.mark.service_hijacking
@pytest.mark.xdist_group("service_hijacking")
class TestServiceHijacking(BaseScenarioTest):
    """Exercise service hijacking plan execution and rollback behavior."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/service_hijacking/resource.yaml"
    LABEL_SELECTOR = "app=nginx"
    SCENARIO_NAME = "service_hijacking"
    SCENARIO_TYPE = "service_hijacking_scenarios"
    NAMESPACE_KEY_PATH = ["service_namespace"]
    OVERRIDES_KEY_PATH = []

    def test_plan_runs_and_restores_service(self):
        """Run the response plan successfully and restore the original Service."""
        result = self.run_scenario(self.tmp_path, self.ns, config_filename="service-hijacking.yaml")
        assert_kraken_success(result, context=self.ns, tmp_path=self.tmp_path)
        assert_scenario_executed(result, self.SCENARIO_NAME, context=self.ns, tmp_path=self.tmp_path)

    def test_missing_service_fails(self):
        """Fail when the configured Service does not exist."""
        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        scenario["service_name"] = "missing-service"
        path = self.write_scenario(self.tmp_path, scenario, suffix="-missing")
        config = self.build_config(self.SCENARIO_TYPE, str(path), filename="missing-service.yaml")
        result = self.run_kraken(config)
        assert_kraken_failure(result, context="missing hijack service", tmp_path=self.tmp_path)
