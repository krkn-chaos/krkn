"""Functional coverage for native OpenShift pod outage and shaping steps."""

import time

import pytest

from lib.base import BaseScenarioTest
from lib.network import (
    collect_kraken_background,
    delete_pod,
    http_ok_and_elapsed,
    start_traffic_pod,
)
from lib.utils import assert_kraken_success, get_pods_list


@pytest.mark.functional
@pytest.mark.native_pod_network
@pytest.mark.openshift_only
@pytest.mark.xdist_group("node-resource-chaos")
class TestNativePodNetwork(BaseScenarioTest):
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_network_chaos/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pod-network-chaos-target"
    SCENARIO_NAME = "native_pod_network"
    SCENARIO_TYPE = "pod_network_scenarios"
    NAMESPACE_KEY_PATH = [0, "config", "namespace"]

    @pytest.mark.timeout(420)
    @pytest.mark.parametrize(
        "step_id",
        ["pod_network_outage", "pod_egress_shaping", "pod_ingress_shaping"],
    )
    def test_pod_traffic_impaired_and_recovers(self, kubectl, step_id):
        network = kubectl([
            "get", "network.config.openshift.io", "cluster",
            "-o", "jsonpath={.spec.networkType}",
        ], timeout=20)
        if network.returncode != 0 or network.stdout.strip() not in (
            "OpenShiftSDN", "OVNKubernetes"
        ):
            pytest.skip("Native pod network steps require an OpenShift OVS/OVN bridge")

        targets = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR).items
        assert len(targets) == 1
        target = targets[0].metadata.name
        peer = start_traffic_pod(kubectl, self.ns, prefix="native-network-peer-")
        url = "http://krkn-network-target:80/"
        try:
            baseline_ok, baseline_elapsed = http_ok_and_elapsed(
                kubectl, self.ns, peer, url
            )
            assert baseline_ok, "Peer could not reach the target before chaos"

            scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
            scenario[0]["id"] = step_id
            settings = scenario[0]["config"]
            settings["pod_name"] = target
            if step_id != "pod_network_outage":
                for key in ("direction", "ingress_ports", "egress_ports"):
                    settings.pop(key)
                settings["network_params"] = {"latency": "3s"}
                settings["execution_type"] = "parallel"
            scenario_path = self.write_scenario(
                self.tmp_path, scenario, suffix=f"_{step_id}"
            )
            config = self.build_config(
                self.SCENARIO_TYPE, str(scenario_path),
                filename=f"{step_id}_config.yaml",
            )

            proc = self.run_kraken_background(config)
            impaired = False
            try:
                deadline = time.monotonic() + 150
                while time.monotonic() < deadline and proc.poll() is None:
                    reachable, elapsed = http_ok_and_elapsed(
                        kubectl, self.ns, peer, url
                    )
                    if step_id == "pod_network_outage":
                        impaired = not reachable
                    else:
                        impaired = not reachable or elapsed >= baseline_elapsed + 1.5
                    if impaired:
                        break
                    time.sleep(1)
            finally:
                result = collect_kraken_background(proc)

            assert_kraken_success(result, context=step_id, tmp_path=self.tmp_path)
            assert impaired, f"{step_id} did not impair peer traffic"
            assert '"output_id": "success"' in result.stdout + result.stderr
            for _ in range(30):
                recovered, _ = http_ok_and_elapsed(kubectl, self.ns, peer, url)
                if recovered:
                    break
                time.sleep(2)
            assert recovered, f"Target did not recover after {step_id}"
        finally:
            delete_pod(kubectl, self.ns, peer)
