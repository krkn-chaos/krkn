"""Service hijacking plan and rollback integration tests."""
import re
import subprocess
import time

import pytest
from kubernetes.client.rest import ApiException

from lib.base import BaseScenarioTest
from lib.utils import assert_kraken_failure, assert_kraken_success, assert_scenario_executed


def _start_traffic_pod(kubectl, namespace):
    """Start a curl client in-cluster so requests follow Service endpoint changes."""
    name = f"service-hijacking-traffic-{namespace[-8:]}"
    created = kubectl(
        [
            "run",
            name,
            "-n",
            namespace,
            "--image=curlimages/curl:8.10.1",
            "--restart=Never",
            "--command",
            "--",
            "sleep",
            "300",
        ],
        timeout=60,
    )
    assert created.returncode == 0, created.stderr
    ready = kubectl(
        ["wait", "--for=condition=Ready", f"pod/{name}", "-n", namespace, "--timeout=90s"],
        timeout=100,
    )
    assert ready.returncode == 0, ready.stderr
    return name


def _service_plan_response(kubectl, namespace, client_pod):
    """Return the status/body from an in-cluster request to the hijacked Service."""
    response = kubectl(
        [
            "exec",
            "-n",
            namespace,
            client_pod,
            "--",
            "curl",
            "-sS",
            "-w",
            "\n%{http_code}",
            "--connect-timeout",
            "2",
            "--max-time",
            "5",
            "http://nginx-service:80/list/index.php",
        ],
        timeout=15,
    )
    if response.returncode != 0:
        return None
    body, separator, status = response.stdout.rpartition("\n")
    if not separator or not status.isdigit():
        return None
    return int(status), body


@pytest.mark.functional
@pytest.mark.service_hijacking
@pytest.mark.xdist_group("service_hijacking")
class TestServiceHijacking(BaseScenarioTest):
    """Exercise service hijacking plan execution and rollback behavior."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/service_hijacking/resource.yaml"
    LABEL_SELECTOR = "app=nginx"
    SCENARIO_NAME = "service_hijacking"
    SCENARIO_TYPE = "service_hijacking_scenarios"
    NAMESPACE_KEY_PATH = ["service_namespace"]
    OVERRIDES_KEY_PATH = []

    def test_plan_runs_and_restores_service(self, kubectl):
        """Observe selector redirection and response-plan output, then verify full rollback."""
        service_name = "nginx-service"
        service = self.k8s_core.read_namespaced_service(service_name, self.ns)
        original_selector = dict(service.spec.selector or {})
        original_pods = self.k8s_core.list_namespaced_pod(
            namespace=self.ns, label_selector=self.LABEL_SELECTOR
        ).items
        assert len(original_pods) == 1, f"Expected one original service pod, found {original_pods}"
        original_pod = original_pods[0]
        assert original_selector == {"app": "nginx"}

        traffic_pod = _start_traffic_pod(kubectl, self.ns)
        proc = None
        try:
            scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
            path = self.write_scenario(self.tmp_path, scenario, suffix="-observe-plan")
            config_path = self.build_config(
                self.SCENARIO_TYPE, str(path), filename="observe-plan.yaml"
            )
            proc = self.run_kraken_background(config_path)
            redirected_selector = None
            plan_response = None
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and proc.poll() is None:
                current_service = self.k8s_core.read_namespaced_service(
                    service_name, self.ns
                )
                selector = dict(current_service.spec.selector or {})
                if selector != original_selector:
                    redirected_selector = selector
                    response = _service_plan_response(
                        kubectl, self.ns, traffic_pod
                    )
                    if response and (
                        (response[0] == 500 and "internal server error" in response[1])
                        or (response[0] == 201 and "resource created" in response[1])
                    ):
                        plan_response = response
                        break
                time.sleep(1)
            assert redirected_selector and redirected_selector != original_selector, (
                f"Service selector never redirected from {original_selector}"
            )
            assert plan_response is not None, (
                "The hijacked Service never returned either configured response-plan result"
            )

            proc.wait(timeout=120)
            stdout, stderr = proc.communicate()
            result = subprocess.CompletedProcess(
                proc.args, proc.returncode, stdout=stdout, stderr=stderr
            )
            assert_kraken_success(result, context=self.ns, tmp_path=self.tmp_path)
            assert_scenario_executed(
                result, self.SCENARIO_NAME, context=self.ns, tmp_path=self.tmp_path
            )
            output = f"{result.stdout or ''}\n{result.stderr or ''}"
            assert "successfully deployed pod:" in output
            assert "selectors successfully restored" in output
            assert "undeploying service-hijacking resources" in output
            hijacker_match = re.search(r"successfully deployed pod:\s+(\S+)", output)
            assert hijacker_match, "Scenario output did not identify the hijacker pod"
            hijacker_name = hijacker_match.group(1)

            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                restored = self.k8s_core.read_namespaced_service(
                    service_name, self.ns
                )
                current_selector = dict(restored.spec.selector or {})
                try:
                    self.k8s_core.read_namespaced_pod(hijacker_name, self.ns)
                    hijacker_present = True
                except ApiException as error:
                    if error.status != 404:
                        raise
                    hijacker_present = False
                endpoints = self.k8s_core.read_namespaced_endpoints(
                    service_name, self.ns
                )
                endpoint_names = [
                    address.target_ref.name
                    for subset in (endpoints.subsets or [])
                    for address in (subset.addresses or [])
                    if address.target_ref and address.target_ref.name
                ]
                if (
                    current_selector == original_selector
                    and not hijacker_present
                    and original_pod.metadata.name in endpoint_names
                ):
                    break
                time.sleep(1)
            else:
                pytest.fail(
                    "Service selector, hijacker pod, and endpoint set did not return to the original state"
                )

            final_pods = self.k8s_core.list_namespaced_pod(
                namespace=self.ns, label_selector=self.LABEL_SELECTOR
            ).items
            assert [(pod.metadata.name, pod.metadata.uid) for pod in final_pods] == [
                (original_pod.metadata.name, original_pod.metadata.uid)
            ]
        finally:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=20)
            kubectl(
                [
                    "delete",
                    "pod",
                    traffic_pod,
                    "-n",
                    self.ns,
                    "--ignore-not-found=true",
                    "--wait=true",
                ],
                timeout=90,
            )

    def test_missing_service_fails(self):
        """Fail when the configured Service does not exist."""
        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        scenario["service_name"] = "missing-service"
        path = self.write_scenario(self.tmp_path, scenario, suffix="-missing")
        config = self.build_config(self.SCENARIO_TYPE, str(path), filename="missing-service.yaml")
        result = self.run_kraken(config)
        assert_kraken_failure(result, context="missing hijack service", tmp_path=self.tmp_path)
