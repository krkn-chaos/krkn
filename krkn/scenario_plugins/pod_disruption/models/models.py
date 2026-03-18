#!/usr/bin/env python
#
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
    def __init__(self, config: dict[str,any] = None):
        if config:
            self.kill = config["kill"] if "kill" in config else 1
            self.timeout = config["timeout"] if "timeout" in config else 120
            self.duration = config["duration"] if "duration" in config else 10
            self.krkn_pod_recovery_time = config["krkn_pod_recovery_time"] if "krkn_pod_recovery_time" in config else 120
            self.label_selector = config["label_selector"] if "label_selector" in config else ""
            self.namespace_pattern = config["namespace_pattern"] if "namespace_pattern" in config else ""
            self.name_pattern = config["name_pattern"] if "name_pattern" in config else ""
            self.node_label_selector = config["node_label_selector"] if "node_label_selector" in config else ""
            self.node_names = config["node_names"] if "node_names" in config else []
            self.exclude_label = config["exclude_label"] if "exclude_label" in config else ""

    namespace_pattern: str
    krkn_pod_recovery_time: int
    timeout: int
    duration: int
    kill: int
    label_selector: str
    name_pattern: str
    node_label_selector: str
    node_names: list
    exclude_label: str