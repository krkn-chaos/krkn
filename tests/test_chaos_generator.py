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

import unittest
from unittest.mock import MagicMock, patch
from krkn.chaos_generator.generator import ChaosGenerator
from krkn.chaos_generator.validator import ConfigValidator
from krkn.chaos_generator.openai_provider import OpenAIProvider

class TestChaosGenerator(unittest.TestCase):
    @patch('krkn.chaos_generator.openai_provider.OpenAI')
    @patch('os.getenv')
    def test_generator_success_openai(self, mock_getenv, mock_openai):
        mock_getenv.return_value = "fake_key"
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="kraken:\n  chaos_scenarios:\n    - pod_disruption_scenarios:\n        - scenarios/kube/pod-kill.yml"))]
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        generator = ChaosGenerator(provider_type="openai", api_key="fake_key")
        
        prompt = "Kill one pod"
        config = generator.generate(prompt)
        
        self.assertIn("kraken:", config)
        self.assertIn("pod_disruption_scenarios", config)

    def test_generator_deterministic_pod(self):
        generator = ChaosGenerator(provider_type="deterministic")
        config = generator.generate("I want to kill some pods")
        self.assertIn("pod_disruption_scenarios", config)
        self.assertIn("scenarios/kube/pod.yml", config)

    def test_generator_deterministic_hog(self):
        generator = ChaosGenerator(provider_type="deterministic")
        config = generator.generate("", target_component="hog")
        self.assertIn("hog_scenarios", config)

    def test_generator_deterministic_openshift(self):
        generator = ChaosGenerator(provider_type="deterministic")
        config = generator.generate("pod kill", cluster_type="openshift")
        self.assertIn("scenarios/openshift/etcd.yml", config)

    def test_validator_valid_dict(self):
        valid_yaml = "kraken:\n  chaos_scenarios: []"
        self.assertTrue(ConfigValidator.validate(valid_yaml))

    def test_validator_valid_list(self):
        valid_yaml = "- id: test\n  config: {}"
        self.assertTrue(ConfigValidator.validate(valid_yaml))

    def test_validator_invalid_yaml(self):
        invalid_yaml = "kraken: ["
        self.assertFalse(ConfigValidator.validate(invalid_yaml))

    def test_validator_missing_kraken_key(self):
        no_kraken = "not_kraken:\n  foo: bar"
        self.assertFalse(ConfigValidator.validate(no_kraken))

if __name__ == '__main__':
    unittest.main()

