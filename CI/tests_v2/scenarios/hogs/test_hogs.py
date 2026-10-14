"""
Functional tests for the hog scenarios (hog_scenarios): cpu_hog, memory_hog, io_hog.

Consolidated family test (migrated from the former per-family test files under
scenarios/cpu_hog/, scenarios/memory_hog/, scenarios/io_hog/ — those directories keep
their scenario_base.yaml as the scenario registry). The happy path is parameterized
over the three hog types; the negative tests are hog-type-independent (both fail in
HogConfig parsing / node selection before any hog-type-specific branch executes), so
they run once, and the signature-verification test is hog-agnostic (it fails in
create_pod's image verification before the pod is created).

Hogs target nodes (not workloads): Krkn deploys a short-lived hog pod (name prefix
"<type>-hog-") onto each selected node, runs it for the configured duration, then
deletes the pod. These tests therefore use @pytest.mark.no_workload (no app
deployment is needed) and verify execution success, node-selector targeting, the
Failed-phase watch, cleanup, and graceful failure on invalid selector/config.

Failed-phase watch semantics: while Kraken runs, the test polls the hog pod by name
and fails if the pod is ever observed with phase Failed (terminal under
restartPolicy: Never — no false positives). Residual gap (accepted): a pod failing
at t≈duration and deleted by the plugin within ~1s can escape the watch; catching
that deterministically needs a production-side change (out of scope).
"""

import logging
import subprocess
import time
from pathlib import Path

import pytest
import yaml
from kubernetes.client import ApiException

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_success,
    assert_scenario_executed,
    schedulable_worker_nodes,
    wait_for_no_pods_by_prefix,
    wait_for_scheduled_pod_by_prefix,
)

logger = logging.getLogger(__name__)

HOG_POD_CREATE_TIMEOUT = 120
HOG_POD_CLEANUP_TIMEOUT = 60
KRAKEN_RUN_TIMEOUT = 300
HOG_DURATION = 10  # test-tuned (matches the production cpu default); binding precedes
# stress start and the pod object persists until the plugin deletes it, so the
# scheduled-pod observation is unaffected.

# (scenario_name, hog pod prefix, extra scenario overrides). scenario_name doubles as
# the scenario-registry dir (scenarios/<name>/scenario_base.yaml) and the
# SCENARIO_EXECUTION_MARKERS key. Per-param family marks keep `-m cpu_hog` etc. usable.
#
# KRKN-009: cpu_hog and memory_hog are kind_only because the hog image's
# run.sh writes hog-jobfile.conf/output.yaml into its working directory
# (/stress-ng), which OpenShift mounts read-only — the pod fails with
# "Read-only file system" even when privileged. io_hog is unaffected (its
# STRESS_PATH hostPath is writable). Remove these marks when KRKN-009 is
# fixed in the image/entrypoint.
HOG_PARAMS = [
    pytest.param("cpu_hog", "cpu-hog-", {}, id="cpu_hog",
                 marks=[pytest.mark.cpu_hog, pytest.mark.kind_only]),
    pytest.param("memory_hog", "memory-hog-", {"memory-vm-bytes": "256m"},
                 id="memory_hog", marks=[pytest.mark.memory_hog, pytest.mark.kind_only]),
    pytest.param("io_hog", "io-hog-", {}, id="io_hog", marks=pytest.mark.io_hog),
]


