"""Pod and node time-action integration coverage."""
import copy
import subprocess
import time

import pytest

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_failure,
    assert_kraken_success,
    container_runtime,
    get_pods_list,
    schedulable_worker_nodes,
    wait_node_ready,
)


def _pod_epoch(kubectl, namespace, pod_name):
    """Read the pod clock without changing it."""
    result = kubectl(
        ["exec", "-n", namespace, pod_name, "-c", "app", "--", "date", "-u", "+%s"]
    )
    if result.returncode != 0:
        raise AssertionError(f"Unable to read pod clock: {result.stderr}")
    return int(result.stdout.strip())


@pytest.mark.functional
@pytest.mark.time_scenarios
@pytest.mark.xdist_group("node-resource-chaos")
class TestTimeScenarios(BaseScenarioTest):
    """Exercise supported pod/node clock actions and invalid-action handling."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/time_scenarios/resource.yaml"
    LABEL_SELECTOR = "app=krkn-time-target"
    SCENARIO_NAME = "time_scenarios"
    SCENARIO_TYPE = "time_scenarios"
    NAMESPACE_KEY_PATH = ["time_scenarios", 0, "namespace"]

    def _run(self, entry, name):
        data = copy.deepcopy(self.load_and_patch_scenario(self.repo_root, self.ns))
        data["time_scenarios"][0].update(entry)
        path = self.write_scenario(self.tmp_path, data, suffix=name)
        config = self.build_config(self.SCENARIO_TYPE, str(path), filename=name + ".config.yaml")
        return self.run_kraken(config, timeout=300)

    def test_pod_time_action_resets_safely(self, kubectl):
        """Verify the source's read-only date action and bounded reset observation."""
        pods = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        assert len(pods.items) == 1, f"Expected one time target pod, found {len(pods.items)}"
        pod_name = pods.items[0].metadata.name
        before = _pod_epoch(kubectl, self.ns, pod_name)
        result = self._run(
            {
                "action": "skew_time",
                "object_type": "pod",
                "label_selector": self.LABEL_SELECTOR,
                "container_name": "",
            },
            "pod",
        )
        assert_kraken_success(result, context=self.ns, tmp_path=self.tmp_path)
        output = f"{result.stdout or ''}\n{result.stderr or ''}"
        assert f"Reset date/time on pod {pod_name}" in output, (
            "Pod action did not report its reset observation; this source path does not "
            "assert a clock mutation because it invokes read-only `date --date`."
        )
        after = _pod_epoch(kubectl, self.ns, pod_name)
        now = int(time.time())
        assert abs(before - now) < 120 and abs(after - now) < 120, (
            f"Pod clock left outside bounded wall-clock observation: before={before}, after={after}, now={now}"
        )
        assert_all_pods_running_and_ready(
            get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR), namespace=self.ns
        )

    @pytest.mark.no_workload
    @pytest.mark.kind_only
    def test_worker_date_action_ntp_safe(self):
        """Exercise only NTP-active action/reset-path handling without changing the host clock."""
        nodes = schedulable_worker_nodes(self.k8s_core)
        if not nodes:
            pytest.skip("No schedulable worker node")
        runtime = container_runtime()
        if not runtime:
            pytest.skip("No KinD container runtime available for a safe NTP probe")
        probe = subprocess.run(
            [runtime, "exec", nodes[0], "timedatectl"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if probe.returncode != 0 or "Network time on: no" in probe.stdout:
            pytest.skip("NTP is inactive or unavailable; skipping unsafe node clock mutation")

        result = self._run(
            {
                "action": "skew_date",
                "object_type": "node",
                "label_selector": f"kubernetes.io/hostname={nodes[0]}",
            },
            "node",
        )
        assert_kraken_success(result, context=nodes[0], tmp_path=self.tmp_path)
        output = f"{result.stdout or ''}\n{result.stderr or ''}"
        assert "ntp active in cluster node" in output.lower()
        assert f"Reset date/time on node {nodes[0]}" in output
        assert wait_node_ready(self.k8s_core, nodes[0], 120)

    def test_invalid_action_fails(self):
        """Reject a time action that the plugin does not support."""
        result = self._run({"action": "not_an_action", "object_type": "pod", "label_selector": self.LABEL_SELECTOR}, "invalid")
        assert_kraken_failure(result, context="invalid time action", tmp_path=self.tmp_path)
