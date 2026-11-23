"""Integration coverage for the legacy node network chaos plugin."""

import pytest

from lib.base import BaseScenarioTest
from lib.network import (
    collect_kraken_background,
    node_tc_qdisc_output,
    wait_for_netem,
    wait_for_no_netem,
)
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_success,
    clean_node_tc_rules,
    schedulable_worker_nodes,
    wait_node_ready,
)


@pytest.mark.functional
@pytest.mark.network_chaos
@pytest.mark.xdist_group("node-resource-chaos")
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

    def _run_background(self, overrides=None, name="network_chaos.yaml"):
        path = self.write_scenario(self.tmp_path, self._scenario(overrides), suffix=name)
        config = self.build_config(
            self.SCENARIO_TYPE, str(path), filename=name + ".config.yaml"
        )
        return self.run_kraken_background(config)

    @pytest.mark.no_workload
    @pytest.mark.kind_only
    @pytest.mark.parametrize(
        "egress_variant",
        [
            pytest.param({"bandwidth": "100mbit"}, id="bandwidth"),
            pytest.param({"latency": "50ms"}, id="latency"),
        ],
    )
    def test_netem_applied_and_cleaned(self, kubectl, egress_variant):
        """Observe an active netem qdisc during chaos, then verify full cleanup.

        Carries every assertion of both original variant tests: netem present
        during chaos, exit 0, node Ready afterwards, netem gone, and no leaked
        fedtools-/chaos- resources in the default namespace.
        """
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node")
        node = nodes[-1]
        if node_tc_qdisc_output(node, dev="eth0") is None:
            pytest.skip("Container runtime unavailable for tc-state assertion")
        before = kubectl(["get", "pods,jobs", "-n", "default", "-o", "name"])
        assert before.returncode == 0, before.stderr
        variant_id = next(iter(egress_variant))
        clean_node_tc_rules(node)
        proc = self._run_background(
            {"node_name": node, "egress": egress_variant}, variant_id
        )
        try:
            active_qdisc = wait_for_netem(node, proc, dev="eth0")
            assert active_qdisc, (
                f"Expected effective netem qdisc on {node} while {variant_id} chaos ran"
            )
        finally:
            result = collect_kraken_background(proc)
        assert_kraken_success(
            result, context=f"node={node} variant={variant_id}", tmp_path=self.tmp_path
        )
        assert wait_node_ready(self.k8s_core, node, 120)
        assert wait_for_no_netem(node, dev="eth0"), (
            f"Legacy network chaos left an effective netem qdisc on {node}"
        )

        after = kubectl(["get", "pods,jobs", "-n", "default", "-o", "name"])
        assert after.returncode == 0, after.stderr
        created = set(after.stdout.splitlines()) - set(before.stdout.splitlines())
        leaked = sorted(
            name
            for name in created
            if name.startswith(("pod/fedtools-", "job/chaos-"))
        )
        assert not leaked, f"Legacy network chaos resources leaked in default: {leaked}"

    @pytest.mark.no_workload
    def test_nonexistent_node_fails(self):
        """Fail when the requested node does not exist."""
        result = self._run({"node_name": "krkn-no-such-node", "egress": {"bandwidth": "100mbit"}}, "bad-node")
        assert_kraken_failure(result, context="invalid node", tmp_path=self.tmp_path)