@pytest.mark.functional
@pytest.mark.xdist_group("node-resource-chaos")
class TestHogs(BaseScenarioTest):
    """Hog scenarios (cpu/memory/io): deploy a hog pod on the node-selector target,
    verify success, node targeting, no Failed pod, execution evidence, and cleanup."""

    SCENARIO_TYPE = "hog_scenarios"
    NAMESPACE_KEY_PATH = ["namespace"]
    NAMESPACE_IS_REGEX = False
    # SCENARIO_NAME is set per test (instance attribute) because this module covers
    # three scenario-registry dirs; base.py helpers read it off self.

    def _scenario(self, scenario_name, namespace, overrides):
        """Load the family's scenario_base.yaml, patch namespace, then apply flat-dict
        overrides (hyphenated keys)."""
        self.SCENARIO_NAME = scenario_name  # instance attr; shadows the class default ""
        scenario = self.load_and_patch_scenario(self.repo_root, namespace)
        scenario.update(overrides)
        return scenario

    def _pod_phase(self, pod_name, namespace):
        """Current pod phase, or None once the pod is deleted (the plugin deletes it
        after completion)."""
        try:
            pod = self.k8s_core.read_namespaced_pod(name=pod_name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                return None
            raise
        return pod.status.phase if pod.status else None

    @pytest.mark.no_workload
    @pytest.mark.order(1)
    @pytest.mark.parametrize("scenario_name,pod_prefix,extra_overrides", HOG_PARAMS)
    def test_hog_success_lifecycle_and_targeting(self, scenario_name, pod_prefix, extra_overrides):
        """Happy path: a hog pod is created on the node-selector target, is never
        observed Failed while Kraken runs, the run succeeds with execution evidence,
        and the pod is cleaned up.

        Residual gap (accepted): a hog pod failing at t≈duration and being deleted by
        the plugin within ~1s can escape the Failed watch; catching that
        deterministically needs a production-side change (out of scope).
        """
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip(f"No schedulable worker node available for {scenario_name} targeting")
        node = nodes[0]
        ns = self.ns
        overrides = {
            "node-selector": f"kubernetes.io/hostname={node}",
            "number-of-nodes": 1,
            "duration": HOG_DURATION,
        }
        overrides.update(extra_overrides)
        scenario = self._scenario(scenario_name, ns, overrides)
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename=f"{scenario_name}_success_config.yaml",
        )
        proc = self.run_kraken_background(config_path)
        try:
            pod = wait_for_scheduled_pod_by_prefix(
                self.k8s_core, ns, pod_prefix, timeout=HOG_POD_CREATE_TIMEOUT
            )
            assert pod is not None, (
                f"Expected a {scenario_name} pod (prefix {pod_prefix!r}) to be created in namespace={ns}"
            )
            assert pod.spec and pod.spec.node_name == node, (
                f"{scenario_name} pod {pod.metadata.name} scheduled on "
                f"{getattr(pod.spec, 'node_name', None)!r}, expected node-selector target {node!r} "
                f"(namespace={ns})"
            )
            # Fail if the hog pod is ever observed Failed while Kraken runs. phase
            # Failed is terminal under restartPolicy: Never — zero false positives.
            # A broken hog image env/entrypoint contract fails seconds into the run,
            # while the plugin is still in its 3s sleep + duration-1s sampling loop.
            pod_name = pod.metadata.name
            deadline = time.monotonic() + KRAKEN_RUN_TIMEOUT
            while proc.poll() is None:
                if time.monotonic() > deadline:
                    raise subprocess.TimeoutExpired(proc.args, KRAKEN_RUN_TIMEOUT)
                if self._pod_phase(pod_name, ns) == "Failed":
                    raise AssertionError(
                        f"{scenario_name} pod {pod_name} observed with phase Failed while Kraken "
                        f"ran (broken hog image/env contract?) namespace={ns} node={node}"
                    )
                time.sleep(0.5)
            out, err = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            raise
        except BaseException:
            # Any poll/assert failure before communicate() must still tear down the
            # background Kraken process, otherwise its hog pod keeps stressing the node
            # and races against subsequent --reruns on the same target.
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise
        result = subprocess.CompletedProcess(
            args=[], returncode=proc.returncode, stdout=out, stderr=err
        )
        assert_kraken_success(result, context=f"node={node} namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, scenario_name, context=f"node={node} namespace={ns}", tmp_path=self.tmp_path
        )
        wait_for_no_pods_by_prefix(self.k8s_core, ns, pod_prefix, timeout=HOG_POD_CLEANUP_TIMEOUT)

    @pytest.mark.no_workload
    @pytest.mark.order(2)
    def test_hog_invalid_selector_fails(self):
        """Negative: a node-selector matching zero nodes makes Krkn fail (no available
        nodes to schedule). Hog-type-independent: fails at node selection before any
        per-type branch executes."""
        ns = self.ns
        scenario = self._scenario("cpu_hog", ns, {
            "node-selector": "kubernetes.io/hostname=krkn-nonexistent-node-zzz",
            "number-of-nodes": 1,
        })
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="hogs_invalid_selector_config.yaml"
        )
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_failure(
            result, context=f"invalid node-selector namespace={ns}", tmp_path=self.tmp_path
        )
        wait_for_no_pods_by_prefix(self.k8s_core, ns, "cpu-hog-", timeout=HOG_POD_CLEANUP_TIMEOUT)

    @pytest.mark.no_workload
    @pytest.mark.order(3)
    def test_hog_invalid_config_fails(self):
        """Negative: omitting the mandatory hog-type field makes Krkn fail at config
        parsing. Hog-type-independent: HogConfig.from_yaml_dict raises before any
        per-type field parsing."""
        ns = self.ns
        scenario = self._scenario("cpu_hog", ns, {})
        scenario.pop("hog-type", None)
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="hogs_invalid_config_config.yaml"
        )
        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)
        assert_kraken_failure(
            result, context=f"missing hog-type namespace={ns}", tmp_path=self.tmp_path
        )

    @pytest.mark.no_workload
    @pytest.mark.order(4)
    def test_unsigned_legacy_hog_image_is_rejected(self):
        """Negative: signature verification rejects the legacy production image."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node available for signature verification test")
        ns = self.ns
        scenario = self._scenario("cpu_hog", ns, {
            "node-selector": f"kubernetes.io/hostname={nodes[0]}",
            "number-of-nodes": 1,
            "duration": 20,
            "image": (
                "quay.io/krkn-chaos/krkn-hog@sha256:"
                "caaf730f5586e690c4af8a8164a746c8b4b2686f3b8b93327df9dbf6e9a04a3f"
            ),
        })
        scenario_path = self.write_scenario(self.tmp_path, scenario)
        config_path = self.build_config(
            self.SCENARIO_TYPE,
            str(scenario_path),
            filename="hogs_unsigned_image_config.yaml",
        )

        config = yaml.safe_load(Path(config_path).read_text())
        config["kraken"]["image_signature_verification_enabled"] = True
        config["kraken"]["image_signature_public_key"] = "cosign.pub"
        Path(config_path).write_text(
            yaml.safe_dump(config, default_flow_style=False, sort_keys=False)
        )

        result = self.run_kraken(config_path, timeout=KRAKEN_RUN_TIMEOUT)

        assert_kraken_failure(
            result,
            context=f"unsigned image namespace={ns}",
            tmp_path=self.tmp_path,
        )
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        assert "Image signature verification failed" in combined
        assert (
            "quay.io/krkn-chaos/krkn-hog@sha256:"
            "caaf730f5586e690c4af8a8164a746c8b4b2686f3b8b93327df9dbf6e9a04a3f"
            in combined
        )
        wait_for_no_pods_by_prefix(
            self.k8s_core,
            ns,
            "cpu-hog-",
            timeout=HOG_POD_CLEANUP_TIMEOUT,
        )
