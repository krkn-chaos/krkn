"""
Functional tests for node chaos scenarios (node_scenarios), migrated from the legacy
CI/tests/test_node.sh.

Node scenarios are destructive at the *node* level: Krkn stops, starts, or reboots the
container that backs a Kubernetes node. On KinD each node is a Docker (or Podman) container,
so these tests use cloud_type=docker and target a *worker* node only — never the control
plane. They use @pytest.mark.no_workload (no app deployment is needed) and verify action
execution (reboot, stop/start), node-name vs label-selector targeting, node recovery, the
control-plane safety guard, and graceful failure on invalid selector/node/action, missing
actions, and unsupported cloud type.

Parallelism note: stopping/rebooting a worker is cluster-wide disruption. When the suite runs
with `-n auto`, other tests scheduled on the same worker may be briefly affected. On a
multi-worker cluster (CI provisions two workers via the repo-root kind-config.yml) the
destructive tests target the *last* schedulable worker while hog tests target the *first*, so
they don't share a node; on a single-worker cluster (the kind-config-dev.yml local default)
both resolve to the same node and overlap is only mitigated by test ordering. Either way the
finalizer restarts the node container and waits for it to become Ready again before returning.
See CI/tests_v2/README.md.
"""

import copy

import pytest

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_container_cycled,
    assert_kraken_failure,
    assert_kraken_marker,
    assert_kraken_success,
    container_started_at,
    ensure_node_container_running,
    load_scenario_base,
    schedulable_worker_nodes,
    wait_node_ready,
)

KRAKEN_RUN_TIMEOUT = 300
NODE_READY_TIMEOUT = 180


