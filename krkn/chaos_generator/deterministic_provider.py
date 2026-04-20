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
            return self._pod_kill_config(cluster_type)
        elif target_component == "node":
            return self._node_scenario_config(cluster_type)
        elif target_component == "hog":
            return self._hog_scenario_config(cluster_type)
        elif target_component == "network":
            return self._network_scenario_config(cluster_type)
        
        # Default fallback
        return self._pod_kill_config(cluster_type)

    def _pod_kill_config(self, cluster_type: str) -> str:
        scenario_path = "scenarios/kube/pod.yml"
        if cluster_type == "openshift":
            scenario_path = "scenarios/openshift/etcd.yml"
            
        return f"""kraken:
    chaos_scenarios:
        - pod_disruption_scenarios:
            - {scenario_path}
"""

    def _node_scenario_config(self, cluster_type: str) -> str:
        scenario_path = "scenarios/kube/node-network-chaos.yml"
        if cluster_type == "openshift":
            scenario_path = "scenarios/openshift/aws_node_scenarios.yml"
            
        return f"""kraken:
    chaos_scenarios:
        - node_scenarios:
            - {scenario_path}
"""

    def _hog_scenario_config(self, cluster_type: str) -> str:
        return f"""kraken:
    chaos_scenarios:
        - hog_scenarios:
            - scenarios/kube/cpu-hog.yml
            - scenarios/kube/memory-hog.yml
"""

    def _network_scenario_config(self, cluster_type: str) -> str:
        scenario_path = "scenarios/kube/pod-network-chaos.yml"
        if cluster_type == "openshift":
            scenario_path = "scenarios/openshift/network_chaos.yaml"
            
        return f"""kraken:
    chaos_scenarios:
        - network_chaos_scenarios:
            - {scenario_path}
"""

