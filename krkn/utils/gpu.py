# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import time

from krkn_lib.k8s import KrknKubernetes

GPU_RESOURCE_KEY = "nvidia.com/gpu"


def discover_gpu_nodes(kubecli: KrknKubernetes) -> list[dict]:
    gpu_nodes = []
    node_names = kubecli.list_nodes()
    for name in node_names:
        count = get_node_gpu_allocatable(kubecli, name)
        if count > 0:
            gpu_nodes.append({"name": name, "gpu_count": count})
            logging.info(f"discovered GPU node: {name} with {count} GPU(s)")
    if not gpu_nodes:
        logging.warning("no GPU nodes found in the cluster")
    return gpu_nodes


def get_node_gpu_allocatable(kubecli: KrknKubernetes, node_name: str) -> int:
    node = kubecli.cli.read_node(node_name)
    allocatable = node.status.allocatable or {}
    return int(allocatable.get(GPU_RESOURCE_KEY, "0"))


def wait_for_gpu_allocatable(
    kubecli: KrknKubernetes,
    node_name: str,
    expected_count: int,
    timeout: int,
) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        current = get_node_gpu_allocatable(kubecli, node_name)
        if current >= expected_count:
            logging.info(
                f"node {node_name} GPU allocatable restored: {current}"
            )
            return True
        logging.info(
            f"node {node_name} GPU allocatable: {current}, "
            f"expected: {expected_count}, waiting..."
        )
        time.sleep(5)
    logging.error(
        f"timeout waiting for GPU allocatable on node {node_name} "
        f"to reach {expected_count}"
    )
    return False


def validate_gpu_health_on_node(
    kubecli: KrknKubernetes,
    node_name: str,
    namespace: str = "nvidia-gpu-operator",
) -> bool:
    driver_pods = kubecli.select_pods_by_namespace_pattern_and_label(
        namespace_pattern=f"^{namespace}$",
        label_selector="app.kubernetes.io/component=nvidia-driver",
        field_selector=f"spec.nodeName={node_name},status.phase=Running",
    )
    if not driver_pods:
        logging.error(
            f"no running nvidia-driver pod found on node {node_name}"
        )
        return False

    driver_pod_name = driver_pods[0][0]
    driver_pod_ns = driver_pods[0][1]
    try:
        output = kubecli.exec_cmd_in_pod(
            command=["nvidia-smi", "--query-gpu=name,uuid,memory.total",
                     "--format=csv,noheader"],
            pod_name=driver_pod_name,
            namespace=driver_pod_ns,
            container="nvidia-driver-ctr",
        )
        logging.info(f"nvidia-smi on {node_name}: {output.strip()}")
        if "GPU" not in output and "NVIDIA" not in output.upper():
            logging.error(
                f"nvidia-smi output on {node_name} does not indicate "
                f"healthy GPU: {output}"
            )
            return False
        return True
    except Exception as e:
        logging.error(f"nvidia-smi failed on node {node_name}: {e}")
        return False


def find_gpu_operator_pods(
    kubecli: KrknKubernetes,
    namespace: str,
    label_selector: str,
) -> list[tuple[str, str]]:
    return kubecli.select_pods_by_namespace_pattern_and_label(
        namespace_pattern=f"^{namespace}$",
        label_selector=label_selector,
        field_selector="status.phase=Running",
    )


def validate_gpu_operator_present(
    kubecli: KrknKubernetes,
    namespace: str,
) -> bool:
    try:
        pods = kubecli.list_pods(namespace)
        if not pods:
            logging.error(
                f"no pods found in GPU Operator namespace '{namespace}'"
            )
            return False
        logging.info(
            f"GPU Operator namespace '{namespace}' has {len(pods)} pod(s)"
        )
        return True
    except Exception as e:
        logging.error(f"failed to validate GPU Operator: {e}")
        return False
