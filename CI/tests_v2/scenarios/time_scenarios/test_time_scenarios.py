"""Pod and node time-action integration coverage."""
import copy

import pytest

from lib.base import BaseScenarioTest
from lib.utils import assert_kraken_failure, assert_kraken_success, schedulable_worker_nodes, wait_node_ready

@pytest.mark.functional
@pytest.mark.time_scenarios
class TestTimeScenarios(BaseScenarioTest):
    """Exercise supported pod/node clock actions and invalid-action handling."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/time_scenarios/resource.yaml"
    LABEL_SELECTOR = "app=krkn-time-target"
    SCENARIO_NAME = "time_scenarios"
    SCENARIO_TYPE = "time_scenarios"
    NAMESPACE_KEY_PATH = ["time_scenarios", 0, "namespace"]

    def _run(self, entry, name):
        data = copy.deepcopy(self.load_and_patch_scenario(self.repo_root, self.ns))
        data["time_scenarios"][0].update(entry)
        path = self.write_scenario(self.tmp_path, data, suffix=name)
        config = self.build_config(self.SCENARIO_TYPE, str(path), filename=name + ".config.yaml")
        return self.run_kraken(config, timeout=300)

    @pytest.mark.kind_only
    def test_pod_time_skew_succeeds(self):
        """Apply a pod-level time skew and expect successful cleanup."""
        result = self._run({"action": "skew_time", "object_type": "pod", "label_selector": self.LABEL_SELECTOR, "container_name": ""}, "pod")
        assert_kraken_success(result, context=self.ns, tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    @pytest.mark.kind_only
    def test_worker_date_skew_succeeds(self):
        """Apply a worker-node date skew and verify the node returns Ready."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node")
        result = self._run({"action": "skew_date", "object_type": "node", "label_selector": f"kubernetes.io/hostname={nodes[0]}"}, "node")
        assert_kraken_success(result, context=nodes[0], tmp_path=self.tmp_path)
        assert wait_node_ready(self.k8s_core, nodes[0], 120)

    def test_invalid_action_fails(self):
        """Reject a time action that the plugin does not support."""
        result = self._run({"action": "not_an_action", "object_type": "pod", "label_selector": self.LABEL_SELECTOR}, "invalid")
        assert_kraken_failure(result, context="invalid time action", tmp_path=self.tmp_path)
