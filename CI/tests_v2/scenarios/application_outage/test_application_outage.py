"""
Functional test for application outage scenario (block network to target pods, then restore).
Equivalent to CI/tests/test_app_outages.sh with proper assertions.
Each test runs in its own ephemeral namespace with workload deployed automatically.
"""

import socket
import subprocess
import time

import pytest
import requests
import yaml
from kubernetes import utils as k8s_utils

from lib.base import (
    BaseScenarioTest,
    KRAKEN_PROC_WAIT_TIMEOUT,
    POLICY_WAIT_TIMEOUT,
    READINESS_TIMEOUT,
)
from lib.deploy import wait_for_deployment_replicas
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_failure,
    assert_kraken_success,
    assert_pod_count_unchanged,
    find_network_policy_by_prefix,
    get_network_policies_list,
    get_pods_list,
    patch_namespace_in_docs,
    scenario_dir,
)


def _wait_for_network_policy(k8s_networking, namespace: str, prefix: str, timeout: int = 30):
    """Poll until a NetworkPolicy with name starting with prefix exists. Return its name."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        policy_list = get_network_policies_list(k8s_networking, namespace)
        policy = find_network_policy_by_prefix(policy_list, prefix)
        if policy:
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


def _get_free_port() -> int:
    """Return a free port for use with port-forward (avoids collisions when running in parallel)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


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
    def test_app_outage_block_and_restore(self):
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)

        result = self.run_scenario(
            self.tmp_path, ns, config_filename="app_outage_config.yaml"
        )
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)

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

    # def test_traffic_blocked_during_outage(self, request):
    #     """During outage, ingress to target pods is blocked; after run, traffic is restored."""
    #     ns = self.ns
    #     nginx_path = scenario_dir(self.repo_root, "application_outage") / "nginx_http.yaml"
    #     docs = list(yaml.safe_load_all(nginx_path.read_text()))
    #     docs = patch_namespace_in_docs(docs, ns)
    #     try:
    #         k8s_utils.create_from_yaml(
    #             self.k8s_client,
    #             yaml_objects=docs,
    #             namespace=ns,
    #         )
    #     except k8s_utils.FailToCreateError as e:
    #         msgs = [str(exc) for exc in e.api_exceptions]
    #         raise AssertionError(
    #             f"Failed to create nginx resources (namespace={ns}): {'; '.join(msgs)}"
    #         ) from e
    #     wait_for_deployment_replicas(self.k8s_apps, ns, "nginx-outage-http", timeout=READINESS_TIMEOUT)
    #     port = _get_free_port()
    #     pf_ref = []

    #     def _kill_port_forward():
    #         if pf_ref and pf_ref[0].poll() is None:
    #             pf_ref[0].terminate()
    #             try:
    #                 pf_ref[0].wait(timeout=5)
    #             except subprocess.TimeoutExpired:
    #                 pf_ref[0].kill()

    #     request.addfinalizer(_kill_port_forward)
    #     pf = subprocess.Popen(
    #         ["kubectl", "port-forward", "-n", ns, "service/nginx-outage-http", f"{port}:80"],
    #         cwd=self.repo_root,
    #         stdout=subprocess.DEVNULL,
    #         stderr=subprocess.DEVNULL,
    #     )
    #     pf_ref.append(pf)
    #     url = f"http://127.0.0.1:{port}/"
    #     try:
    #         time.sleep(2)
    #         baseline_ok = False
    #         for _ in range(10):
    #             try:
    #                 resp = requests.get(url, timeout=3)
    #                 if resp.ok:
    #                     baseline_ok = True
    #                     break
    #             except (requests.ConnectionError, requests.Timeout):
    #                 pass
    #             time.sleep(1)
    #         assert baseline_ok, f"Baseline: HTTP request to nginx should succeed (namespace={ns})"

    #         scenario = self.load_and_patch_scenario(self.repo_root, ns, duration=15)
    #         scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_traffic")
    #         config_path = self.build_config(
    #             self.SCENARIO_TYPE, str(scenario_path),
    #             filename="app_outage_traffic_config.yaml",
    #         )
    #         proc = self.run_kraken_background(config_path)
    #         policy_name = _wait_for_network_policy(
    #             self.k8s_networking, ns, self.POLICY_PREFIX, timeout=POLICY_WAIT_TIMEOUT
    #         )
    #         assert policy_name, f"Expected policy to exist (namespace={ns})"
    #         time.sleep(2)
    #         failed = False
    #         for _ in range(5):
    #             try:
    #                 resp = requests.get(url, timeout=2)
    #                 if not resp.ok:
    #                     failed = True
    #                     break
    #             except (requests.ConnectionError, requests.Timeout):
    #                 failed = True
    #                 break
    #             time.sleep(1)
    #         assert failed, f"During outage, HTTP request to nginx should fail (namespace={ns})"
    #         proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)
    #         time.sleep(1)
    #         resp = requests.get(url, timeout=5)
    #         assert resp.ok, f"After scenario, HTTP request to nginx should succeed (namespace={ns})"
    #     finally:
    #         pf.terminate()
    #         pf.wait(timeout=5)

    @pytest.mark.parametrize(
        "block_type",
        [["Ingress"], ["Egress"], ["Ingress", "Egress"]],
        ids=["Ingress", "Egress", "Ingress_Egress"],
    )
    def test_block_type_variants(self, block_type):
        """Scenario runs successfully with Ingress-only, Egress-only, or both."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        block_id = "_".join(block_type).lower()
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"block": block_type},
            config_filename=f"app_outage_block_{block_id}_config.yaml",
        )
        assert_kraken_success(
            result, context=f"block={block_type} namespace={ns}", tmp_path=self.tmp_path
        )
        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)
        assert_all_pods_running_and_ready(after, namespace=ns)

    def test_exclude_label_e2e(self):
        """Scenario with exclude_label (matchExpressions) runs and restores."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"exclude_label": {"env": "prod"}},
            config_filename="app_outage_exclude_config.yaml",
        )
        assert_kraken_success(result, context=f"exclude_label namespace={ns}", tmp_path=self.tmp_path)
        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)

    @pytest.mark.no_workload
    def test_invalid_scenario_fails(self):
        """Invalid scenario file (missing application_outage) causes Kraken to exit non-zero."""
        invalid_scenario_path = self.tmp_path / "invalid_scenario.yaml"
        invalid_scenario_path.write_text("foo: bar\n")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(invalid_scenario_path),
            filename="invalid_config.yaml",
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(
            result, context=f"namespace={self.ns}", tmp_path=self.tmp_path
        )

    @pytest.mark.no_workload
    def test_bad_namespace_fails(self):
        """Scenario targeting non-existent namespace causes Kraken to exit non-zero."""
        scenario = self.load_and_patch_scenario(self.repo_root, "nonexistent-namespace-xyz-12345")
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_bad_ns")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="app_outage_bad_ns_config.yaml",
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(
            result,
            context=f"test namespace={self.ns}",
            tmp_path=self.tmp_path,
        )
