"""Pod network impairment lifecycle tests."""
import subprocess
import time

import pytest

from lib.base import BaseScenarioTest, KRAKEN_PROC_WAIT_TIMEOUT
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_failure,
    assert_kraken_success,
    assert_scenario_executed,
    get_pods_list,
    list_pods_by_prefix,
)


@pytest.mark.functional
@pytest.mark.pod_network_chaos
@pytest.mark.xdist_group("node-resource-chaos")
class TestPodNetworkChaos(BaseScenarioTest):
    """Apply pod-level network impairment and verify recovery and invalid-target handling."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_network_chaos/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pod-network-chaos-target"
    SCENARIO_NAME = "pod_network_chaos"
    SCENARIO_TYPE = "network_chaos_ng_scenarios"
    NAMESPACE_KEY_PATH = [0, "namespace"]
    OVERRIDES_KEY_PATH = [0]
    TRAFFIC_POD_PREFIX = "pod-network-traffic-"

    def _target(self):
        pods = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR).items
        assert pods, "network target did not become ready"
        return pods[0].metadata.name

    def _start_traffic_pod(self, kubectl):
        """Start a peer pod used to make traffic through the target's eth0."""
        name = f"{self.TRAFFIC_POD_PREFIX}{self.ns[-8:]}"
        created = kubectl(
            [
                "run",
                name,
                "-n",
                self.ns,
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
            ["wait", "--for=condition=Ready", f"pod/{name}", "-n", self.ns, "--timeout=90s"],
            timeout=100,
        )
        assert ready.returncode == 0, ready.stderr
        return name

    def _http_request(self, kubectl, traffic_pod, target_service):
        """Return (success, elapsed seconds) for a peer-pod HTTP request."""
        response = kubectl(
            [
                "exec",
                "-n",
                self.ns,
                traffic_pod,
                "--",
                "curl",
                "-sS",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code} %{time_total}",
                "--connect-timeout",
                "2",
                "--max-time",
                "5",
                f"http://{target_service}:80/",
            ],
            timeout=15,
        )
        if response.returncode != 0:
            return False, float("inf")
        status, _, elapsed = response.stdout.strip().partition(" ")
        try:
            return status == "200", float(elapsed)
        except ValueError:
            return False, float("inf")

    def _collect_background(self, proc):
        """Collect a background Kraken process, killing it if its bound times out."""
        try:
            stdout, stderr = proc.communicate(
                timeout=max(KRAKEN_PROC_WAIT_TIMEOUT, 180)
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        return subprocess.CompletedProcess(
            proc.args, proc.returncode, stdout, stderr
        )

    def test_latency_loss_and_recovery(self, kubectl):
        """Observe delayed peer traffic during netem and successful traffic after rollback."""
        target = self._target()
        traffic_pod = None
        target_service = "krkn-network-target"
        try:
            traffic_pod = self._start_traffic_pod(kubectl)
            baseline_ok, _ = self._http_request(
                kubectl, traffic_pod, target_service
            )
            assert baseline_ok, (
                "Peer traffic must reach the target before network chaos starts"
            )
            scenario = self.load_and_patch_scenario(
                self.repo_root,
                self.ns,
                target=target,
                test_duration=20,
                latency="2s",
                loss="10",
            )
            scenario_path = self.write_scenario(
                self.tmp_path, scenario, suffix="_traffic"
            )
            config_path = self.build_config(
                self.SCENARIO_TYPE,
                str(scenario_path),
                filename="pod_network_chaos_traffic.yaml",
            )
            proc = self.run_kraken_background(config_path)
            result = None
            try:
                # Presence of the helper proves setup has begun; request polling then
                # proves the target's externally reachable path is actually impaired.
                deadline = time.monotonic() + 120
                impaired = False
                while time.monotonic() < deadline:
                    if list_pods_by_prefix(
                        self.k8s_core, self.ns, "pod-network-chaos-"
                    ) and proc.poll() is None:
                        request_ok, elapsed = self._http_request(
                            kubectl, traffic_pod, target_service
                        )
                        if not request_ok or elapsed >= 1.0:
                            impaired = True
                            break
                    if proc.poll() is not None:
                        break
                    time.sleep(1)
                assert impaired, (
                    "Expected peer HTTP traffic to be delayed or fail while pod "
                    "network netem was active"
                )
            finally:
                result = self._collect_background(proc)
            assert_kraken_success(
                result, context=self.ns, tmp_path=self.tmp_path
            )
            assert_scenario_executed(
                result, self.SCENARIO_NAME, context=self.ns, tmp_path=self.tmp_path
            )

            deadline = time.monotonic() + 60
            restored = False
            while time.monotonic() < deadline:
                request_ok, _ = self._http_request(
                    kubectl, traffic_pod, target_service
                )
                if request_ok:
                    restored = True
                    break
                time.sleep(1)
            assert restored, "Peer HTTP traffic did not recover after tc rollback"
            after = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
            assert_all_pods_running_and_ready(after, namespace=self.ns)
        finally:
            if traffic_pod:
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

    def test_nonexistent_target_fails(self):
        """Reject a pod target that does not exist."""
        result = self.run_scenario(self.tmp_path, self.ns, overrides={"target": "no-such-pod", "test_duration": 5}, config_filename="bad-target.yaml")
        assert_kraken_failure(result, context="bad pod network target", tmp_path=self.tmp_path)
