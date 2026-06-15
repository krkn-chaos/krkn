"""
Functional test for the namespace_deletion (service_disruption) scenario.
Migrated from CI/tests/test_namespace.sh.

The service_disruption plugin selects namespaces by regex (scenarios[].namespace)
or by namespace label_selector, then deletes all objects (deployments, daemonsets,
statefulsets, replicasets, services) inside each selected namespace. delete_count
controls how many matched namespaces are disrupted per run; runs repeats the loop.

Safety: every namespace targeted here is the per-test ephemeral namespace or one the
test creates with a unique krkn-test-<uuid> prefix, so the regex/label can never match
a namespace the test did not create.
"""

import logging
import os
import time
import uuid

import pytest
import yaml
from kubernetes import client
from kubernetes import utils as k8s_utils
from kubernetes.client.rest import ApiException

from lib.base import BaseScenarioTest, READINESS_TIMEOUT
from lib.deploy import wait_for_deployment_replicas
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_success,
    assert_scenario_executed,
    patch_namespace_in_docs,
)

logger = logging.getLogger(__name__)

_TARGET_NAME = "namespace-deletion-target"

# Pod-security labels mirror the test_namespace fixture so manually created
# namespaces accept the same workloads on both Kubernetes and OpenShift.
_NS_BASE_LABELS = {
    "pod-security.kubernetes.io/audit": "privileged",
    "pod-security.kubernetes.io/enforce": "privileged",
    "pod-security.kubernetes.io/enforce-version": "v1.24",
    "pod-security.kubernetes.io/warn": "privileged",
    "security.openshift.io/scc.podSecurityLabelSync": "false",
}


