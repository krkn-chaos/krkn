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
from dataclasses import dataclass


@dataclass
class InputParams:
    def __init__(self, config: dict[str, any] = None):
        if config is not None:
            self.namespace = config.get("namespace", "nvidia-gpu-operator")
            self.node_selector = config.get("node_selector", "")
            self.number_of_nodes = config.get("number_of_nodes", 1)
            self.pod_label_selector = config.get(
                "pod_label_selector", "app=nvidia-device-plugin-daemonset"
            )
            self.recovery_timeout = config.get("recovery_timeout", 120)
            self.expected_recovery = config.get("expected_recovery", True)
            self.verify_allocatable = config.get("verify_allocatable", True)
            self.krkn_pod_recovery_time = config.get(
                "krkn_pod_recovery_time", 120
            )
            self.validate_gpu_health = config.get("validate_gpu_health", True)

    namespace: str
    node_selector: str
    number_of_nodes: int
    pod_label_selector: str
    recovery_timeout: int
    expected_recovery: bool
    verify_allocatable: bool
    krkn_pod_recovery_time: int
    validate_gpu_health: bool
