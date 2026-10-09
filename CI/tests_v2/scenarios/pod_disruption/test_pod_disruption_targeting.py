"""Node-scoped pod disruption targeting without cluster-system workloads."""
import time

import pytest
from kubernetes import client

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_success,
    assert_scenario_executed,
    get_pods_list,
    pod_uids,
    schedulable_worker_nodes,
)


@pytest.mark.functional
@pytest.mark.pod_disruption
class TestPodDisruptionTargeting(BaseScenarioTest):
    """Check node-scoped victim selection with stable replacement placement."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_disruption/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pod-disruption-target"
    SCENARIO_NAME = "pod_disruption"
    SCENARIO_TYPE = "pod_disruption_scenarios"
    NAMESPACE_KEY_PATH = [0, "config", "namespace_pattern"]
    NAMESPACE_IS_REGEX = True

    def test_worker_selector_limits_victim_to_selected_node(self):
        """Disrupt only the selected-node pod, leaving an off-node decoy untouched."""
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        if not before.items or not before.items[0].spec.node_name:
            pytest.skip("Target workload is not scheduled on a worker node")
        target_pod = before.items[0]
        target_node = target_pod.spec.node_name
        workers = schedulable_worker_nodes(self.k8s_core)
        decoy_nodes = [node for node in workers if node != target_node]
        if target_node not in workers or not decoy_nodes:
            pytest.skip("At least two schedulable workers are required for off-node targeting")

        # This test covers victim selection, not cross-node recovery. Pin the
        # Deployment replacement to the selected worker so the baseline plugin
        # can observe recovery using its node-scoped selector.
        self.k8s_apps.patch_namespaced_deployment(
            name="krkn-pod-disruption-target",
            namespace=self.ns,
            body={
                "spec": {
                    "template": {
                        "spec": {
                            "nodeSelector": {"kubernetes.io/hostname": target_node}
                        }
                    }
                }
            },
        )
        target_pod = None
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            targets = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
            if len(targets.items) == 1:
                candidate = targets.items[0]
                statuses = (
                    candidate.status.container_statuses
                    if candidate.status
                    else None
                )
                if (
                    candidate.spec.node_name == target_node
                    and candidate.status
                    and candidate.status.phase == "Running"
                    and statuses
                    and all(status.ready for status in statuses)
                ):
                    target_pod = candidate
                    break
            time.sleep(1)
        if target_pod is None:
            pytest.fail(
                f"Deployment replacement did not become ready on selected worker {target_node}"
            )
        target_uid = target_pod.metadata.uid

        decoy_name = "krkn-pod-disruption-off-node"
        decoy_node = decoy_nodes[0]
        decoy = client.V1Pod(
            metadata=client.V1ObjectMeta(name=decoy_name, labels={"app": "krkn-pod-disruption-target"}),
            spec=client.V1PodSpec(
                node_name=decoy_node,
                restart_policy="Never",
                containers=[
                    client.V1Container(
                        name="app",
                        image="nginxinc/nginx-unprivileged:1.29.1-alpine",
                        ports=[client.V1ContainerPort(container_port=8080)],
                    )
                ],
            ),
        )
        self.k8s_core.create_namespaced_pod(namespace=self.ns, body=decoy)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                current = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
                decoy_pod = next(
                    (pod for pod in current.items if pod.metadata.name == decoy_name),
                    None,
                )
                if (
                    decoy_pod
                    and decoy_pod.status
                    and decoy_pod.status.phase == "Running"
                    and decoy_pod.spec.node_name == decoy_node
                    and decoy_pod.status.container_statuses
                    and all(status.ready for status in decoy_pod.status.container_statuses)
                ):
                    break
                time.sleep(1)
            else:
                pytest.fail(f"Off-node decoy {decoy_name} did not become ready on {decoy_node}")

            before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
            target_pods = [pod for pod in before.items if pod.metadata.name != decoy_name]
            assert len(target_pods) == 1, f"Expected one controller target, found {target_pods}"
            assert target_pods[0].metadata.uid == target_uid
            decoy_uid = decoy_pod.metadata.uid

            scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
            config = scenario[0]["config"]
            config.update({"node_label_selector": f"kubernetes.io/hostname={target_node}", "kill": 1})
            path = self.write_scenario(self.tmp_path, scenario, suffix="-node-target")
            result = self.run_kraken(
                self.build_config(self.SCENARIO_TYPE, str(path), filename="node-target.yaml")
            )
            assert_kraken_success(result, context=f"node={target_node}", tmp_path=self.tmp_path)
            assert_scenario_executed(
                result, self.SCENARIO_NAME, context=self.ns, tmp_path=self.tmp_path
            )

            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                after = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
                target_after = [pod for pod in after.items if pod.metadata.name != decoy_name]
                decoy_after = [pod for pod in after.items if pod.metadata.name == decoy_name]
                if (
                    len(target_after) == 1
                    and target_after[0].metadata.uid != target_uid
                    and target_after[0].spec.node_name == target_node
                    and decoy_after
                    and decoy_after[0].metadata.uid == decoy_uid
                    and decoy_after[0].spec.node_name == decoy_node
                ):
                    break
                time.sleep(1)
            else:
                pytest.fail("Selected-node pod was not replaced while off-node decoy remained unchanged")

            assert set(pod_uids(before)) != set(pod_uids(after)), "No target pod was disrupted"
            assert [pod.metadata.uid for pod in after.items if pod.metadata.name == decoy_name] == [decoy_uid]
            assert_all_pods_running_and_ready(after, namespace=self.ns)
        finally:
            try:
                self.k8s_core.delete_namespaced_pod(
                    name=decoy_name, namespace=self.ns, grace_period_seconds=0
                )
            except Exception:
                pass
