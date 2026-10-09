"""
Functional test for the service hijacking scenario (patch a Service's selector to redirect
traffic to a configurable webservice pod for a duration, then restore).
Equivalent to CI/tests/test_service_hijacking.sh with proper assertions.
"""

import contextlib
import logging
import socket
import subprocess
import time

import pytest
import requests
from kubernetes import client

from lib.base import BaseScenarioTest, KRAKEN_PROC_WAIT_TIMEOUT
from lib.utils import (
    assert_kraken_failure,
    assert_kraken_success,
    assert_scenario_executed,
    list_pods_by_prefix,
    wait_for_no_pods_by_prefix,
)

logger = logging.getLogger(__name__)

# krkn_lib.deploy_service_hijacking names the hijacker pod "service-hijacking-pod-<random5>".
HIJACKER_POD_PREFIX = "service-hijacking-pod-"
SELECTOR_WAIT_TIMEOUT = 30
HTTP_RETRY_TIMEOUT = 10


def _free_port() -> int:
    """Ask the OS for an unused local TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _service_port_forward(repo_root, namespace: str, service_name: str, service_port: int = 80):
    """Port-forward a Service to a free local port; yields the local base URL."""
    port = _free_port()
    proc = subprocess.Popen(
        ["kubectl", "port-forward", "-n", namespace, f"service/{service_name}", f"{port}:{service_port}"],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)  # let the forward come up before the first request
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _request_with_retry(method: str, url: str, timeout_total: float = HTTP_RETRY_TIMEOUT, **kwargs):
    """Retry until the port-forward accepts connections, then return the response."""
    deadline = time.monotonic() + timeout_total
    last_exc = None
    while time.monotonic() < deadline:
        try:
            return requests.request(method, url, timeout=3, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            time.sleep(0.5)
    raise AssertionError(f"HTTP {method} {url} did not connect within {timeout_total}s: {last_exc}")


def _get_selector(k8s_core, namespace: str, service_name: str) -> dict:
    svc = k8s_core.read_namespaced_service(name=service_name, namespace=namespace)
    return dict(svc.spec.selector or {})


def _wait_for_selector_change(k8s_core, namespace: str, service_name: str, original: dict,
                               timeout: int = SELECTOR_WAIT_TIMEOUT) -> dict:
    """Poll until the Service selector differs from `original`. Return the new selector."""
    deadline = time.monotonic() + timeout
    current = original
    while time.monotonic() < deadline:
        current = _get_selector(k8s_core, namespace, service_name)
        if current != original:
            return current
        time.sleep(1)
    raise TimeoutError(
        f"Service {namespace}/{service_name} selector did not change from {original} within {timeout}s"
    )


def _wait_for_selector_restored(k8s_core, namespace: str, service_name: str, original: dict,
                                 timeout: int = SELECTOR_WAIT_TIMEOUT) -> None:
    """Poll until the Service selector matches `original` again."""
    deadline = time.monotonic() + timeout
    current = None
    while time.monotonic() < deadline:
        current = _get_selector(k8s_core, namespace, service_name)
        if current == original:
            return
        time.sleep(1)
    raise TimeoutError(
        f"Service {namespace}/{service_name} selector did not restore to {original} within {timeout}s "
        f"(last={current})"
    )


@pytest.mark.functional
@pytest.mark.service_hijacking
class TestServiceHijacking(BaseScenarioTest):
    """Service hijacking scenario: patch a Service selector to a hijacker webservice, then restore."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/service_hijacking/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "scenario=hijack"
    SCENARIO_NAME = "service_hijacking"
    SCENARIO_TYPE = "service_hijacking_scenarios"
    NAMESPACE_KEY_PATH = ["service_namespace"]
    NAMESPACE_IS_REGEX = False
    OVERRIDES_KEY_PATH = []  # scenario fields are top-level; overrides patch them directly

    SERVICE_NAME = "nginx-service"
    SERVICE_NAME_NUMERIC = "nginx-service-numeric"
    SERVICE_NAME_UNPATCHABLE = "nginx-service-unpatchable"

    @pytest.mark.order(1)
    def test_hijack_plan_steps_and_restore(self):
        """Rows 1-3, 6, 7: selector is patched, GET/POST on /list/index.php and PATCH on /patch
        return each step's configured status/payload/MIME, then the original selector is
        restored and the hijacker pod is undeployed."""
        ns = self.ns
        original_selector = _get_selector(self.k8s_core, ns, self.SERVICE_NAME)

        scenario = self.load_and_patch_scenario(self.repo_root, ns, chaos_duration=12)
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_plan")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="hijack_plan_config.yaml"
        )
        proc = self.run_kraken_background(config_path)
        try:
            hijacked_selector = _wait_for_selector_change(self.k8s_core, ns, self.SERVICE_NAME, original_selector)
            assert hijacked_selector, f"Expected a new selector after hijack (namespace={ns})"

            with _service_port_forward(self.repo_root, ns, self.SERVICE_NAME) as base_url:
                # Step 1 window (~0-6s).
                resp = _request_with_retry("GET", f"{base_url}/list/index.php")
                assert resp.status_code == 500, f"Step 1 GET status (namespace={ns}): {resp.status_code}"
                assert resp.json() == {"status": "internal server error"}, f"Step 1 GET payload (namespace={ns})"
                assert resp.headers.get("content-type", "").startswith("application/json"), (
                    f"Step 1 GET MIME (namespace={ns}): {resp.headers.get('content-type')}"
                )

                resp = _request_with_retry("POST", f"{base_url}/list/index.php")
                assert resp.status_code == 401, f"Step 1 POST status (namespace={ns}): {resp.status_code}"
                assert resp.json() == {"status": "unauthorized"}, f"Step 1 POST payload (namespace={ns})"

                resp = _request_with_retry("PATCH", f"{base_url}/patch")
                assert resp.status_code == 201, f"Step 1 PATCH status (namespace={ns}): {resp.status_code}"
                assert resp.text.strip() == "resource patched", f"Step 1 PATCH payload (namespace={ns})"

                # Cross into step 2's window.
                time.sleep(7)

                resp = _request_with_retry("GET", f"{base_url}/list/index.php")
                assert resp.status_code == 201, f"Step 2 GET status (namespace={ns}): {resp.status_code}"
                assert resp.json() == {"status": "resource created"}, f"Step 2 GET payload (namespace={ns})"

                resp = _request_with_retry("POST", f"{base_url}/list/index.php")
                assert resp.status_code == 404, f"Step 2 POST status (namespace={ns}): {resp.status_code}"
                assert resp.text.strip() == "not found", f"Step 2 POST payload (namespace={ns})"

                resp = _request_with_retry("PATCH", f"{base_url}/patch")
                assert resp.status_code == 400, f"Step 2 PATCH status (namespace={ns}): {resp.status_code}"
                assert resp.text.strip() == "bad request", f"Step 2 PATCH payload (namespace={ns})"

            proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)
            stdout = proc.stdout.read() if proc.stdout else ""
            stderr = proc.stderr.read() if proc.stderr else ""
        except Exception:
            if proc.poll() is None:
                proc.terminate()
            raise
        result = subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        assert_scenario_executed(result, self.SCENARIO_NAME, context=f"namespace={ns}", tmp_path=self.tmp_path)

        # Row 6: original selector restored.
        _wait_for_selector_restored(self.k8s_core, ns, self.SERVICE_NAME, original_selector)
        # Row 7: hijacker pod undeployed.
        wait_for_no_pods_by_prefix(self.k8s_core, ns, HIJACKER_POD_PREFIX, timeout=30)

    def _single_step_scenario(self, ns: str, service_name: str, service_target_port, chaos_duration: int = 6):
        """Build a minimal one-resource/one-step plan for the port-targeting tests."""
        scenario = self.load_and_patch_scenario(self.repo_root, ns, chaos_duration=chaos_duration)
        scenario["service_name"] = service_name
        scenario["service_target_port"] = service_target_port
        scenario["plan"] = [
            {
                "resource": "/list/index.php",
                "steps": {
                    "GET": [
                        {
                            "duration": chaos_duration,
                            "status": 200,
                            "mime_type": "text/plain",
                            "payload": "ok",
                        }
                    ]
                },
            }
        ]
        return scenario

    def test_named_port_targeting(self):
        """Row 4: service_target_port as a named port ("http-web-svc") routes traffic correctly."""
        ns = self.ns
        scenario = self._single_step_scenario(ns, self.SERVICE_NAME, "http-web-svc")
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_named_port")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="hijack_named_port_config.yaml"
        )
        original_selector = _get_selector(self.k8s_core, ns, self.SERVICE_NAME)
        proc = self.run_kraken_background(config_path)
        try:
            _wait_for_selector_change(self.k8s_core, ns, self.SERVICE_NAME, original_selector)
            with _service_port_forward(self.repo_root, ns, self.SERVICE_NAME) as base_url:
                resp = _request_with_retry("GET", f"{base_url}/list/index.php")
                assert resp.status_code == 200 and resp.text.strip() == "ok", (
                    f"Named-port hijack response (namespace={ns}): {resp.status_code} {resp.text!r}"
                )
        finally:
            proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)
        assert proc.returncode == 0, f"Kraken exited {proc.returncode} (namespace={ns})"

    def test_numeric_port_targeting(self):
        """Row 5: service_target_port as an integer (80) routes traffic correctly."""
        ns = self.ns
        scenario = self._single_step_scenario(ns, self.SERVICE_NAME_NUMERIC, 80)
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_numeric_port")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="hijack_numeric_port_config.yaml"
        )
        original_selector = _get_selector(self.k8s_core, ns, self.SERVICE_NAME_NUMERIC)
        proc = self.run_kraken_background(config_path)
        try:
            _wait_for_selector_change(self.k8s_core, ns, self.SERVICE_NAME_NUMERIC, original_selector)
            with _service_port_forward(self.repo_root, ns, self.SERVICE_NAME_NUMERIC) as base_url:
                resp = _request_with_retry("GET", f"{base_url}/list/index.php")
                assert resp.status_code == 200 and resp.text.strip() == "ok", (
                    f"Numeric-port hijack response (namespace={ns}): {resp.status_code} {resp.text!r}"
                )
        finally:
            proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)
        assert proc.returncode == 0, f"Kraken exited {proc.returncode} (namespace={ns})"

    def test_rollback_on_interruption(self):
        """Row 11: interrupting a running scenario leaves rollback state on disk; `execute-rollback`
        restores the original selector and removes the hijacker pod."""
        ns = self.ns
        original_selector = _get_selector(self.k8s_core, ns, self.SERVICE_NAME)
        scenario = self.load_and_patch_scenario(self.repo_root, ns, chaos_duration=60)
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_rollback")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="hijack_rollback_config.yaml"
        )
        proc = self.run_kraken_background(config_path)

        # Drain stdout/stderr in background threads to prevent OS pipe buffer
        # deadlock (~64 KiB limit) during the long selector-change wait.
        import threading
        def _drain(stream):
            try:
                for _ in stream:
                    pass
            except Exception:
                pass
        threading.Thread(target=_drain, args=(proc.stdout,), daemon=True).start()
        threading.Thread(target=_drain, args=(proc.stderr,), daemon=True).start()

        try:
            _wait_for_selector_change(self.k8s_core, ns, self.SERVICE_NAME, original_selector)
            hijacker_pods = list_pods_by_prefix(self.k8s_core, ns, HIJACKER_POD_PREFIX)
            assert hijacker_pods, f"Expected a hijacker pod before interruption (namespace={ns})"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=KRAKEN_PROC_WAIT_TIMEOUT)

        rollback_result = self.run_kraken(config_path, extra_args=["execute-rollback"])
        assert rollback_result.returncode == 0, (
            f"execute-rollback failed (namespace={ns}): {rollback_result.stderr}"
        )
        _wait_for_selector_restored(self.k8s_core, ns, self.SERVICE_NAME, original_selector)
        wait_for_no_pods_by_prefix(self.k8s_core, ns, HIJACKER_POD_PREFIX, timeout=30)

    @pytest.mark.no_workload
    def test_nonexistent_service_fails(self):
        """Row 8: targeting a Service that doesn't exist causes Kraken to exit non-zero."""
        ns = self.ns
        scenario = self.load_and_patch_scenario(self.repo_root, ns, chaos_duration=3)
        scenario["service_name"] = "nonexistent-svc"
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_missing_svc")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="hijack_missing_svc_config.yaml"
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(result, context=f"namespace={ns}", tmp_path=self.tmp_path)
        combined = f"{result.stdout or ''}\n{result.stderr or ''}"
        assert "not found in namespace" in combined, (
            f"Expected 'not found in namespace' in Krkn output (namespace={ns})"
        )

    @pytest.mark.no_workload
    def test_nonexistent_namespace_fails(self):
        """Row 9: targeting a namespace that doesn't exist causes Kraken to exit non-zero."""
        scenario = self.load_and_patch_scenario(self.repo_root, "nonexistent-namespace-xyz-12345", chaos_duration=3)
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_bad_ns")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="hijack_bad_ns_config.yaml"
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(result, context=f"test namespace={self.ns}", tmp_path=self.tmp_path)

    @pytest.mark.no_workload
    def test_service_patch_failure(self):
        """Row 10: an ExternalName Service structurally rejects a selector patch (the API server
        forbids spec.selector when type=ExternalName), simulating a service that can't be patched."""
        ns = self.ns
        body = client.V1Service(
            metadata=client.V1ObjectMeta(name=self.SERVICE_NAME_UNPATCHABLE),
            spec=client.V1ServiceSpec(type="ExternalName", external_name="example.com"),
        )
        self.k8s_core.create_namespaced_service(namespace=ns, body=body)

        scenario = self.load_and_patch_scenario(self.repo_root, ns, chaos_duration=3)
        scenario["service_name"] = self.SERVICE_NAME_UNPATCHABLE
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="_unpatchable")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(scenario_path), filename="hijack_unpatchable_config.yaml"
        )
        result = self.run_kraken(config_path)
        assert_kraken_failure(result, context=f"namespace={ns}", tmp_path=self.tmp_path)