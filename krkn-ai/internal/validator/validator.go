// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package validator

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/krkn-chaos/krkn-ai/pkg/config"
	"gopkg.in/yaml.v3"
)

type Validator struct{}

func NewValidator() *Validator {
	return &Validator{}
}

// ValidateJSON parses AI JSON output and converts it to config.KrknConfig while performing safety checks
func (v *Validator) ValidateAndConvert(jsonStr string) (*config.KrknConfig, error) {
	var cfg config.KrknConfig
	if err := json.Unmarshal([]byte(jsonStr), &cfg); err != nil {
		return nil, fmt.Errorf("invalid JSON from AI: %v", err)
	}

	if len(cfg.Scenarios) == 0 {
		return nil, fmt.Errorf("AI generated zero scenarios")
	}

	for _, s := range cfg.Scenarios {
		if err := v.isSafe(&s); err != nil {
			return nil, err
		}
	}

	return &cfg, nil
}

// ValidateYAML validates an existing YAML string
func (v *Validator) ValidateYAML(yamlStr string) error {
	var cfg config.KrknConfig
	return yaml.Unmarshal([]byte(yamlStr), &cfg)
}

func (v *Validator) isSafe(s *config.Scenario) error {
	// Guardrail 1: Duration check
	if s.Duration > 3600 {
		return fmt.Errorf("safety check failed: duration too long (%d seconds), max allowed is 3600", s.Duration)
	}

	// Guardrail 2: Destructive cluster-wide actions
	if s.Type == "node_scenario" && s.Namespace == "" {
		// If it looks like it might reboot everything
		for _, action := range s.Actions {
			if strings.Contains(action, "reboot") || strings.Contains(action, "stop") {
				return fmt.Errorf("safety check failed: destructive node scenario without scope protection")
			}
		}
	}

	// Guardrail 3: Basic field presence
	if s.Type == "" {
		return fmt.Errorf("scenario type is required")
	}
	if len(s.Actions) == 0 {
		return fmt.Errorf("at least one action is required")
	}

	return nil
}

