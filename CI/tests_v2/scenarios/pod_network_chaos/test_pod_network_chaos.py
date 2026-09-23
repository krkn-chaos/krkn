"""Pod network impairment lifecycle tests."""
import pytest

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_failure,
    assert_kraken_success,
    assert_scenario_executed,
    get_pods_list,
)

@pytest.mark.functional
@pytest.mark.pod_network_chaos
@pytest.mark.kind_only
@pytest.mark.xdist_group("pod_network_chaos")
class TestPodNetworkChaos(BaseScenarioTest):
    """Apply pod-level network impairment and verify recovery and invalid-target handling."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_network_chaos/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pod-network-chaos-target"
    SCENARIO_NAME = "pod_network_chaos"
    SCENARIO_TYPE = "network_chaos_ng_scenarios"
    NAMESPACE_KEY_PATH = [0, "namespace"]
    OVERRIDES_KEY_PATH = [0]

    def _target(self):
        pods = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR).items
        assert pods, "network target did not become ready"
        return pods[0].metadata.name

    def test_latency_loss_and_recovery(self):
        """Apply pod network latency/loss and confirm the target workload recovers."""
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        result = self.run_scenario(self.tmp_path, self.ns, overrides={"target": self._target(), "test_duration": 20, "latency": "100ms", "loss": "10"})
        assert_kraken_success(result, context=self.ns, tmp_path=self.tmp_path)
        assert_scenario_executed(result, self.SCENARIO_NAME, context=self.ns, tmp_path=self.tmp_path)
        after = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        assert_all_pods_running_and_ready(after, namespace=self.ns)
        assert len(after.items) == len(before.items)

    def test_nonexistent_target_fails(self):
        """Reject a pod target that does not exist."""
        result = self.run_scenario(self.tmp_path, self.ns, overrides={"target": "no-such-pod", "test_duration": 5}, config_filename="bad-target.yaml")
        assert_kraken_failure(result, context="bad pod network target", tmp_path=self.tmp_path)
