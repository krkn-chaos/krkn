"""
Functional test for application outage scenario (block network to target pods, then restore).
Equivalent to CI/tests/test_app_outages.sh with proper assertions.
Each test runs in its own ephemeral namespace with workload deployed automatically.
"""

import copy
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
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_success,
    assert_pod_count_unchanged,
    find_network_policy_by_prefix,
    get_network_policies_list,
    get_pods_list,
    load_scenario_base,
    patch_namespace_in_docs,
    scenario_dir,
    wait_for_deployment_ready,
)


def _load_and_patch_scenario(repo_root, namespace: str, **overrides):
    """Load scenario_base.yaml and patch namespace and any overrides (duration, block, exclude_label)."""
    scenario = copy.deepcopy(load_scenario_base(repo_root, "application_outage"))
    scenario["application_outage"]["namespace"] = namespace
    for key, value in overrides.items():
        if key == "namespace":
            scenario["application_outage"]["namespace"] = value
        else:
            scenario["application_outage"][key] = value
    return scenario


def _write_scenario(tmp_path, scenario_dict, filename="app_outage_scenario.yaml"):
    path = tmp_path / filename
    with open(path, "w") as f:
        yaml.dump(scenario_dict, f, default_flow_style=False, sort_keys=False)
    return path


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

    @pytest.mark.order(1)
    def test_app_outage_block_and_restore(
        self, build_config, run_kraken, k8s_core, tmp_path, repo_root
    ):
        ns = self.ns
        before = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)
        before_count = len(before.items)

        scenario_path = _write_scenario(tmp_path, _load_and_patch_scenario(repo_root, ns))
        config_path = build_config(
            "application_outages_scenarios",
            str(scenario_path),
            filename="app_outage_config.yaml",
        )
        result = run_kraken(config_path)
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=tmp_path)

        after = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)
        assert_all_pods_running_and_ready(after, namespace=ns)

    def test_network_policy_created_then_deleted(
        self, build_config, run_kraken_background, k8s_networking, tmp_path, repo_root
    ):
        """NetworkPolicy with prefix krkn-deny- is created during run and deleted after."""
        ns = self.ns
        scenario = _load_and_patch_scenario(repo_root, ns, duration=12)
        scenario_path = _write_scenario(tmp_path, scenario)
        config_path = build_config(
            "application_outages_scenarios", str(scenario_path),
            filename="app_outage_np_lifecycle.yaml",
        )
        proc = run_kraken_background(config_path)
        try:
            policy_name = _wait_for_network_policy(
                k8s_networking, ns, self.POLICY_PREFIX, timeout=POLICY_WAIT_TIMEOUT
            )
            assert policy_name.startswith(self.POLICY_PREFIX), (
                f"Policy name {policy_name!r} should start with {self.POLICY_PREFIX!r} (namespace={ns})"
            )
            policy_list = get_network_policies_list(k8s_networking, ns)
            policy = find_network_policy_by_prefix(policy_list, self.POLICY_PREFIX)
            assert policy is not None and policy.spec is not None, (
                f"Expected NetworkPolicy with spec (namespace={ns})"
            )
            assert policy.spec.pod_selector is not None, f"Policy should have pod_selector (namespace={ns})"
            assert policy.spec.policy_types is not None, f"Policy should have policy_types (namespace={ns})"
        finally:
            proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)
        _assert_no_network_policy_with_prefix(k8s_networking, ns, self.POLICY_PREFIX)

    def test_traffic_blocked_during_outage(
        self,
        build_config,
        run_kraken_background,
        k8s_client,
        k8s_apps,
        k8s_networking,
        kubectl,
        tmp_path,
        repo_root,
    ):
        """During outage, ingress to target pods is blocked; after run, traffic is restored."""
        ns = self.ns
        nginx_path = scenario_dir(repo_root, "application_outage") / "nginx_http.yaml"
        docs = list(yaml.safe_load_all(nginx_path.read_text()))
        docs = patch_namespace_in_docs(docs, ns)
        try:
            k8s_utils.create_from_yaml(
                k8s_client,
                yaml_objects=docs,
                namespace=ns,
            )
        except k8s_utils.FailToCreateError as e:
            msgs = [str(exc) for exc in e.api_exceptions]
            raise AssertionError(
                f"Failed to create nginx resources (namespace={ns}): {'; '.join(msgs)}"
            ) from e
        wait_for_deployment_ready(k8s_apps, ns, "nginx-outage-http", timeout=READINESS_TIMEOUT)
        port = _get_free_port()
        pf = subprocess.Popen(
            ["kubectl", "port-forward", "-n", ns, "service/nginx-outage-http", f"{port}:80"],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{port}/"
        try:
            time.sleep(2)
            baseline_ok = False
            for _ in range(10):
                try:
                    resp = requests.get(url, timeout=3)
                    if resp.ok:
                        baseline_ok = True
                        break
                except (requests.ConnectionError, requests.Timeout):
                    pass
                time.sleep(1)
            assert baseline_ok, f"Baseline: HTTP request to nginx should succeed (namespace={ns})"

            scenario = _load_and_patch_scenario(repo_root, ns, duration=15)
            scenario_path = _write_scenario(tmp_path, scenario, "app_outage_traffic.yaml")
            config_path = build_config(
                "application_outages_scenarios", str(scenario_path),
                filename="app_outage_traffic_config.yaml",
            )
            proc = run_kraken_background(config_path)
            policy_name = _wait_for_network_policy(
                k8s_networking, ns, self.POLICY_PREFIX, timeout=POLICY_WAIT_TIMEOUT
            )
            assert policy_name, f"Expected policy to exist (namespace={ns})"
            time.sleep(2)
            failed = False
            for _ in range(5):
                try:
                    resp = requests.get(url, timeout=2)
                    if not resp.ok:
                        failed = True
                        break
                except (requests.ConnectionError, requests.Timeout):
                    failed = True
                    break
                time.sleep(1)
            assert failed, f"During outage, HTTP request to nginx should fail (namespace={ns})"
            proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)
            time.sleep(1)
            resp = requests.get(url, timeout=5)
            assert resp.ok, f"After scenario, HTTP request to nginx should succeed (namespace={ns})"
        finally:
            pf.terminate()
            pf.wait(timeout=5)

    @pytest.mark.parametrize(
        "block_type",
        [["Ingress"], ["Egress"], ["Ingress", "Egress"]],
        ids=["Ingress", "Egress", "Ingress_Egress"],
    )
    def test_block_type_variants(
        self, build_config, run_kraken, k8s_core, tmp_path, block_type, repo_root
    ):
        """Scenario runs successfully with Ingress-only, Egress-only, or both."""
        ns = self.ns
        before = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)
        scenario = _load_and_patch_scenario(repo_root, ns, block=block_type)
        block_id = "_".join(block_type).lower()
        scenario_path = _write_scenario(tmp_path, scenario, f"app_outage_block_{block_id}.yaml")
        config_path = build_config(
            "application_outages_scenarios", str(scenario_path),
            filename=f"app_outage_block_{block_id}_config.yaml",
        )
        result = run_kraken(config_path)
        assert_kraken_success(result, context=f"block={block_type} namespace={ns}", tmp_path=tmp_path)
        after = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)
        assert_all_pods_running_and_ready(after, namespace=ns)

    def test_exclude_label_e2e(
        self, build_config, run_kraken, k8s_core, tmp_path, repo_root
    ):
        """Scenario with exclude_label (matchExpressions) runs and restores."""
        ns = self.ns
        before = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)
        scenario = _load_and_patch_scenario(repo_root, ns, exclude_label={"env": "prod"})
        scenario_path = _write_scenario(tmp_path, scenario, "app_outage_exclude.yaml")
        config_path = build_config(
            "application_outages_scenarios", str(scenario_path),
            filename="app_outage_exclude_config.yaml",
        )
        result = run_kraken(config_path)
        assert_kraken_success(result, context=f"exclude_label namespace={ns}", tmp_path=tmp_path)
        after = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)

    @pytest.mark.no_workload
    def test_invalid_scenario_fails(
        self, build_config, run_kraken, tmp_path
    ):
        """Invalid scenario file (missing application_outage) causes Kraken to exit non-zero."""
        invalid_scenario_path = tmp_path / "invalid_scenario.yaml"
        invalid_scenario_path.write_text("foo: bar\n")
        config_path = build_config(
            "application_outages_scenarios", str(invalid_scenario_path),
            filename="invalid_config.yaml",
        )
        result = run_kraken(config_path)
        assert result.returncode != 0, (
            "Invalid scenario should cause Kraken to fail (namespace=%s)" % self.ns
        )

    @pytest.mark.no_workload
    def test_bad_namespace_fails(
        self, build_config, run_kraken, tmp_path, repo_root
    ):
        """Scenario targeting non-existent namespace causes Kraken to exit non-zero."""
        scenario = _load_and_patch_scenario(repo_root, "nonexistent-namespace-xyz-12345")
        scenario_path = _write_scenario(tmp_path, scenario, "app_outage_bad_ns.yaml")
        config_path = build_config(
            "application_outages_scenarios", str(scenario_path),
            filename="app_outage_bad_ns_config.yaml",
        )
        result = run_kraken(config_path)
        assert result.returncode != 0, (
            "Non-existent namespace should cause Kraken to fail (test namespace=%s)" % self.ns
        )
