"""
Functional tests for the legacy network_chaos scenario (network_chaos_scenarios), migrated
from CI/tests/test_net_chaos.sh.

Legacy network chaos targets nodes (not workloads): Krkn deploys privileged hostNetwork
Jobs (name prefix "chaos-") on selected node(s) to apply tc netem egress shaping, then
deletes the jobs. A short-lived fedtools-* probe pod may be created to discover interfaces.
These tests use @pytest.mark.no_workload and verify Krkn exit codes, tc application/cleanup,
node targeting, serial execution, and graceful failure on invalid inputs.
"""

import copy
import logging
import time
import uuid
from contextlib import contextmanager

import pytest
from kubernetes import client
from kubernetes.stream import stream

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_marker,
    assert_kraken_success,
    assert_scenario_executed,
    load_scenario_base,
    schedulable_worker_nodes,
    wait_for_no_pods_by_prefix,
)

logger = logging.getLogger(__name__)

CHAOS_JOB_PREFIX = "chaos-"
FEDTOOLS_POD_PREFIX = "fedtools-"
DEFAULT_NAMESPACE = "default"
TOOLS_IMAGE = "quay.io/krkn-chaos/krkn:tools"
# Job script: sleep 30 + duration + sleep 20 (+ image pull). Budget generously.
KRAKEN_RUN_TIMEOUT = 360
PROBE_POD_TIMEOUT = 180
JOB_CLEANUP_TIMEOUT = 60
WORKER_ROLE_LABEL = "node-role.kubernetes.io/worker"


