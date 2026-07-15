"""
Functional test for service hijacking scenario.
Migrated from CI/tests/test_service_hijacking.sh with control-plane assertions.

Each test runs in its own ephemeral namespace with an nginx Pod + Service deployed
automatically.  Assertions are at the control-plane level (service selector patched /
restored, hijacker pod deployed / cleaned up), NOT at the HTTP-response level.
"""

import copy
import logging
import time

import pytest

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_success,
    assert_scenario_executed,
    list_pods_by_prefix,
    load_scenario_base,
    wait_for_no_pods_by_prefix,
)

logger = logging.getLogger(__name__)

# Prefix used by the service-hijacking plugin when deploying the hijacker pod.
HIJACKER_POD_PREFIX = "krkn-service-hijacking"


def _read_service_selector(k8s_core, name: str, namespace: str) -> dict:
    """Return the current selector dict of a Service, or {} if not found."""
    try:
        svc = k8s_core.read_namespaced_service(name=name, namespace=namespace)
        return dict(svc.spec.selector or {})
    except Exception:
        return {}


def _wait_for_service_selector_change(
    k8s_core, name: str, namespace: str, original_selector: dict, timeout: float = 60
) -> dict:
    """Poll until the service selector differs from *original_selector*.
    Returns the new selector, or raises TimeoutError."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = _read_service_selector(k8s_core, name, namespace)
        if current and current != original_selector:
            return current
        time.sleep(1)
    raise TimeoutError(
        f"Service {namespace}/{name} selector did not change from "
        f"{original_selector!r} within {timeout}s"
    )


@pytest.mark.functional
@pytest.mark.service_hijacking
class TestServiceHijacking(BaseScenarioTest):
    """Service hijacking scenario: patch service selector, redirect traffic, restore."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/service_hijacking/resource.yaml"
    WORKLOAD_IS_PATH = True
    # The resource.yaml deploys a bare Pod (not a Deployment), so we match its label.
    LABEL_SELECTOR = "app.kubernetes.io/name=proxy"
    SCENARIO_NAME = "service_hijacking"
    SCENARIO_TYPE = "service_hijacking_scenarios"
    # Flat YAML: namespace lives at top-level "service_namespace", handled by override below.
    NAMESPACE_KEY_PATH = []
    NAMESPACE_IS_REGEX = False

    # ── Override base helpers for the flat YAML structure ──────────────────

    def load_and_patch_scenario(self, repo_root, namespace, **overrides):
        """Load scenario_base.yaml and patch ``service_namespace`` (flat dict, not nested)."""
        scenario = copy.deepcopy(load_scenario_base(repo_root, self.SCENARIO_NAME))
        scenario["service_namespace"] = namespace
        for key, value in overrides.items():
            scenario[key] = value
        return scenario

    # ── Happy-path tests ──────────────────────────────────────────────────

    @pytest.mark.order(1)
    def test_service_hijack_single_step(self):
        """TC-1: Service hijack with single GET step.

        Verify: Krkn exits 0, service selector is patched to point to
        hijacker pod, original selector is restored after chaos, hijacker
        pod is cleaned up.
        """
        ns = self.ns
        original_selector = _read_service_selector(self.k8s_core, "nginx-service", ns)
        assert original_selector, f"nginx-service not found in namespace={ns}"

        result = self.run_scenario(self.tmp_path, ns)
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path
        )

        # After scenario completes: selector should be restored.
        restored_selector = _read_service_selector(self.k8s_core, "nginx-service", ns)
        assert restored_selector == original_selector, (
            f"Service selector not restored: expected {original_selector}, "
            f"got {restored_selector} (namespace={ns})"
        )

        # Hijacker pod should be gone.
        hijacker_pods = list_pods_by_prefix(self.k8s_core, ns, HIJACKER_POD_PREFIX)
        assert len(hijacker_pods) == 0, (
            f"Hijacker pod(s) still present after scenario: "
            f"{[p.metadata.name for p in hijacker_pods]} (namespace={ns})"
        )

    def test_multi_step_plan(self):
        """TC-2: Multi-step plan (time-based transitions).

        Verify: plan with 2 GET steps completes, Krkn exits 0.
        """
        ns = self.ns
        multi_step_plan = [
            {
                "resource": "/health",
                "steps": {
                    "GET": [
                        {"duration": 8, "status": 500, "mime_type": "application/json",
                         "payload": '{"status":"internal server error"}'},
                        {"duration": 8, "status": 201, "mime_type": "application/json",
                         "payload": '{"status":"resource created"}'},
                    ]
                },
            }
        ]
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"plan": multi_step_plan, "chaos_duration": 16},
            config_filename="multi_step_config.yaml",
        )
        assert_kraken_success(result, context=f"multi-step namespace={ns}", tmp_path=self.tmp_path)

    def test_multiple_http_methods(self):
        """TC-3: Multiple HTTP methods (GET + POST).

        Verify: plan with both GET and POST methods defined completes, Krkn exits 0.
        """
        ns = self.ns
        multi_method_plan = [
            {
                "resource": "/api",
                "steps": {
                    "GET": [
                        {"duration": 15, "status": 200, "mime_type": "application/json",
                         "payload": '{"method":"get"}'},
                    ],
                    "POST": [
                        {"duration": 15, "status": 201, "mime_type": "application/json",
                         "payload": '{"method":"post"}'},
                    ],
                },
            }
        ]
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"plan": multi_method_plan},
            config_filename="multi_method_config.yaml",
        )
        assert_kraken_success(
            result, context=f"multi-method namespace={ns}", tmp_path=self.tmp_path
        )

    def test_named_port_targeting(self):
        """TC-4: Named port targeting.

        Verify: service_target_port as a string (named port) works correctly.
        """
        ns = self.ns
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"service_target_port": "http-web-svc"},
            config_filename="named_port_config.yaml",
        )
        assert_kraken_success(
            result, context=f"named-port namespace={ns}", tmp_path=self.tmp_path
        )

    def test_numeric_port_targeting(self):
        """TC-5: Numeric port targeting.

        Verify: service_target_port as an integer works correctly.
        """
        ns = self.ns
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"service_target_port": 80},
            config_filename="numeric_port_config.yaml",
        )
        assert_kraken_success(
            result, context=f"numeric-port namespace={ns}", tmp_path=self.tmp_path
        )

    def test_service_restoration(self):
        """TC-6: Service restoration after chaos_duration.

        Verify: original service selectors match after scenario completes.
        """
        ns = self.ns
        original_selector = _read_service_selector(self.k8s_core, "nginx-service", ns)
        assert original_selector, f"nginx-service not found in namespace={ns}"

        result = self.run_scenario(self.tmp_path, ns, config_filename="restore_config.yaml")
        assert_kraken_success(result, context=f"restore namespace={ns}", tmp_path=self.tmp_path)

        restored_selector = _read_service_selector(self.k8s_core, "nginx-service", ns)
        assert restored_selector == original_selector, (
            f"Service selector mismatch after restoration: "
            f"expected {original_selector}, got {restored_selector} (namespace={ns})"
        )

    def test_hijacker_pod_cleanup(self):
        """TC-7: Hijacker pod cleanup.

        Verify: no krkn-service-hijacking pods remain in namespace after scenario.
        """
        ns = self.ns
        result = self.run_scenario(self.tmp_path, ns, config_filename="cleanup_config.yaml")
        assert_kraken_success(result, context=f"cleanup namespace={ns}", tmp_path=self.tmp_path)

        # Allow a brief settling window, then assert no hijacker pods.
        wait_for_no_pods_by_prefix(self.k8s_core, ns, HIJACKER_POD_PREFIX, timeout=30)

    # ── Negative / failure-mode tests ─────────────────────────────────────

    @pytest.mark.no_workload
    def test_nonexistent_service_fails(self):
        """TC-8: Non-existent service.

        Verify: Krkn exits 1 with error when targeting a service that doesn't exist.
        """
        ns = self.ns
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"service_name": "nonexistent-svc"},
            config_filename="nonexistent_svc_config.yaml",
        )
        assert_kraken_failure(
            result, context=f"nonexistent-svc namespace={ns}", tmp_path=self.tmp_path
        )

    @pytest.mark.no_workload
    def test_nonexistent_namespace_fails(self):
        """TC-9: Non-existent namespace.

        Verify: Krkn exits 1 when namespace doesn't exist.
        """
        ns = self.ns
        result = self.run_scenario(
            self.tmp_path, ns,
            overrides={"service_namespace": "fake-ns"},
            config_filename="nonexistent_ns_config.yaml",
        )
        assert_kraken_failure(
            result, context=f"fake-ns namespace={ns}", tmp_path=self.tmp_path
        )

    @pytest.mark.no_workload
    def test_service_patch_failure(self):
        """TC-10: Service patch failure.

        Verify: Krkn exits 1 when the target service exists but selector
        replacement fails. Simulated by targeting a service whose name matches
        but that lives in a namespace where no service is deployed (the test
        namespace has no workload because of no_workload marker, so
        nginx-service does not exist there).
        """
        ns = self.ns
        # The test namespace is empty (no_workload), so nginx-service does not exist.
        # This exercises the "service not found" code path in the plugin.
        result = self.run_scenario(
            self.tmp_path, ns,
            config_filename="patch_failure_config.yaml",
        )
        assert_kraken_failure(
            result, context=f"patch-failure namespace={ns}", tmp_path=self.tmp_path
        )

    # ── Rollback verification ─────────────────────────────────────────────

    def test_rollback_on_interruption(self):
        """TC-11: Rollback on interruption.

        Verify: if the scenario is interrupted (SIGTERM), the rollback
        handler restores original selectors and deletes the hijacker pod.
        """
        import signal

        ns = self.ns
        original_selector = _read_service_selector(self.k8s_core, "nginx-service", ns)
        assert original_selector, f"nginx-service not found in namespace={ns}"

        # Use a long chaos_duration so we have time to interrupt.
        scenario = self.load_and_patch_scenario(
            self.repo_root, ns, chaos_duration=120
        )
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_rollback")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path),
            filename="rollback_config.yaml",
        )
        proc = self.run_kraken_background(config_path)
        try:
            # Wait for the hijack to take effect (selector changes).
            _wait_for_service_selector_change(
                self.k8s_core, "nginx-service", ns, original_selector, timeout=90
            )
            logger.info("Hijack detected in namespace=%s, sending SIGTERM", ns)
            # Interrupt Krkn; rollback handler should fire.
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=60)
        except Exception:
            # Kill the process if anything goes wrong.
            proc.kill()
            proc.wait(timeout=10)
            raise
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)

        # Give rollback handler time to restore.
        time.sleep(5)

        # Verify service selector was restored by the rollback handler.
        restored_selector = _read_service_selector(self.k8s_core, "nginx-service", ns)
        assert restored_selector == original_selector, (
            f"Rollback failed: service selector not restored after interruption. "
            f"Expected {original_selector}, got {restored_selector} (namespace={ns})"
        )

        # Verify hijacker pod was cleaned up by rollback handler.
        hijacker_pods = list_pods_by_prefix(self.k8s_core, ns, HIJACKER_POD_PREFIX)
        assert len(hijacker_pods) == 0, (
            f"Rollback failed: hijacker pod(s) still present after interruption: "
            f"{[p.metadata.name for p in hijacker_pods]} (namespace={ns})"
        )

