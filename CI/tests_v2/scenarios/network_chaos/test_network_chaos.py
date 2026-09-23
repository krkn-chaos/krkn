"""Integration coverage for the legacy node network chaos plugin."""

import pytest

from lib.base import BaseScenarioTest
from lib.utils import assert_kraken_failure, assert_kraken_success, schedulable_worker_nodes, wait_node_ready

@pytest.mark.functional
@pytest.mark.network_chaos
@pytest.mark.kind_only
@pytest.mark.xdist_group("network_chaos")
class TestNetworkChaos(BaseScenarioTest):
    """Exercise legacy node network chaos targeting, effects, and cleanup."""
    SCENARIO_NAME = "network_chaos"
    SCENARIO_TYPE = "network_chaos_scenarios"
    NAMESPACE_KEY_PATH = []

    def _scenario(self, overrides=None):
        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        scenario["network_chaos"].update(overrides or {})
        return scenario

    def _run(self, overrides=None, name="network_chaos.yaml"):
        path = self.write_scenario(self.tmp_path, self._scenario(overrides), suffix=name)
        config = self.build_config(self.SCENARIO_TYPE, str(path), filename=name + ".config.yaml")
        return self.run_kraken(config, timeout=300)

    @pytest.mark.no_workload
    def test_bandwidth_targeting_worker_and_cleanup(self, kubectl):
        """Verify worker targeting and cleanup of default-namespace resources."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node")
        before = kubectl(["get", "pods,jobs", "-n", "default", "-o", "name"])
        assert before.returncode == 0, before.stderr

        node = nodes[-1]
        result = self._run({"node_name": node, "egress": {"bandwidth": "100mbit"}}, "bandwidth")
        assert_kraken_success(result, context=f"node={node}", tmp_path=self.tmp_path)
        assert wait_node_ready(self.k8s_core, node, 120)

        after = kubectl(["get", "pods,jobs", "-n", "default", "-o", "name"])
        assert after.returncode == 0, after.stderr
        created = set(after.stdout.splitlines()) - set(before.stdout.splitlines())
        leaked = sorted(
            name for name in created
            if name.startswith(("pod/fedtools-", "job/chaos-"))
        )
        assert not leaked, f"Legacy network chaos resources leaked in default: {leaked}"

    @pytest.mark.no_workload
    def test_latency_only_variant(self):
        """Apply latency-only node chaos to a schedulable worker."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node")
        result = self._run({"node_name": nodes[0], "egress": {"latency": "50ms"}}, "latency")
        assert_kraken_success(result, context="latency variant", tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    def test_nonexistent_node_fails(self):
        """Fail when the requested node does not exist."""
        result = self._run({"node_name": "krkn-no-such-node", "egress": {"bandwidth": "100mbit"}}, "bad-node")
        assert_kraken_failure(result, context="invalid node", tmp_path=self.tmp_path)
