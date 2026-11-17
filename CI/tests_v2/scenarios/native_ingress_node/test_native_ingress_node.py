"""Functional coverage for the native node ingress scenario runner."""

import pytest

from lib.base import BaseScenarioTest
from lib.network import (
    collect_kraken_background,
    node_tc_qdisc_output,
    wait_for_netem,
    wait_for_no_netem,
)
from lib.utils import assert_kraken_success, schedulable_worker_nodes


@pytest.mark.functional
@pytest.mark.native_ingress_node
@pytest.mark.kind_only
@pytest.mark.no_workload
@pytest.mark.xdist_group("node-resource-chaos")
class TestNativeIngressNode(BaseScenarioTest):
    SCENARIO_NAME = "native_ingress_node"
    SCENARIO_TYPE = "ingress_node_scenarios"

    @pytest.mark.timeout(420)
    def test_ingress_latency_applied_and_cleaned(self):
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node")
        node = nodes[-1]
        if node_tc_qdisc_output(node) is None:
            pytest.skip("Cannot inspect tc state in the local node container")
        assert wait_for_no_netem(node, timeout=30), (
            f"Existing netem rule on {node}; cannot establish a clean baseline"
        )

        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        scenario[0]["config"]["node_interface_name"] = {node: ["eth0"]}
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        config = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="native_ingress_node_config.yaml",
        )

        proc = self.run_kraken_background(config)
        try:
            observed = wait_for_netem(node, proc, timeout=150)
        finally:
            result = collect_kraken_background(proc)
        assert_kraken_success(result, context=f"native ingress on {node}", tmp_path=self.tmp_path)
        assert observed, f"No ingress netem qdisc observed on {node}"
        assert '"output_id": "success"' in result.stdout + result.stderr
        assert wait_for_no_netem(node, timeout=90), f"Ingress netem rule remained on {node}"
