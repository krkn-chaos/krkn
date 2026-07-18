"""
Functional tests for node network chaos (network_chaos_ng_scenarios), migrated from
CI/tests/test_node_network_chaos.sh.

Node network chaos targets node network interfaces via a privileged helper pod
(prefix ``node-network-chaos-``). Tests use @pytest.mark.no_workload and verify
Krkn execution, targeting, safety guards, negative cases, and post-run cleanup
(tc rules removed, helper pod deleted, nodes Ready). Network SLO measurement is
out of scope.
"""

import copy
import re
import subprocess

import pytest
import yaml

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_marker,
    assert_kraken_success,
    assert_scenario_executed,
    clean_node_tc_rules,
    container_runtime,
    load_scenario_base,
    schedulable_worker_nodes,
    seed_node_complex_tc_rules,
    wait_for_no_pods_by_prefix,
    wait_node_ready,
)

CHAOS_POD_PREFIX = "node-network-chaos-"
KRAKEN_RUN_TIMEOUT = 300
NODE_READY_TIMEOUT = 120
CHAOS_POD_CLEANUP_TIMEOUT = 90
TEST_DURATION = 30


@pytest.mark.functional
@pytest.mark.node_network_chaos
class TestNodeNetworkChaos(BaseScenarioTest):
    """Node network chaos: packet loss, latency, bandwidth, direction, targeting, safety, cleanup."""

    SCENARIO_NAME = "node_network_chaos"
    SCENARIO_TYPE = "network_chaos_ng_scenarios"
    NAMESPACE_KEY_PATH = [0, "namespace"]
    NAMESPACE_IS_REGEX = False
    OVERRIDES_KEY_PATH = [0]

    def _scenario(self, namespace, overrides=None, drop=None):
        """Load scenario_base.yaml, patch namespace, then apply per-entry overrides."""
        scenario = copy.deepcopy(load_scenario_base(self.repo_root, self.SCENARIO_NAME))
        scenario[0]["namespace"] = namespace
        entry = scenario[0]
        for key in (drop or []):
            entry.pop(key, None)
        if overrides:
            entry.update(overrides)
        return scenario

    def _target_worker(self):
        """Return last schedulable worker — hog tests use nodes[0]; node chaos uses nodes[-1]."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node available for node network chaos")
        return nodes[-1]

    def _prepare_node_tc(self, overrides=None):
        """Reset leftover tc rules so force:false runs still inject and clean up."""
        o = overrides or {}
        target = o.get("target")
        if target:
            clean_node_tc_rules(target)
        elif o.get("label_selector"):
            for node in schedulable_worker_nodes(self.k8s_core):
                clean_node_tc_rules(node)

    def _run_chaos(
        self,
        namespace,
        overrides=None,
        drop=None,
        suffix="",
        config_name=None,
        *,
        prepare_tc=True,
    ):
        """Build scenario + config, run Krkn, return CompletedProcess.

        Set ``prepare_tc=False`` when the target is not a real KinD node container
        (negative tests) or when pre-seeded tc rules must be preserved (force:false guard).
        """
        if prepare_tc:
            self._prepare_node_tc(overrides)
        scenario = self._scenario(namespace, overrides=overrides, drop=drop)
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix=suffix)
        config_path = self.build_config(
            self.SCENARIO_TYPE,
            str(scenario_path),
            filename=config_name or f"node_network_chaos{suffix}_config.yaml",
        )
        return self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)

    def _assert_happy_run(self, result, context):
        """Common assertions for successful chaos injection + cleanup."""
        assert_kraken_success(result, context=context, tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=context, tmp_path=self.tmp_path
        )
        assert_kraken_marker(
            result, "removing tc rules", context=context, tmp_path=self.tmp_path
        )

    def _tc_qdisc_output(self, node: str) -> str:
        """Return ``tc qdisc show`` from the KinD node container, or empty if unavailable."""
        runtime = container_runtime()
        if not runtime:
            return ""
        try:
            proc = subprocess.run(
                [runtime, "exec", node, "tc", "qdisc", "show"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:  # noqa: BLE001
            return ""
        if proc.returncode != 0:
            return ""
        return proc.stdout or ""

    def _assert_no_residual_netem(self, node: str, context: str) -> None:
        """Assert Krkn netem/tbf rules are not left on the node (best-effort on KinD)."""
        output = self._tc_qdisc_output(node)
        if not output:
            pytest.skip(f"Container runtime unavailable; cannot verify tc rules on {node}")
        assert "netem" not in output.lower(), (
            f"Residual netem tc rules on node {node} after scenario ({context}):\n{output}"
        )

    def _assert_all_nodes_ready(self) -> None:
        """Assert every cluster node reports Ready."""
        for node in [n.metadata.name for n in self.k8s_core.list_node().items]:
            assert wait_node_ready(self.k8s_core, node, timeout=NODE_READY_TIMEOUT), (
                f"Node {node} not Ready within {NODE_READY_TIMEOUT}s after scenario"
            )

    @pytest.mark.no_workload
    @pytest.mark.order(1)
    def test_packet_loss_applied_and_cleanup(self):
        """Happy path: loss rule applied to target node, runs test_duration, cleans up, exits 0."""
        node = self._target_worker()
        ns = self.ns
        result = self._run_chaos(
            ns,
            {
                "target": node,
                "loss": "10",
                "test_duration": TEST_DURATION,
                "latency": "0s",
                "bandwidth": "1gbit",
                "force": False,
            },
            suffix="_packet_loss",
        )
        self._assert_happy_run(result, context=f"packet_loss node={node} ns={ns}")
        wait_for_no_pods_by_prefix(
            self.k8s_core, ns, CHAOS_POD_PREFIX, timeout=CHAOS_POD_CLEANUP_TIMEOUT
        )

    @pytest.mark.no_workload
    @pytest.mark.order(2)
    def test_latency_ingress_egress(self):
        """Latency injection on node network with ingress and egress enabled."""
        node = self._target_worker()
        ns = self.ns
        result = self._run_chaos(
            ns,
            {
                "target": node,
                "latency": "100ms",
                "loss": "0",
                "ingress": True,
                "egress": True,
                "test_duration": TEST_DURATION,
            },
            suffix="_latency",
        )
        self._assert_happy_run(result, context=f"latency node={node} ns={ns}")

    @pytest.mark.no_workload
    @pytest.mark.order(3)
    def test_bandwidth_limit(self):
        """Bandwidth throttle applied to node network interfaces."""
        node = self._target_worker()
        ns = self.ns
        result = self._run_chaos(
            ns,
            {
                "target": node,
                "bandwidth": "1mbit",
                "loss": "0",
                "latency": "0s",
                "test_duration": TEST_DURATION,
            },
            suffix="_bandwidth",
        )
        self._assert_happy_run(result, context=f"bandwidth node={node} ns={ns}")

    @pytest.mark.no_workload
    @pytest.mark.order(4)
    def test_egress_only_direction(self):
        """Only outbound (egress) traffic from the node is affected."""
        node = self._target_worker()
        ns = self.ns
        result = self._run_chaos(
            ns,
            {
                "target": node,
                "ingress": False,
                "egress": True,
                "test_duration": TEST_DURATION,
            },
            suffix="_egress_only",
        )
        self._assert_happy_run(result, context=f"egress_only node={node} ns={ns}")

    @pytest.mark.no_workload
    @pytest.mark.order(5)
    def test_instance_count_with_label_selector(self):
        """When multiple nodes match, only instance_count nodes are targeted.

        KinD workers often lack ``node-role.kubernetes.io/worker`` (role column is
        empty), so the selector is built from known worker hostnames — same label
        node_scenarios uses for real targeting.
        """
        workers = schedulable_worker_nodes(self.k8s_core)
        if len(workers) < 2:
            pytest.skip("Need at least two worker nodes to verify instance_count limiting")
        # Match all schedulable workers; KinD does not set node-role.kubernetes.io/worker.
        label_selector = "kubernetes.io/hostname in (" + ",".join(workers) + ")"
        ns = self.ns
        result = self._run_chaos(
            ns,
            {
                "label_selector": label_selector,
                "instance_count": 1,
                "target": "",
                "test_duration": TEST_DURATION,
            },
            suffix="_instance_count",
        )
        self._assert_happy_run(result, context=f"instance_count ns={ns}")
        combined = f"{result.stdout or ''}\n{result.stderr or ''}"
        targeting_hits = len(re.findall(r"targeting node ", combined))
        assert targeting_hits == 1, (
            f"Expected exactly 1 targeted node (instance_count=1), saw {targeting_hits} "
            f"'targeting node' log lines"
        )

    @pytest.mark.no_workload
    @pytest.mark.order(6)
    def test_force_false_skips_injection_when_tc_rules_exist(self, request):
        """With force: false, existing complex tc rules warn and skip injection (no override)."""
        node = self._target_worker()
        request.addfinalizer(lambda: clean_node_tc_rules(node))
        if not seed_node_complex_tc_rules(node):
            pytest.skip("Container runtime unavailable; cannot seed tc rules on KinD node")
        ns = self.ns
        result = self._run_chaos(
            ns,
            {"target": node, "force": False, "test_duration": TEST_DURATION},
            suffix="_force_false",
            prepare_tc=False,
        )
        assert_kraken_success(
            result, context=f"force_false node={node} ns={ns}", tmp_path=self.tmp_path
        )
        combined = f"{result.stdout or ''}\n{result.stderr or ''}"
        assert_kraken_marker(
            result,
            "already has tc rules set for",
            context=f"force_false node={node}",
            tmp_path=self.tmp_path,
        )
        assert "removing tc rules" not in combined, (
            "force=false must not inject or clean tc when complex rules already exist"
        )
        assert "forcing node network configuration override" not in combined

    @pytest.mark.no_workload
    @pytest.mark.order(7)
    def test_nonexistent_target_node_fails(self):
        """Krkn fails gracefully when the specified node does not exist."""
        ns = self.ns
        result = self._run_chaos(
            ns,
            {"target": "fake-node-xyz", "test_duration": TEST_DURATION},
            suffix="_bad_target",
            prepare_tc=False,
        )
        assert_kraken_failure(
            result, context="nonexistent target node", tmp_path=self.tmp_path
        )

    @pytest.mark.no_workload
    @pytest.mark.order(8)
    def test_no_nodes_matching_selector_warns(self):
        """Empty selector match logs 'no targets found' and Krkn exits 0."""
        ns = self.ns
        result = self._run_chaos(
            ns,
            {
                "label_selector": "role=nonexistent",
                "target": "",
                "test_duration": TEST_DURATION,
            },
            suffix="_empty_selector",
        )
        assert_kraken_success(
            result, context="no matching selector", tmp_path=self.tmp_path
        )
        assert_kraken_marker(
            result, "no targets found", context="empty selector", tmp_path=self.tmp_path
        )

    @pytest.mark.no_workload
    @pytest.mark.order(9)
    def test_invalid_config_format_fails(self):
        """Scenario YAML not in list format makes Krkn exit 1."""
        ns = self.ns
        bad_scenario = {"id": "node_network_chaos", "namespace": ns, "target": "any"}
        scenario_path = self.tmp_path / "node_network_chaos_bad_format.yaml"
        scenario_path.write_text(yaml.dump(bad_scenario, default_flow_style=False))
        config_path = self.build_config(
            self.SCENARIO_TYPE,
            str(scenario_path),
            filename="node_network_chaos_bad_format_config.yaml",
        )
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_failure(
            result, context="invalid config format", tmp_path=self.tmp_path
        )
        assert_kraken_marker(
            result,
            "network chaos scenario config must be a list of objects",
            context="invalid config format",
            tmp_path=self.tmp_path,
        )

    @pytest.mark.no_workload
    @pytest.mark.order(10)
    def test_network_rules_removed_post_run(self):
        """No residual netem tc rules remain on the node after the scenario."""
        node = self._target_worker()
        ns = self.ns
        result = self._run_chaos(
            ns,
            {
                "target": node,
                "loss": "10",
                "latency": "50ms",
                "test_duration": TEST_DURATION,
            },
            suffix="_tc_cleanup",
        )
        self._assert_happy_run(result, context=f"tc_cleanup node={node} ns={ns}")
        self._assert_no_residual_netem(node, context="post-run tc check")

    @pytest.mark.no_workload
    @pytest.mark.order(11)
    def test_cluster_health_preserved(self):
        """All nodes return to Ready after node network chaos."""
        node = self._target_worker()
        ns = self.ns
        result = self._run_chaos(
            ns,
            {"target": node, "test_duration": TEST_DURATION},
            suffix="_cluster_health",
        )
        self._assert_happy_run(result, context=f"cluster_health node={node} ns={ns}")
        self._assert_all_nodes_ready()

    @pytest.mark.no_workload
    @pytest.mark.order(12)
    def test_chaos_helper_pod_cleaned_up(self):
        """krkn-network-chaos helper pod (node-network-chaos-*) is deleted after scenario."""
        node = self._target_worker()
        ns = self.ns
        result = self._run_chaos(
            ns,
            {"target": node, "test_duration": TEST_DURATION},
            suffix="_pod_cleanup",
        )
        self._assert_happy_run(result, context=f"pod_cleanup node={node} ns={ns}")
        wait_for_no_pods_by_prefix(
            self.k8s_core, ns, CHAOS_POD_PREFIX, timeout=CHAOS_POD_CLEANUP_TIMEOUT
        )
