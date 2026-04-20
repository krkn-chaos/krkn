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

import os
import logging
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
from .base import AIProvider

class OpenAIProvider(AIProvider):
    def __init__(self, model: str = "gpt-4-turbo-preview", api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logging.warning("OPENAI_API_KEY not set. OpenAI provider will fail.")
        if OpenAI is None:
            logging.error("openai library is not installed. Please install it with 'pip install openai' to use OpenAIProvider.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def generate_config(self, prompt: str, **kwargs) -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI provider.")
        if self.client is None:
            raise ValueError("openai library is not installed.")

        system_prompt = (
            "You are a chaos engineering expert for the Krkn (Kraken) framework. "
            "Your task is to translate natural language descriptions of chaos scenarios "
            "into valid Krkn YAML configurations. "
            "Always return ONLY the YAML configuration without any markdown blocks or explanation."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate a Krkn config for: {prompt}"}
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                lines = content.splitlines()
                # Remove starting ```yaml or ``` line
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # Remove ending ``` line
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
            return content
        except Exception as e:
            logging.error(f"Error calling OpenAI API: {e}")
            raise

