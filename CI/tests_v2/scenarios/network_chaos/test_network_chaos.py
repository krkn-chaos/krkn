"""Integration coverage for the legacy node network chaos plugin."""

import subprocess
import time

import pytest

from lib.base import BaseScenarioTest, KRAKEN_PROC_WAIT_TIMEOUT
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_success,
    clean_node_tc_rules,
    container_runtime,
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

    @staticmethod
    def _collect_background(proc):
        """Collect a background Kraken run, killing it if collection times out."""
        try:
            stdout, stderr = proc.communicate(
                timeout=max(KRAKEN_PROC_WAIT_TIMEOUT, 180)
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        return subprocess.CompletedProcess(
            proc.args, proc.returncode, stdout, stderr
        )

    @staticmethod
    def _tc_qdisc_output(node):
        """Read effective qdisc state from a local KinD node container."""
        runtime = container_runtime()
        if not runtime:
            pytest.skip("Container runtime unavailable for tc-state assertion")
        try:
            result = subprocess.run(
                [runtime, "exec", node, "tc", "qdisc", "show", "dev", "eth0"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            pytest.fail(f"Could not inspect tc state on {node}: {exc}")
        assert result.returncode == 0, result.stderr
        return result.stdout or ""

    def _wait_for_netem(self, node, proc, timeout=120):
        """Poll until the legacy run has installed an effective netem qdisc."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            output = self._tc_qdisc_output(node)
            if "netem" in output.lower():
                return output
            if proc.poll() is not None:
                break
            time.sleep(1)
        return ""

    def _wait_for_no_netem(self, node, timeout=60):
        """Poll until cleanup removes the effective netem qdisc."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            output = self._tc_qdisc_output(node)
            if "netem" not in output.lower():
                return output
            time.sleep(1)
        return ""

    @pytest.mark.no_workload
    @pytest.mark.kind_only
    def test_bandwidth_targeting_worker_and_cleanup(self, kubectl):
        """Observe an active netem qdisc, then verify jobs and tc state are cleaned."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node")
        before = kubectl(["get", "pods,jobs", "-n", "default", "-o", "name"])
        assert before.returncode == 0, before.stderr

        node = nodes[-1]
        clean_node_tc_rules(node)
        proc = self._run_background(
            {"node_name": node, "egress": {"bandwidth": "100mbit"}}, "bandwidth"
        )
        try:
            active_qdisc = self._wait_for_netem(node, proc)
            assert active_qdisc, (
                f"Expected effective netem qdisc on {node} while bandwidth chaos ran"
            )
        finally:
            result = self._collect_background(proc)
        assert_kraken_success(result, context=f"node={node}", tmp_path=self.tmp_path)
        assert wait_node_ready(self.k8s_core, node, 120)
        assert self._wait_for_no_netem(node), (
            f"Legacy network chaos left an effective netem qdisc on {node}"
        )

        after = kubectl(["get", "pods,jobs", "-n", "default", "-o", "name"])
        assert after.returncode == 0, after.stderr
        created = set(after.stdout.splitlines()) - set(before.stdout.splitlines())
        leaked = sorted(
            name for name in created
            if name.startswith(("pod/fedtools-", "job/chaos-"))
        )
        assert not leaked, f"Legacy network chaos resources leaked in default: {leaked}"

    @pytest.mark.no_workload
    @pytest.mark.kind_only
    def test_latency_only_variant(self):
        """Observe an effective netem qdisc during latency-only node chaos."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node")
        node = nodes[0]
        clean_node_tc_rules(node)
        proc = self._run_background(
            {"node_name": node, "egress": {"latency": "50ms"}}, "latency"
        )
        try:
            active_qdisc = self._wait_for_netem(node, proc)
            assert active_qdisc, (
                f"Expected effective netem qdisc on {node} while latency chaos ran"
            )
        finally:
            result = self._collect_background(proc)
        assert_kraken_success(result, context="latency variant", tmp_path=self.tmp_path)
        assert self._wait_for_no_netem(node), (
            f"Latency chaos left an effective netem qdisc on {node}"
        )

    @pytest.mark.no_workload
    def test_nonexistent_node_fails(self):
        """Fail when the requested node does not exist."""
        result = self._run({"node_name": "krkn-no-such-node", "egress": {"bandwidth": "100mbit"}}, "bad-node")
        assert_kraken_failure(result, context="invalid node", tmp_path=self.tmp_path)
