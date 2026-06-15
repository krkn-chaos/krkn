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
import uuid

import pytest

from lib.base import BaseScenarioTest
from lib.deploy import (
    deploy_manifest_to_namespace,
    deployment_exists,
    wait_for_no_deployment,
    wait_for_present_deployment_count,
)
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_success,
    assert_scenario_executed,
)

logger = logging.getLogger(__name__)

_TARGET_NAME = "namespace-deletion-target"


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

    # --- happy-path tests ----------------------------------------------------

    @pytest.mark.order(1)
    def test_single_namespace_object_deletion(self):
        """Regex matches exactly one namespace; all its objects are deleted, Krkn exits 0."""
        ns = self.ns
        assert deployment_exists(self.k8s_apps, ns, _TARGET_NAME), f"Workload not deployed in {ns}"
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"delete_count": 1, "runs": 1, "sleep": 1},
            config_filename="ns_del_single.yaml",
        )
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path
        )
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") != "1":
            wait_for_no_deployment(self.k8s_apps, ns, _TARGET_NAME)
            services = self.k8s_core.list_namespaced_service(ns).items
            assert all(s.metadata.name != _TARGET_NAME for s in services), (
                f"Service {_TARGET_NAME} should have been deleted in namespace={ns}"
            )

    @pytest.mark.no_workload
    def test_multiple_namespace_delete_count(self, make_namespace):
        """Regex matches 3 namespaces with delete_count=2; exactly 2 are disrupted, 1 untouched."""
        prefix = f"krkn-test-{uuid.uuid4().hex[:8]}-multi"
        namespaces = []
        for i in range(3):
            name = make_namespace(f"{prefix}-{i}")
            deploy_manifest_to_namespace(
                self.k8s_client, self.k8s_apps, self.WORKLOAD_MANIFEST, name,
                _TARGET_NAME, repo_root=self.repo_root,
            )
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
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") != "1":
            wait_for_present_deployment_count(self.k8s_apps, namespaces, _TARGET_NAME, expected=1)

    def test_multiple_runs_repeat_disruption_loop(self):
        """runs=2 executes the disruption loop twice.

        The plugin logs "Delete objects in selected namespace" once per run, so the
        count proves the outer runs loop iterated twice. Actual object removal is
        asserted in test_single_namespace_object_deletion; here the workload is deleted
        in run 1 and never recreated (Krkn does not redeploy between runs), so run 2
        re-selects the now-empty namespace and deletes nothing. This test therefore
        verifies that the loop repeats, not that deletion recurs against live objects.
        """
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
                f"Expected the disruption loop to iterate >=2 times for runs=2, "
                f"saw {count} (namespace={ns})"
            )

    def test_wait_time_accepted(self):
        """A configured wait_time is accepted and the scenario completes successfully."""
        ns = self.ns
        # Use a non-default wait_time (base scenario_base.yaml defaults to 30) so the test
        # actually exercises override patching rather than passing on the base value.
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"wait_time": 5, "delete_count": 1, "runs": 1, "sleep": 1},
            config_filename="ns_del_wait.yaml",
        )
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path
        )

    @pytest.mark.no_workload
    def test_label_selector_targeting(self, make_namespace):
        """With namespace empty and a label_selector set, targeting works by namespace label."""
        label_key = "krkn-test-ns"
        label_value = uuid.uuid4().hex[:8]
        name = make_namespace(
            f"krkn-test-{label_value}-label", extra_labels={label_key: label_value}
        )
        deploy_manifest_to_namespace(
            self.k8s_client, self.k8s_apps, self.WORKLOAD_MANIFEST, name,
            _TARGET_NAME, repo_root=self.repo_root,
        )
        # Build the scenario directly: label-selector mode requires the namespace field to be a
        # literal empty string (""), but NAMESPACE_IS_REGEX=True makes load_and_patch_scenario wrap
        # any namespace as ^...$, so an empty namespace through run_scenario would become "^$".
        # We patch with a real name (harmless) and then blank the namespace to "" explicitly.
        scenario = self.load_and_patch_scenario(
            self.repo_root, name,
            label_selector=f"{label_key}={label_value}", delete_count=1, runs=1, sleep=1,
        )
        scenario["scenarios"][0]["namespace"] = ""
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_label")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="ns_del_label.yaml"
        )
        # This test bypasses run_scenario (to blank the namespace field), so the dry-run
        # short-circuit in BaseScenarioTest.run_scenario does not apply here. Honor it
        # explicitly: skip the real Kraken invocation and the cluster post-check.
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
            logger.info(
                "[dry-run] Would run Kraken with config=%s (label-selector mode)", config_path
            )
            return
        result = self.run_kraken(config_path)
        assert_kraken_success(result, context=f"namespace={name}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={name}", tmp_path=self.tmp_path
        )
        wait_for_no_deployment(self.k8s_apps, name, _TARGET_NAME)

    # --- negative / failure-mode tests ---------------------------------------

    @pytest.mark.no_workload
    def test_no_match_namespace_fails(self):
        """A regex matching zero namespaces makes Krkn exit non-zero with a clear error."""
        # UUID-based name so the regex is guaranteed not to match any pre-existing
        # namespace (e.g. leftover from a previous run); this namespace is never created.
        ns = f"krkn-test-nonexistent-{uuid.uuid4().hex}"
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"delete_count": 1, "runs": 1},
            config_filename="ns_del_nomatch.yaml",
        )
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
            return  # Krkn is skipped under dry-run; the failure path can't be exercised.
        assert_kraken_failure(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        combined = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
        # The service_disruption plugin only ever logs "not enough namespaces matching ..."
        # (service_disruption_scenario_plugin.py:82-90); there is no "no namespaces matching" path.
        assert "not enough namespaces" in combined, (
            "Expected a 'not enough namespaces matching' error in Krkn output"
        )

    @pytest.mark.no_workload
    def test_namespace_and_label_mutual_exclusion_fails(self):
        """Setting both namespace and label_selector makes Krkn exit 1 with a mutual-exclusion error."""
        ns = "krkn-test-mutual-excl"
        label_selector = "app=foo"
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"label_selector": label_selector, "delete_count": 1, "runs": 1},
            config_filename="ns_del_mutual.yaml",
        )
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
            return  # Krkn is skipped under dry-run; the failure path can't be exercised.
        assert_kraken_failure(
            result, context=f"namespace={ns}, label_selector={label_selector}", tmp_path=self.tmp_path
        )
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
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
            return  # Krkn is skipped under dry-run; the failure path can't be exercised.
        assert_kraken_failure(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        combined = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
        assert "not enough namespaces" in combined, (
            f"Expected 'not enough namespaces' error in Krkn output (namespace={ns})"
        )
