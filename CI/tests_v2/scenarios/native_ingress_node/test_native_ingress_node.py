"""KinD coverage for ingress shaping and pre-existing qdisc ownership."""

import subprocess
import uuid

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
    container_runtime,
    schedulable_worker_nodes,
)


@pytest.mark.functional
@pytest.mark.native_ingress_node
@pytest.mark.kind_only
@pytest.mark.no_workload
@pytest.mark.xdist_group("node-resource-chaos")
class TestNativeIngressNode(BaseScenarioTest):
    SCENARIO_NAME = "native_ingress_node"
    SCENARIO_TYPE = "ingress_node_scenarios"

    @pytest.fixture
    def node_veth(self, k8s_core):
        nodes = schedulable_worker_nodes(k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node")
        node = nodes[-1]
        runtime = container_runtime()
        if not runtime or node_tc_qdisc_output(node) is None:
            pytest.skip("Cannot inspect tc state in the local node container")

        suffix = uuid.uuid4().hex[:8]
        interface, peer = f"krkn{suffix}a", f"krkn{suffix}b"
        created = subprocess.run(
            [runtime, "exec", node, "ip", "link", "add", interface,
             "type", "veth", "peer", "name", peer],
            capture_output=True, text=True, timeout=30,
        )
        assert created.returncode == 0, created.stderr
        try:
            enabled = subprocess.run(
                [runtime, "exec", node, "ip", "link", "set", interface, "up"],
                capture_output=True, text=True, timeout=30,
            )
            assert enabled.returncode == 0, enabled.stderr
            yield node, interface, runtime
        finally:
            subprocess.run(
                [runtime, "exec", node, "ip", "link", "del", interface],
                capture_output=True, text=True, timeout=30,
            )

    def scenario_config(self, node, interface):
        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        scenario[0]["config"]["node_interface_name"] = {node: [interface]}
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        return self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="native_ingress_node_config.yaml",
        )

    @pytest.mark.timeout(420)
    def test_ingress_latency_applied_and_cleaned(self, node_veth):
        node, interface, _ = node_veth
        assert wait_for_no_netem(node, timeout=30), f"Existing netem rule on {node}"
        proc = self.run_kraken_background(self.scenario_config(node, interface))
        try:
            observed = wait_for_netem(node, proc, timeout=150)
        finally:
            result = collect_kraken_background(proc)

        assert_kraken_success(result, context=f"native ingress on {node}", tmp_path=self.tmp_path)
        assert observed, f"No ingress netem qdisc observed on {node}"
        assert "dev ifb0" in observed, observed
        assert '"output_id": "success"' in result.stdout + result.stderr
        assert wait_for_no_netem(node, timeout=90), f"Ingress netem rule remained on {node}"

    @pytest.mark.timeout(180)
    def test_existing_ingress_qdisc_is_preserved(self, node_veth):
        node, interface, runtime = node_veth
        created = subprocess.run(
            [runtime, "exec", node, "tc", "qdisc", "add", "dev", interface,
             "handle", "ffff:", "ingress"],
            capture_output=True, text=True, timeout=30,
        )
        assert created.returncode == 0, created.stderr
        try:
            result = self.run_kraken(self.scenario_config(node, interface))
            assert_kraken_failure(result, context="pre-existing ingress qdisc", tmp_path=self.tmp_path)
            assert "already has an ingress qdisc" in result.stdout + result.stderr
            assert "qdisc ingress" in node_tc_qdisc_output(node, dev=interface)
            filters = subprocess.run(
                [runtime, "exec", node, "tc", "filter", "show", "dev", interface,
                 "parent", "ffff:"],
                capture_output=True, text=True, timeout=30,
            )
            assert filters.returncode == 0, filters.stderr
            assert not filters.stdout.strip(), filters.stdout
        finally:
            subprocess.run(
                [runtime, "exec", node, "tc", "qdisc", "del", "dev", interface,
                 "handle", "ffff:", "ingress"],
                capture_output=True, text=True, timeout=30,
            )