@pytest.mark.functional
@pytest.mark.namespace_deletion
class TestNamespaceDeletion(BaseScenarioTest):
    """namespace_deletion scenario: delete all objects in selected namespaces."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/namespace_deletion/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "app=namespace-deletion-target"
    SCENARIO_NAME = "namespace_deletion"
    SCENARIO_TYPE = "service_disruption_scenarios"
    NAMESPACE_KEY_PATH = ["scenarios", 0, "namespace"]
    NAMESPACE_IS_REGEX = True
    OVERRIDES_KEY_PATH = ["scenarios", 0]

    # --- helpers -------------------------------------------------------------

    def _delete_namespace(self, name):
        try:
            self.k8s_core.delete_namespace(
                name=name, body=client.V1DeleteOptions(propagation_policy="Background")
            )
        except Exception as e:  # noqa: BLE001 - cleanup must never raise
            logger.warning("Failed to delete namespace %s: %s", name, e)

    def _make_namespace(self, request, name, extra_labels=None):
        labels = dict(_NS_BASE_LABELS)
        if extra_labels:
            labels.update(extra_labels)
        body = client.V1Namespace(metadata=client.V1ObjectMeta(name=name, labels=labels))
        self.k8s_core.create_namespace(body=body)
        request.addfinalizer(lambda: self._delete_namespace(name))
        logger.info("Created test namespace: %s", name)
        return name

    def _deploy_target(self, namespace):
        path = self.repo_root / self.WORKLOAD_MANIFEST
        docs = patch_namespace_in_docs(list(yaml.safe_load_all(path.read_text())), namespace)
        k8s_utils.create_from_yaml(self.k8s_client, yaml_objects=docs, namespace=namespace)
        wait_for_deployment_replicas(self.k8s_apps, namespace, _TARGET_NAME, timeout=READINESS_TIMEOUT)

    def _deployment_exists(self, namespace):
        try:
            self.k8s_apps.read_namespaced_deployment(name=_TARGET_NAME, namespace=namespace)
            return True
        except ApiException as e:
            if e.status == 404:
                return False
            raise

    def _wait_no_deployment(self, namespace, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._deployment_exists(namespace):
                return
            time.sleep(1)
        raise AssertionError(
            f"Deployment {_TARGET_NAME} still present in namespace={namespace} after {timeout}s"
        )

    def _wait_present_count(self, namespaces, expected, timeout=45):
        deadline = time.monotonic() + timeout
        present = list(namespaces)
        while time.monotonic() < deadline:
            present = [n for n in namespaces if self._deployment_exists(n)]
            if len(present) == expected:
                return present
            time.sleep(1)
        raise AssertionError(
            f"Expected {expected} namespace(s) with {_TARGET_NAME} present, "
            f"found {len(present)}: {present}"
        )

    # --- happy-path tests ----------------------------------------------------

    @pytest.mark.order(1)
    def test_single_namespace_object_deletion(self):
        """Regex matches exactly one namespace; all its objects are deleted, Krkn exits 0."""
        ns = self.ns
        assert self._deployment_exists(ns), f"Workload not deployed in {ns}"
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"delete_count": 1, "runs": 1, "sleep": 1},
            config_filename="ns_del_single.yaml",
        )
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path
        )
        self._wait_no_deployment(ns)
        services = self.k8s_core.list_namespaced_service(ns).items
        assert all(s.metadata.name != _TARGET_NAME for s in services), (
            f"Service {_TARGET_NAME} should have been deleted in namespace={ns}"
        )

    @pytest.mark.no_workload
    def test_multiple_namespace_delete_count(self, request):
        """Regex matches 3 namespaces with delete_count=2; exactly 2 are disrupted, 1 untouched."""
        prefix = f"krkn-test-{uuid.uuid4().hex[:8]}-multi"
        namespaces = []
        for i in range(3):
            name = self._make_namespace(request, f"{prefix}-{i}")
            self._deploy_target(name)
            namespaces.append(name)
        result = self.run_scenario(
            self.tmp_path, f"{prefix}-.*",
            overrides={"delete_count": 2, "runs": 1, "sleep": 1},
            config_filename="ns_del_multi.yaml",
        )
        assert_kraken_success(result, context=f"prefix={prefix}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"prefix={prefix}", tmp_path=self.tmp_path
        )
        # Exactly one of the three namespaces should still hold its deployment.
        self._wait_present_count(namespaces, expected=1)

    def test_multiple_runs_repeat_deletion(self):
        """runs=2 repeats the deletion loop: the selection/delete log appears at least twice."""
        ns = self.ns
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"runs": 2, "delete_count": 1, "sleep": 1},
            config_filename="ns_del_runs.yaml",
        )
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path
        )
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") != "1":
            combined = f"{result.stdout or ''}\n{result.stderr or ''}"
            count = combined.count("Delete objects in selected namespace")
            assert count >= 2, (
                f"Expected >=2 deletion iterations for runs=2, saw {count} (namespace={ns})"
            )

    def test_wait_time_accepted(self):
        """A configured wait_time is accepted and the scenario completes successfully."""
        ns = self.ns
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"wait_time": 30, "delete_count": 1, "runs": 1, "sleep": 1},
            config_filename="ns_del_wait.yaml",
        )
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path
        )

    @pytest.mark.no_workload
    def test_label_selector_targeting(self, request):
        """With namespace empty and a label_selector set, targeting works by namespace label."""
        label_key = "krkn-test-ns"
        label_value = uuid.uuid4().hex[:8]
        name = self._make_namespace(
            request, f"krkn-test-{label_value}-label", extra_labels={label_key: label_value}
        )
        self._deploy_target(name)
        # Build the scenario directly: blanking the namespace can't go through run_scenario,
        # whose **overrides would collide with the positional `namespace` argument.
        scenario = self.load_and_patch_scenario(
            self.repo_root, name,
            label_selector=f"{label_key}={label_value}", delete_count=1, runs=1, sleep=1,
        )
        scenario["scenarios"][0]["namespace"] = ""
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_label")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="ns_del_label.yaml"
        )
        result = self.run_kraken(config_path)
        assert_kraken_success(result, context=f"namespace={name}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={name}", tmp_path=self.tmp_path
        )
        self._wait_no_deployment(name)

    # --- negative / failure-mode tests ---------------------------------------

    @pytest.mark.no_workload
    def test_no_match_namespace_fails(self):
        """A regex matching zero namespaces makes Krkn exit non-zero with a clear error."""
        result = self.run_scenario(
            self.tmp_path, "krkn-test-nonexistent-zzz-00000000",
            overrides={"delete_count": 1, "runs": 1},
            config_filename="ns_del_nomatch.yaml",
        )
        assert_kraken_failure(result, context=f"namespace={self.ns}", tmp_path=self.tmp_path)
        combined = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
        assert "no namespaces matching" in combined or "not enough namespaces" in combined, (
            "Expected a 'no namespaces matching' error in Krkn output"
        )

    @pytest.mark.no_workload
    def test_namespace_and_label_mutual_exclusion_fails(self):
        """Setting both namespace and label_selector makes Krkn exit 1 with a mutual-exclusion error."""
        result = self.run_scenario(
            self.tmp_path, "krkn-test-mutual-excl",
            overrides={"label_selector": "app=foo", "delete_count": 1, "runs": 1},
            config_filename="ns_del_mutual.yaml",
        )
        assert_kraken_failure(result, context=f"namespace={self.ns}", tmp_path=self.tmp_path)
        combined = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
        assert "you can only have namespace or label set" in combined, (
            "Expected the mutual-exclusion error in Krkn output"
        )

    def test_delete_count_exceeds_available_fails(self):
        """delete_count greater than the number of matched namespaces fails with 'not enough namespaces'."""
        ns = self.ns
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"delete_count": 5, "runs": 1, "sleep": 1},
            config_filename="ns_del_exceeds.yaml",
        )
        assert_kraken_failure(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        combined = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
        assert "not enough namespaces" in combined, (
            f"Expected 'not enough namespaces' error in Krkn output (namespace={ns})"
        )