@pytest.mark.functional
@pytest.mark.network_chaos_legacy
class TestNetworkChaosLegacy(BaseScenarioTest):
    """Legacy network_chaos plugin: tc netem on node interfaces via privileged Jobs."""

    SCENARIO_NAME = "network_chaos_legacy"
    SCENARIO_TYPE = "network_chaos_scenarios"
    NAMESPACE_KEY_PATH = []
    NAMESPACE_IS_REGEX = False
    OVERRIDES_KEY_PATH = ["network_chaos"]

    def _batch_api(self):
        return client.BatchV1Api()

    def _scenario(self, overrides=None, drop=None):
        """Load scenario_base.yaml and patch the network_chaos dict."""
        scenario = copy.deepcopy(load_scenario_base(self.repo_root, self.SCENARIO_NAME))
        nc = scenario["network_chaos"]
        for key in drop or []:
            nc.pop(key, None)
        if overrides:
            nc.update(overrides)
        return scenario

    def _target_worker(self):
        """Return a schedulable worker node name or skip when none exist."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node available for network chaos targeting")
        return nodes[0]

    def _ensure_worker_role_label(self, node: str) -> None:
        """KinD workers often lack the worker role label; add it for label_selector tests."""
        body = {"metadata": {"labels": {WORKER_ROLE_LABEL: ""}}}
        self.k8s_core.patch_node(node, body)

    def _run_scenario(self, scenario, config_filename: str):
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename=config_filename,
        )
        return self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)

    def _delete_pod_best_effort(self, name: str) -> None:
        try:
            self.k8s_core.delete_namespaced_pod(
                name=name,
                namespace=DEFAULT_NAMESPACE,
                body=client.V1DeleteOptions(grace_period_seconds=0),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete probe pod %s: %s", name, exc)

    @contextmanager
    def _node_probe(self, node: str):
        """Privileged hostNetwork pod on node for ip/tc checks. Skips if image won't start."""
        name = f"nc-probe-{uuid.uuid4().hex[:8]}"
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name=name, namespace=DEFAULT_NAMESPACE),
            spec=client.V1PodSpec(
                node_name=node,
                host_network=True,
                restart_policy="Never",
                containers=[
                    client.V1Container(
                        name="probe",
                        image=TOOLS_IMAGE,
                        command=["/bin/sh", "-c", "sleep 600"],
                        security_context=client.V1SecurityContext(privileged=True),
                    )
                ],
            ),
        )
        self.k8s_core.create_namespaced_pod(namespace=DEFAULT_NAMESPACE, body=pod)
        try:
            deadline = time.monotonic() + PROBE_POD_TIMEOUT
            while time.monotonic() < deadline:
                p = self.k8s_core.read_namespaced_pod(name=name, namespace=DEFAULT_NAMESPACE)
                phase = (p.status.phase if p.status else None) or ""
                if phase == "Running":
                    yield name
                    return
                if phase == "Failed":
                    break
                time.sleep(1)
            pytest.skip(
                f"Could not start probe pod on node={node} "
                f"(image {TOOLS_IMAGE} may be unavailable)"
            )
        finally:
            self._delete_pod_best_effort(name)

    def _exec_in_pod(self, pod_name: str, shell_cmd: str) -> str:
        resp = stream(
            self.k8s_core.connect_get_namespaced_pod_exec,
            pod_name,
            DEFAULT_NAMESPACE,
            command=["/bin/sh", "-c", shell_cmd],
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
        )
        return resp or ""

    def _discover_default_interface(self, probe_pod: str) -> str:
        out = self._exec_in_pod(
            probe_pod, "ip r | grep default | awk '/default/ {print $5}' | head -1"
        )
        iface = (out or "").strip().splitlines()[0].strip() if (out or "").strip() else ""
        if not iface:
            pytest.skip("Could not discover default interface on target node")
        return iface

    def _tc_qdisc_show(self, probe_pod: str, iface: str) -> str:
        return self._exec_in_pod(probe_pod, f"tc qdisc show dev {iface} 2>/dev/null || true")

    def _has_netem_rules(self, tc_output: str) -> bool:
        return "netem" in (tc_output or "")

    def _ensure_tc_clean(self, probe_pod: str, iface: str) -> None:
        """Remove stale netem left by a prior failed/interrupted run."""
        self._exec_in_pod(probe_pod, f"tc qdisc del dev {iface} root 2>/dev/null || true")

    def _wait_for_tc_clean(self, probe_pod: str, iface: str, timeout: float = 90) -> None:
        """Poll until netem is gone (job does tc_unset before exit)."""
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline:
            last = self._tc_qdisc_show(probe_pod, iface)
            if not self._has_netem_rules(last):
                return
            time.sleep(2)
        # Best-effort recover cluster health for later tests, then fail this assertion.
        self._ensure_tc_clean(probe_pod, iface)
        raise AssertionError(
            f"Residual netem tc rules on {iface} after {timeout}s: {last!r}"
        )

    def _list_chaos_jobs(self):
        jobs = self._batch_api().list_namespaced_job(namespace=DEFAULT_NAMESPACE)
        return [
            j for j in jobs.items
            if j.metadata and j.metadata.name and j.metadata.name.startswith(CHAOS_JOB_PREFIX)
        ]

    def _wait_for_no_chaos_jobs(self, timeout: float = JOB_CLEANUP_TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._list_chaos_jobs():
                return
            time.sleep(1)
        remaining = [j.metadata.name for j in self._list_chaos_jobs()]
        raise AssertionError(
            f"chaos-* jobs still present in namespace={DEFAULT_NAMESPACE} "
            f"after {timeout}s: {remaining}"
        )

    @pytest.mark.no_workload
    @pytest.mark.order(1)
    def test_egress_bandwidth_latency_injection(self):
        """Happy path: bandwidth + latency egress shaping applies tc and Krkn exits 0."""
        node = self._target_worker()
        with self._node_probe(node) as probe_pod:
            iface = self._discover_default_interface(probe_pod)
            self._ensure_tc_clean(probe_pod, iface)
            scenario = self._scenario(
                {
                    "duration": 10,
                    "node_name": node,
                    "egress": {"bandwidth": "100mbit", "latency": "50ms"},
                    "execution": "parallel",
                },
                drop=["label_selector"],
            )
            result = self._run_scenario(scenario, "nc_bandwidth_latency_config.yaml")
            assert_kraken_success(
                result, context=f"bandwidth+latency node={node}", tmp_path=self.tmp_path,
            )
            assert_scenario_executed(
                result, self.SCENARIO_NAME, context=f"bandwidth+latency node={node}",
                tmp_path=self.tmp_path,
            )
            assert_kraken_marker(
                result, "tc qdisc add", context=f"node={node}", tmp_path=self.tmp_path,
            )
            self._wait_for_tc_clean(probe_pod, iface)

    @pytest.mark.no_workload
    @pytest.mark.order(2)
    def test_node_targeting_by_name(self):
        """Happy path: node_name targets the specified worker directly."""
        node = self._target_worker()
        with self._node_probe(node) as probe_pod:
            iface = self._discover_default_interface(probe_pod)
            self._ensure_tc_clean(probe_pod, iface)
            scenario = self._scenario(
                {
                    "duration": 10,
                    "node_name": node,
                    "egress": {"bandwidth": "100mbit"},
                },
                drop=["label_selector"],
            )
            result = self._run_scenario(scenario, "nc_node_name_config.yaml")
            assert_kraken_success(result, context=f"node_name={node}", tmp_path=self.tmp_path)
            assert_scenario_executed(
                result, self.SCENARIO_NAME, context=f"node_name={node}", tmp_path=self.tmp_path,
            )
            combined = f"{result.stdout or ''}\n{result.stderr or ''}"
            assert node in combined, f"Expected node {node!r} in Krkn logs"
            self._wait_for_tc_clean(probe_pod, iface)

    @pytest.mark.no_workload
    @pytest.mark.order(3)
    def test_node_targeting_by_label_selector(self):
        """Happy path: label_selector selects a worker node for chaos."""
        node = self._target_worker()
        self._ensure_worker_role_label(node)
        with self._node_probe(node) as probe_pod:
            iface = self._discover_default_interface(probe_pod)
            self._ensure_tc_clean(probe_pod, iface)
            scenario = self._scenario(
                {
                    "duration": 10,
                    "label_selector": WORKER_ROLE_LABEL,
                    "instance_count": 1,
                    "egress": {"bandwidth": "100mbit"},
                },
                drop=["node_name"],
            )
            result = self._run_scenario(scenario, "nc_label_selector_config.yaml")
            assert_kraken_success(
                result, context=f"label_selector node={node}", tmp_path=self.tmp_path,
            )
            assert_scenario_executed(
                result, self.SCENARIO_NAME, context=f"label_selector node={node}",
                tmp_path=self.tmp_path,
            )
            self._wait_for_tc_clean(probe_pod, iface)

    @pytest.mark.no_workload
    @pytest.mark.order(4)
    def test_interface_selection(self):
        """Happy path: chaos is scoped to the specified interface only."""
        node = self._target_worker()
        with self._node_probe(node) as probe_pod:
            iface = self._discover_default_interface(probe_pod)
            self._ensure_tc_clean(probe_pod, iface)
            scenario = self._scenario(
                {
                    "duration": 10,
                    "node_name": node,
                    "interfaces": [iface],
                    "egress": {"bandwidth": "100mbit"},
                },
                drop=["label_selector"],
            )
            result = self._run_scenario(scenario, "nc_interface_config.yaml")
            assert_kraken_success(
                result, context=f"interface={iface} node={node}", tmp_path=self.tmp_path,
            )
            assert_kraken_marker(
                result, f"dev {iface}", context=f"node={node}", tmp_path=self.tmp_path,
            )
            self._wait_for_tc_clean(probe_pod, iface)

    @pytest.mark.no_workload
    @pytest.mark.order(5)
    def test_serial_execution_mode(self):
        """Happy path: execution=serial processes egress parameters one job at a time."""
        node = self._target_worker()
        with self._node_probe(node) as probe_pod:
            iface = self._discover_default_interface(probe_pod)
            self._ensure_tc_clean(probe_pod, iface)
            scenario = self._scenario(
                {
                    "duration": 10,
                    "node_name": node,
                    "execution": "serial",
                    "egress": {"bandwidth": "100mbit", "latency": "50ms"},
                },
                drop=["label_selector"],
            )
            result = self._run_scenario(scenario, "nc_serial_config.yaml")
            assert_kraken_success(
                result, context=f"serial execution node={node}", tmp_path=self.tmp_path,
            )
            assert_kraken_marker(
                result,
                "Waiting for serial job to finish",
                context=f"node={node}",
                tmp_path=self.tmp_path,
            )
            self._wait_for_tc_clean(probe_pod, iface)

    @pytest.mark.no_workload
    @pytest.mark.order(6)
    def test_packet_loss_parameter(self):
        """Happy path: egress loss percentage is applied via tc netem."""
        node = self._target_worker()
        with self._node_probe(node) as probe_pod:
            iface = self._discover_default_interface(probe_pod)
            self._ensure_tc_clean(probe_pod, iface)
            scenario = self._scenario(
                {
                    "duration": 10,
                    "node_name": node,
                    "egress": {"loss": 0.02},
                },
                drop=["label_selector"],
            )
            result = self._run_scenario(scenario, "nc_loss_config.yaml")
            assert_kraken_success(result, context=f"loss node={node}", tmp_path=self.tmp_path)
            assert_kraken_marker(
                result, "loss 0.02", context=f"node={node}", tmp_path=self.tmp_path,
            )
            self._wait_for_tc_clean(probe_pod, iface)

    @pytest.mark.no_workload
    @pytest.mark.order(7)
    def test_nonexistent_node_name_fails(self):
        """Negative: a node_name that does not exist makes Krkn fail."""
        scenario = self._scenario(
            {
                "node_name": "nonexistent-node",
                "egress": {"bandwidth": "100mbit"},
            },
            drop=["label_selector"],
        )
        result = self._run_scenario(scenario, "nc_bad_node_config.yaml")
        assert_kraken_failure(result, context="nonexistent node_name", tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    @pytest.mark.order(8)
    def test_no_matching_label_selector_fails(self):
        """Negative: a label_selector matching zero nodes makes Krkn fail."""
        scenario = self._scenario(
            {
                "label_selector": "role=nonexistent",
                "instance_count": 1,
                "egress": {"bandwidth": "100mbit"},
            },
            drop=["node_name"],
        )
        result = self._run_scenario(scenario, "nc_bad_selector_config.yaml")
        assert_kraken_failure(result, context="no matching label_selector", tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    @pytest.mark.order(9)
    def test_invalid_interface_handled_gracefully(self):
        """Negative: an interface that does not exist on the node makes Krkn fail cleanly."""
        node = self._target_worker()
        scenario = self._scenario(
            {
                "node_name": node,
                "interfaces": ["fake0"],
                "egress": {"bandwidth": "100mbit"},
            },
            drop=["label_selector"],
        )
        result = self._run_scenario(scenario, "nc_bad_iface_config.yaml")
        assert_kraken_failure(result, context="invalid interface fake0", tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    @pytest.mark.order(10)
    def test_tc_rules_removed_after_duration(self):
        """Cleanup: no residual netem tc rules remain on the node interface after the scenario."""
        node = self._target_worker()
        with self._node_probe(node) as probe_pod:
            iface = self._discover_default_interface(probe_pod)
            self._ensure_tc_clean(probe_pod, iface)
            scenario = self._scenario(
                {
                    "duration": 10,
                    "node_name": node,
                    "egress": {"bandwidth": "100mbit", "latency": "50ms"},
                    "execution": "parallel",
                },
                drop=["label_selector"],
            )
            result = self._run_scenario(scenario, "nc_cleanup_tc_config.yaml")
            assert_kraken_success(
                result, context=f"tc cleanup node={node}", tmp_path=self.tmp_path,
            )
            self._wait_for_tc_clean(probe_pod, iface)

    @pytest.mark.no_workload
    @pytest.mark.order(11)
    def test_helper_pods_cleaned_up(self):
        """Cleanup: fedtools probe pods and chaos jobs are removed after the scenario."""
        node = self._target_worker()
        with self._node_probe(node) as probe_pod:
            iface = self._discover_default_interface(probe_pod)
            self._ensure_tc_clean(probe_pod, iface)
            scenario = self._scenario(
                {
                    "duration": 10,
                    "node_name": node,
                    "egress": {"bandwidth": "100mbit"},
                },
                drop=["label_selector"],
            )
            result = self._run_scenario(scenario, "nc_cleanup_pods_config.yaml")
            assert_kraken_success(
                result, context=f"helper cleanup node={node}", tmp_path=self.tmp_path,
            )
            self._wait_for_tc_clean(probe_pod, iface)
        self._wait_for_no_chaos_jobs()
        wait_for_no_pods_by_prefix(
            self.k8s_core, DEFAULT_NAMESPACE, FEDTOOLS_POD_PREFIX, timeout=JOB_CLEANUP_TIMEOUT,
        )
        assert not self._list_chaos_jobs(), (
            f"chaos-* jobs still present in namespace={DEFAULT_NAMESPACE}"
        )
