"""
Functional test for application outage scenario (block network to target pods, then restore).
Equivalent to CI/tests/test_app_outages.sh with proper assertions.
The main happy-path test reuses one namespace and workload for multiple scenario runs (default, exclude_label, block variants); other tests use their own ephemeral namespace as needed.

Negative config paths (invalid scenario, bad namespace) are unit-covered
(.local-unit-tests/test_application_outage_local.py, ported for a future
pushed unit layer).
"""

import time

import pytest

from lib.base import (
    BaseScenarioTest,
    KRAKEN_PROC_WAIT_TIMEOUT,
    POLICY_WAIT_TIMEOUT,
)
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_success,
    assert_pod_count_unchanged,
    assert_scenario_executed,
    find_network_policy_by_prefix,
    get_network_policies_list,
    get_pods_list,
)


def _wait_for_network_policy(k8s_networking, namespace: str, prefix: str, timeout: int = 30):
    """Poll until a NetworkPolicy with name starting with prefix exists. Return its name."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        policy_list = get_network_policies_list(k8s_networking, namespace)
        policy = find_network_policy_by_prefix(policy_list, prefix)
        if policy and policy.metadata:
            return policy.metadata.name
        time.sleep(1)
    raise TimeoutError(f"No NetworkPolicy with prefix {prefix!r} in {namespace} within {timeout}s")


def _assert_no_network_policy_with_prefix(k8s_networking, namespace: str, prefix: str):
    policy_list = get_network_policies_list(k8s_networking, namespace)
    policy = find_network_policy_by_prefix(policy_list, prefix)
    name = policy.metadata.name if policy and policy.metadata else "?"
    assert policy is None, (
        f"Expected no NetworkPolicy with prefix {prefix!r} in namespace={namespace}, found {name}"
    )


@pytest.mark.functional
@pytest.mark.application_outage
class TestApplicationOutage(BaseScenarioTest):
    """Application outage scenario: block network to target pods, then restore."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/application_outage/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "scenario=outage"
    POLICY_PREFIX = "krkn-deny-"
    SCENARIO_NAME = "application_outage"
    SCENARIO_TYPE = "application_outages_scenarios"
    NAMESPACE_KEY_PATH = ["application_outage", "namespace"]
    NAMESPACE_IS_REGEX = False
    OVERRIDES_KEY_PATH = ["application_outage"]

    @pytest.mark.order(1)
    def test_app_outage_block_restore_and_variants(self):
        """Default, exclude_label, and block-type variants (Ingress, Egress, both) run successfully in one namespace; each run restores and pods stay ready."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)

        cases = [
            ("default", {}, "app_outage_config.yaml"),
            ("exclude_label", {"exclude_label": {"env": "prod"}}, "app_outage_exclude_config.yaml"),
            ("block=Ingress", {"block": ["Ingress"]}, "app_outage_block_ingress_config.yaml"),
            ("block=Egress", {"block": ["Egress"]}, "app_outage_block_egress_config.yaml"),
            ("block=Ingress,Egress", {"block": ["Ingress", "Egress"]}, "app_outage_block_ingress_egress_config.yaml"),
        ]
        for context_name, overrides, config_filename in cases:
            result = self.run_scenario(
                self.tmp_path, ns,
                overrides=overrides if overrides else None,
                config_filename=config_filename,
            )
            assert_kraken_success(
                result, context=f"{context_name} namespace={ns}", tmp_path=self.tmp_path
            )
            assert_scenario_executed(
                result, self.SCENARIO_NAME,
                context=f"{context_name} namespace={ns}", tmp_path=self.tmp_path,
            )
            after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
            assert_pod_count_unchanged(before, after, namespace=ns)
            assert_all_pods_running_and_ready(after, namespace=ns)

    def test_network_policy_created_then_deleted(self):
        """NetworkPolicy with prefix krkn-deny- is created during run and deleted after."""
        ns = self.ns
        scenario = self.load_and_patch_scenario(self.repo_root, ns, duration=12)
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_np_lifecycle")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="app_outage_np_lifecycle.yaml",
        )
        proc = self.run_kraken_background(config_path)
        try:
            policy_name = _wait_for_network_policy(
                self.k8s_networking, ns, self.POLICY_PREFIX, timeout=POLICY_WAIT_TIMEOUT
            )
            assert policy_name.startswith(self.POLICY_PREFIX), (
                f"Policy name {policy_name!r} should start with {self.POLICY_PREFIX!r} (namespace={ns})"
            )
            policy_list = get_network_policies_list(self.k8s_networking, ns)
            policy = find_network_policy_by_prefix(policy_list, self.POLICY_PREFIX)
            assert policy is not None and policy.spec is not None, (
                f"Expected NetworkPolicy with spec (namespace={ns})"
            )
            assert policy.spec.pod_selector is not None, f"Policy should have pod_selector (namespace={ns})"
            assert policy.spec.policy_types is not None, f"Policy should have policy_types (namespace={ns})"
        finally:
            proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)
        _assert_no_network_policy_with_prefix(self.k8s_networking, ns, self.POLICY_PREFIX)
