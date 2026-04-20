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

import yaml
import logging

class ConfigValidator:
    @staticmethod
    def validate(yaml_content: str) -> bool:
        """
        Validates the generated Krkn configuration.
        """
        try:
            config = yaml.safe_load(yaml_content)
            if config is None:
                logging.error("Generated config is empty.")
                return False
                
            # If it's a dictionary, check for 'kraken' key
            if isinstance(config, dict):
                if 'kraken' not in config:
                    logging.error("Generated config dictionary missing 'kraken' key.")
                    return False
                return True
            
            # Legacy support for list of scenarios (if that's what was intended)
            if isinstance(config, list):
                for scenario in config:
                    if not isinstance(scenario, dict):
                        logging.error("Scenario in list is not a dictionary.")
                        return False
                return True
            
            logging.error("Generated config is neither a dictionary nor a list.")
            return False
        except yaml.YAMLError as e:
            logging.error(f"Error parsing generated YAML: {e}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error during validation: {e}")
            return False

