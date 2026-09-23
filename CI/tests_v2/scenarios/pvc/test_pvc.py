"""PVC fill lifecycle and failure-mode integration tests."""
import pytest

from lib.base import BaseScenarioTest
from lib.utils import assert_all_pods_running_and_ready, assert_kraken_failure, assert_kraken_success, get_pods_list

@pytest.mark.functional
@pytest.mark.pvc
class TestPVC(BaseScenarioTest):
    """Validate PVC fill effects, workload health, and missing-claim failure."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pvc/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pvc-target"
    SCENARIO_NAME = "pvc"
    SCENARIO_TYPE = "pvc_scenarios"
    NAMESPACE_KEY_PATH = ["pvc_scenario", "namespace"]
    OVERRIDES_KEY_PATH = ["pvc_scenario"]

    def test_fill_keeps_target_pod_healthy(self):
        """Fill part of the claim while keeping the target pod healthy."""
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        result = self.run_scenario(self.tmp_path, self.ns, overrides={"fill_percentage": 50, "duration": 5})
        assert_kraken_success(result, context=self.ns, tmp_path=self.tmp_path)
        assert_all_pods_running_and_ready(get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR), namespace=self.ns)
        assert len(before.items) == 1

    def test_missing_pvc_fails(self):
        """Fail when the scenario names a PVC that does not exist."""
        result = self.run_scenario(self.tmp_path, self.ns, overrides={"pvc_name": "missing-pvc"}, config_filename="missing.yaml")
        assert_kraken_failure(result, context="missing PVC", tmp_path=self.tmp_path)
