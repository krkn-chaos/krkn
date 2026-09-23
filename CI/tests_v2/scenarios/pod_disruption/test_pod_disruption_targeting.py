"""Node-scoped pod disruption targeting without cluster-system workloads."""
import pytest

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_success,
    assert_scenario_executed,
    get_pods_list,
    pod_uids,
    schedulable_worker_nodes,
)

@pytest.mark.functional
@pytest.mark.pod_disruption
class TestPodDisruptionTargeting(BaseScenarioTest):
    """Check worker-scoped victim selection and successful pod recovery."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_disruption/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pod-disruption-target"
    SCENARIO_NAME = "pod_disruption"
    SCENARIO_TYPE = "pod_disruption_scenarios"
    NAMESPACE_KEY_PATH = [0, "config", "namespace_pattern"]
    NAMESPACE_IS_REGEX = True

    def test_worker_selector_limits_victim_to_selected_node(self):
        """Kill a pod on the selected worker and verify its replacement recovers."""
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        if not before.items or not before.items[0].spec.node_name:
            pytest.skip("Target workload is not scheduled on a worker node")
        target = before.items[0].spec.node_name
        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        config = scenario[0]["config"]
        config.update({"node_label_selector": f"kubernetes.io/hostname={target}", "kill": 1})
        path = self.write_scenario(self.tmp_path, scenario, suffix="-node-target")
        result = self.run_kraken(self.build_config(self.SCENARIO_TYPE, str(path), filename="node-target.yaml"))
        assert_kraken_success(result, context=f"node={target}", tmp_path=self.tmp_path)
        assert_scenario_executed(result, self.SCENARIO_NAME, context=self.ns, tmp_path=self.tmp_path)
        after = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        assert set(pod_uids(before)) != set(pod_uids(after))
        assert_all_pods_running_and_ready(after, namespace=self.ns)
