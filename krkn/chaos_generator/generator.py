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
from .openai_provider import OpenAIProvider
from .deterministic_provider import DeterministicProvider
from .validator import ConfigValidator

class ChaosGenerator:
    def __init__(self, provider=None, provider_type: str = "openai", **kwargs):
        if provider:
            self.provider = provider
        elif provider_type == "openai":
            self.provider = OpenAIProvider(**kwargs)
        elif provider_type == "deterministic":
            self.provider = DeterministicProvider(**kwargs)
        else:
            raise ValueError(f"Unsupported AI provider: {provider_type}")
        self.validator = ConfigValidator()

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generates and validates a chaos configuration.
        """
        logging.info(f"Generating chaos config for prompt: {prompt}")
        config_yaml = self.provider.generate_config(prompt, **kwargs)
        
        if self.validator.validate(config_yaml):
            logging.info("Successfully generated and validated chaos config.")
            return config_yaml
        else:
            # We logging error in validator
            raise ValueError("Generated configuration failed validation.")