@pytest.mark.functional
@pytest.mark.node_scenarios
class TestNodeScenarios(BaseScenarioTest):
    """Node chaos scenarios: reboot and stop/start a KinD worker, plus targeting, safety, and negative cases."""

    SCENARIO_NAME = "node_scenarios"
    SCENARIO_TYPE = "node_scenarios"
    NAMESPACE_KEY_PATH = []
    NAMESPACE_IS_REGEX = False

    def _scenario(self, overrides=None, drop=None):
        """Load scenario_base.yaml and patch its single node_scenarios entry (drop keys, then apply overrides)."""
        scenario = copy.deepcopy(load_scenario_base(self.repo_root, self.SCENARIO_NAME))
        node = scenario["node_scenarios"][0]
        for key in (drop or []):
            node.pop(key, None)
        if overrides:
            node.update(overrides)
        return scenario

    def _target_worker(self, request):
        """Pick the last schedulable worker (hog tests use the first) and register a restore finalizer."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node available for node scenario targeting")
        node = nodes[-1]
        request.addfinalizer(lambda: ensure_node_container_running(node, self.k8s_core))
        return node

    @pytest.mark.no_workload
    @pytest.mark.order(1)
    def test_node_reboot_targets_node_name_and_recovers(self, request):
        """Happy path: node_reboot_scenario targeted by node_name reboots the worker container.

        Krkn runs with kube_check disabled: its in-process wait for the node to flip
        Unknown->Ready is brittle behind the multi-control-plane KinD API load balancer, which
        surfaces transient "Response ended prematurely" connection drops as a hard scenario
        failure. Real disruption is instead proven deterministically by the node container's
        StartedAt advancing, and recovery by the node returning Ready.
        """
        node = self._target_worker(request)
        scenario = self._scenario(
            {
                "actions": ["node_reboot_scenario"],
                "node_name": node,
                "cloud_type": "docker",
                "kube_check": False,
                "timeout": 120,
            },
            drop=["label_selector"],
        )
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_reboot")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="node_reboot_config.yaml"
        )
        started_before = container_started_at(node)
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_success(result, context=f"node_reboot node={node}", tmp_path=self.tmp_path)
        assert_kraken_marker(
            result, "node_reboot_scenario has been successfully injected",
            context=f"node={node}", tmp_path=self.tmp_path,
        )
        assert_container_cycled(node, started_before, "reboot")
        assert wait_node_ready(self.k8s_core, node, timeout=NODE_READY_TIMEOUT), (
            f"Node {node} did not return Ready within {NODE_READY_TIMEOUT}s after reboot"
        )

    @pytest.mark.no_workload
    @pytest.mark.order(2)
    def test_node_stop_start_targets_label_selector_and_recovers(self, request):
        """Happy path: node_stop_start_scenario targeted by label_selector stops then starts the worker.

        Like the reboot happy path, Krkn runs with kube_check disabled (the in-process
        Unknown->Ready wait is brittle behind the multi-control-plane KinD API load balancer).
        Disruption is proven by the node container's StartedAt advancing and recovery by the
        node returning Ready.
        """
        node = self._target_worker(request)
        scenario = self._scenario(
            {
                "actions": ["node_stop_start_scenario"],
                "label_selector": f"kubernetes.io/hostname={node}",
                "instance_count": 1,
                "cloud_type": "docker",
                "kube_check": False,
                "duration": 5,
                "timeout": 120,
            },
            drop=["node_name"],
        )
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_stop_start")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="node_stop_start_config.yaml"
        )
        started_before = container_started_at(node)
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_success(result, context=f"node_stop_start node={node}", tmp_path=self.tmp_path)
        assert_kraken_marker(
            result, "node_start_scenario has been successfully injected",
            context=f"node={node}", tmp_path=self.tmp_path,
        )
        assert_container_cycled(node, started_before, "stop/start")
        assert wait_node_ready(self.k8s_core, node, timeout=NODE_READY_TIMEOUT), (
            f"Node {node} did not return Ready within {NODE_READY_TIMEOUT}s after stop/start"
        )

    @pytest.mark.no_workload
    @pytest.mark.order(3)
    def test_invalid_label_selector_fails(self):
        """Negative: a label_selector matching zero nodes makes Krkn fail (no Ready nodes to act on)."""
        scenario = self._scenario(
            {
                "actions": ["node_stop_start_scenario"],
                "label_selector": "kubernetes.io/hostname=krkn-nonexistent-node-zzz",
                "instance_count": 1,
                "cloud_type": "docker",
            },
            drop=["node_name"],
        )
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_bad_selector")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="node_bad_selector_config.yaml"
        )
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_failure(result, context="invalid label_selector", tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    @pytest.mark.order(4)
    def test_invalid_node_name_fails(self):
        """Negative: a node_name that does not exist (not a killable node) makes Krkn fail."""
        scenario = self._scenario(
            {
                "actions": ["node_stop_start_scenario"],
                "node_name": "krkn-nonexistent-node-zzz",
                "cloud_type": "docker",
            },
            drop=["label_selector"],
        )
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_bad_node")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="node_bad_node_config.yaml"
        )
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_failure(result, context="invalid node_name", tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    @pytest.mark.order(5)
    def test_missing_actions_fails(self):
        """Negative: an entry without `actions` makes Krkn fail fast (actions must be defined and non-empty)."""
        scenario = self._scenario(drop=["actions", "node_name"])
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_no_actions")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="node_no_actions_config.yaml"
        )
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_failure(result, context="missing actions", tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    @pytest.mark.order(6)
    def test_unsupported_cloud_type_fails(self):
        """Negative: an unsupported cloud_type makes Krkn fail when building the node scenario object."""
        scenario = self._scenario(
            {
                "actions": ["node_stop_start_scenario"],
                "label_selector": "node-role.kubernetes.io/worker=",
                "cloud_type": "krkn-unsupported-cloud",
            },
            drop=["node_name"],
        )
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_bad_cloud")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="node_bad_cloud_config.yaml"
        )
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_failure(result, context="unsupported cloud_type", tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    @pytest.mark.order(7)
    def test_unknown_action_is_skipped(self, request):
        """Negative-ish: an unrecognized action is skipped (logged, no node touched) and Krkn still exits 0."""
        node = self._target_worker(request)
        scenario = self._scenario(
            {
                "actions": ["node_bogus_scenario"],
                "label_selector": f"kubernetes.io/hostname={node}",
                "instance_count": 1,
                "cloud_type": "docker",
                "kube_check": False,
            },
            drop=["node_name"],
        )
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_unknown_action")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="node_unknown_action_config.yaml"
        )
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_success(result, context="unknown action", tmp_path=self.tmp_path)
        assert_kraken_marker(
            result, "There is no node action that matches",
            context="unknown action", tmp_path=self.tmp_path,
        )

    @pytest.mark.no_workload
    @pytest.mark.order(8)
    def test_control_plane_excluded_from_targeting(self):
        """Safety guard: control-plane/master nodes are never returned by the worker-targeting helper the destructive tests use."""
        all_nodes = self.k8s_core.list_node().items
        control_plane = [
            n.metadata.name for n in all_nodes
            if {"node-role.kubernetes.io/control-plane", "node-role.kubernetes.io/master"}
            & set((n.metadata.labels or {}).keys())
        ]
        if not control_plane:
            pytest.skip("Cluster has no labeled control-plane node to assert exclusion against")
        workers = schedulable_worker_nodes(self.k8s_core)
        overlap = set(control_plane) & set(workers)
        assert not overlap, (
            f"Control-plane node(s) {sorted(overlap)} must never be selected as a destructive "
            f"node-scenario target; worker set was {workers}"
        )
