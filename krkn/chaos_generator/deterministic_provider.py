# Copyright 2026 Red Hat, Inc.
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
from .base import AIProvider

class DeterministicProvider(AIProvider):
    def __init__(self, **kwargs):
        pass

    def generate_config(self, prompt: str, **kwargs) -> str:
        """
        Generates a chaos configuration based on keywords in the prompt or structured inputs.
        """
        cluster_type = kwargs.get("cluster_type", "kubernetes").lower()
        target_component = kwargs.get("target_component", "").lower()
        slo = kwargs.get("slo", "")
        
        prompt = prompt.lower() if prompt else ""
        
        # Determine target component from prompt if not explicitly provided
        if not target_component:
            if "pod" in prompt:
                target_component = "pod"
            elif "node" in prompt:
                target_component = "node"
            elif "cpu" in prompt or "memory" in prompt or "hog" in prompt:
                target_component = "hog"
            elif "network" in prompt:
                target_component = "network"

        if target_component == "pod":
            scenarios = self._pod_kill_scenarios(cluster_type)
        elif target_component == "node":
            scenarios = self._node_scenarios(cluster_type)
        elif target_component == "hog":
            scenarios = self._hog_scenarios(cluster_type)
        elif target_component == "network":
            scenarios = self._network_scenarios(cluster_type)
        else:
            # Default fallback
            scenarios = self._pod_kill_scenarios(cluster_type)
        
        return self._assemble_full_config(scenarios, slo)

    def _assemble_full_config(self, scenarios: list, slo: str) -> str:
        # If SLO is provided, we can add a comment or adjust tunings
        slo_comment = f"# Targeted SLO: {slo}" if slo else ""
        
        full_config = f"""# Copyright 2026 Red Hat, Inc.
# Licensed under the Apache License, Version 2.0 (the "License");
{slo_comment}
kraken:
    chaos_scenarios:
{self._indent_list(scenarios, 8)}
    kubeconfig_path: ~/.kube/config
    publish_kraken_status: false
    port: 8081

tunings:
    wait_duration: 60
    iterations: 1
    daemon_mode: false

performance_monitoring:
    enable_alerts: false
    enable_metrics: false

elastic:
    enable_elastic: false

telemetry:
    enabled: false
"""
        return full_config

    def _indent_list(self, items: list, indent: int) -> str:
        spaces = " " * indent
        return "\n".join([f"{spaces}- {item}" for item in items])

    def _pod_kill_scenarios(self, cluster_type: str) -> list:
        scenario_path = "scenarios/kube/pod.yml"
        if cluster_type == "openshift":
            scenario_path = "scenarios/openshift/etcd.yml"
        return [f"pod_disruption_scenarios:\n                - {scenario_path}"]

    def _node_scenarios(self, cluster_type: str) -> list:
        scenario_path = "scenarios/kube/node-network-chaos.yml"
        if cluster_type == "openshift":
            scenario_path = "scenarios/openshift/aws_node_scenarios.yml"
        return [f"node_scenarios:\n                - {scenario_path}"]

    def _hog_scenarios(self, cluster_type: str) -> list:
        return [
            "hog_scenarios:\n                - scenarios/kube/cpu-hog.yml",
            "hog_scenarios:\n                - scenarios/kube/memory-hog.yml"
        ]

    def _network_scenarios(self, cluster_type: str) -> list:
        scenario_path = "scenarios/kube/pod-network-chaos.yml"
        if cluster_type == "openshift":
            scenario_path = "scenarios/openshift/network_chaos.yaml"
        return [f"network_chaos_scenarios:\n                - {scenario_path}"]
