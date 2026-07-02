"""
Functional tests for pod_network_filter (network_chaos_ng_scenarios).

Migrated from CI/tests/test_pod_network_filter.sh. Validates filter rule lifecycle,
Krkn exit behavior, and cleanup — not packet-level drop semantics.
"""

import subprocess
import time

import pytest

from lib.base import BaseScenarioTest, KRAKEN_PROC_WAIT_TIMEOUT
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_failure,
    assert_kraken_success,
    assert_pod_count_unchanged,
    assert_scenario_executed,
    get_pods_list,
    list_pods_by_prefix,
    wait_for_no_pods_by_prefix,
)


@pytest.mark.functional
@pytest.mark.pod_network_filter
class TestPodNetworkFilter(BaseScenarioTest):
    """pod_network_filter: iptables port/protocol filtering on pod network namespaces."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_network_filter/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "test=pod-network-filter"
    SCENARIO_NAME = "pod_network_filter"
    SCENARIO_TYPE = "network_chaos_ng_scenarios"
    NAMESPACE_KEY_PATH = [0, "namespace"]
    NAMESPACE_IS_REGEX = False
    OVERRIDES_KEY_PATH = [0]

    HELPER_POD_PREFIX = "pod-filter-"

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _combined_output(result) -> str:
        return f"{result.stdout or ''}\n{result.stderr or ''}"

    def _target_pod(self) -> str:
        pods = get_pods_list(
            self.k8s_core, self.ns, "app=krkn-pod-network-filter-target"
        )
        assert pods.items, f"No target pod in namespace={self.ns}"
        return pods.items[0].metadata.name

    def _filter_kwargs(self, **overrides) -> dict:
        opts = {
            "label_selector": "",
            "instance_count": 1,
            "test_duration": 10,
            "ingress": False,
            "egress": True,
            "protocols": ["tcp"],
            "ports": [80],
        }
        opts.update(overrides)
        if opts.get("label_selector"):
            opts["target"] = ""
        elif "target" not in overrides:
            opts["target"] = self._target_pod()
        return opts

    def _run_filter(self, config_filename: str = "test_config.yaml", **overrides):
        return self.run_scenario(
            self.tmp_path,
            self.ns,
            overrides=self._filter_kwargs(**overrides),
            config_filename=config_filename,
        )

    def _run_and_assert_success(self, config_filename: str = "test_config.yaml", **overrides):
        ns = self.ns
        result = self._run_filter(config_filename=config_filename, **overrides)
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path
        )
        return result

    def _assert_pods_healthy(self, before):
        after = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=self.ns)
        assert_all_pods_running_and_ready(after, namespace=self.ns)

    # -- happy path (1–8) ----------------------------------------------

    @pytest.mark.order(1)
    def test_tcp_port_block_egress(self, wait_for_pods_running):
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        self._run_and_assert_success(
            config_filename="tcp_egress.yaml",
            protocols=["tcp"],
            ports=[80],
            egress=True,
            ingress=False,
        )
        wait_for_pods_running(self.ns, self.LABEL_SELECTOR, timeout=90)
        self._assert_pods_healthy(before)

    @pytest.mark.order(2)
    def test_udp_port_block(self):
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        self._run_and_assert_success(
            config_filename="udp_block.yaml",
            protocols=["udp"],
            ports=[53],
            egress=True,
            ingress=False,
        )
        self._assert_pods_healthy(before)

    @pytest.mark.order(3)
    def test_multiple_protocols_tcp_udp(self):
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        self._run_and_assert_success(
            config_filename="tcp_udp.yaml",
            protocols=["tcp", "udp"],
            ports=[53],
            egress=True,
            ingress=False,
        )
        self._assert_pods_healthy(before)

    @pytest.mark.order(4)
    def test_multiple_ports(self):
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        self._run_and_assert_success(
            config_filename="multi_port.yaml",
            protocols=["tcp"],
            ports=[80, 443, 8080],
            egress=True,
            ingress=False,
        )
        self._assert_pods_healthy(before)

    @pytest.mark.order(5)
    def test_ingress_direction(self):
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        self._run_and_assert_success(
            config_filename="ingress_only.yaml",
            protocols=["tcp"],
            ports=[80],
            ingress=True,
            egress=False,
        )
        self._assert_pods_healthy(before)

    @pytest.mark.order(6)
    def test_both_directions(self):
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        self._run_and_assert_success(
            config_filename="both_directions.yaml",
            protocols=["tcp"],
            ports=[80],
            ingress=True,
            egress=True,
        )
        self._assert_pods_healthy(before)

    @pytest.mark.order(7)
    def test_label_selector_targeting(self):
        nginx_pods = get_pods_list(self.k8s_core, self.ns, "app=nginx")
        assert len(nginx_pods.items) >= 2, (
            f"Expected >=2 nginx pods for label selector test (namespace={self.ns})"
        )
        result = self._run_and_assert_success(
            config_filename="label_selector.yaml",
            label_selector="app=nginx",
            instance_count=1,
            egress=True,
            ingress=False,
            protocols=["tcp"],
            ports=[80],
        )
        combined = self._combined_output(result)
        assert combined.count("creating workload to filter pod") == 1, (
            f"Expected exactly one filtered target (instance_count=1, namespace={self.ns})"
        )

    @pytest.mark.order(8)
    def test_duration_and_cleanup(self):
        result = self._run_and_assert_success(
            config_filename="duration.yaml",
            test_duration=30,
            protocols=["tcp"],
            ports=[80],
            egress=True,
            ingress=False,
        )
        combined = self._combined_output(result)
        assert "waiting 30 seconds before removing the iptables rules" in combined, (
            f"Expected duration wait log (namespace={self.ns})"
        )
        assert "removing iptables rules" in combined, (
            f"Expected iptables cleanup log (namespace={self.ns})"
        )

    # -- negative / failure-mode (9–11) --------------------------------

    def test_nonexistent_target_pod_fails(self):
        result = self._run_filter(
            config_filename="bad_target.yaml",
            target="fake-pod-xyz",
            label_selector="",
        )
        assert_kraken_failure(
            result, context=f"namespace={self.ns}", tmp_path=self.tmp_path
        )
        combined = self._combined_output(result).lower()
        assert "fake-pod-xyz" in combined
        assert "not found" in combined

    def test_no_matching_pods_for_label(self):
        result = self._run_filter(
            config_filename="no_label_match.yaml",
            label_selector="app=nonexistent",
        )
        assert_kraken_success(
            result, context=f"namespace={self.ns}", tmp_path=self.tmp_path
        )
        assert "no targets found" in self._combined_output(result).lower(), (
            f"Expected no-targets warning (namespace={self.ns})"
        )

    @pytest.mark.no_workload
    def test_invalid_config_structure_fails(self):
        invalid_path = self.tmp_path / "invalid_pod_network_filter.yaml"
        invalid_path.write_text("pod_network_filter:\n  namespace: default\n")
        config_path = self.build_config(
            self.SCENARIO_TYPE,
            str(invalid_path),
            filename="invalid_structure_config.yaml",
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(
            result, context="invalid scenario structure", tmp_path=self.tmp_path
        )
        assert "network chaos scenario config must be a list" in self._combined_output(result).lower()

    # -- cleanup verification (12–13) ----------------------------------

    def test_filter_rules_removed_after_scenario(self):
        """Rules are applied then removed; a second run succeeds (no stale state)."""
        ns = self.ns
        result = self._run_and_assert_success(
            config_filename="cleanup_rules_1.yaml",
            test_duration=12,
            protocols=["tcp"],
            ports=[80],
        )
        assert "removing iptables rules" in self._combined_output(result)
        wait_for_no_pods_by_prefix(
            self.k8s_core, ns, self.HELPER_POD_PREFIX, timeout=30
        )
        # Re-run: would fail or no-op silently if rules were left behind.
        self._run_and_assert_success(
            config_filename="cleanup_rules_2.yaml",
            test_duration=10,
            protocols=["tcp"],
            ports=[80],
        )

    def test_chaos_helper_pod_deleted(self):
        """pod-filter-* helper pod appears during the run and is removed afterward."""
        ns = self.ns
        scenario = self.load_and_patch_scenario(
            self.repo_root, ns, **self._filter_kwargs(test_duration=12)
        )
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_helper")
        config_path = self.build_config(
            self.SCENARIO_TYPE,
            str(scenario_path),
            filename="helper_lifecycle_config.yaml",
        )
        proc = self.run_kraken_background(config_path)
        try:
            deadline = time.monotonic() + 90
            helper_seen = False
            while time.monotonic() < deadline:
                if list_pods_by_prefix(self.k8s_core, ns, self.HELPER_POD_PREFIX):
                    helper_seen = True
                    break
                if proc.poll() is not None:
                    break
                time.sleep(1)
            assert helper_seen, (
                f"Expected {self.HELPER_POD_PREFIX}* helper pod during run (namespace={ns})"
            )
        finally:
            stdout, stderr = proc.communicate(timeout=KRAKEN_PROC_WAIT_TIMEOUT)
            result = subprocess.CompletedProcess(
                proc.args, proc.returncode, stdout, stderr
            )
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        wait_for_no_pods_by_prefix(
            self.k8s_core, ns, self.HELPER_POD_PREFIX, timeout=30
        )
