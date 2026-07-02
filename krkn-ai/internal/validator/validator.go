// Copyright 2026 Red Hat, Inc.
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

// ValidateAndConvert parses AI JSON output and converts it to config.KrknConfig while performing safety checks
func (v *Validator) ValidateAndConvert(jsonStr string) (*config.KrknConfig, error) {
	var cfg config.KrknConfig
	if err := json.Unmarshal([]byte(jsonStr), &cfg); err != nil {
		return nil, fmt.Errorf("invalid JSON from AI: %v", err)
	}

	// Basic Krkn structure validation
	if len(cfg.Kraken.ChaosScenarios) == 0 {
		return nil, fmt.Errorf("AI generated zero scenarios in kraken.chaos_scenarios")
	}

	// Safety check on each scenario
	// Note: In the official schema, each scenario is often another struct. 
	// To keep validator simple without knowing every scenario type, 
	// we perform best-effort safety checks if fields match.
	for _, sRaw := range cfg.Kraken.ChaosScenarios {
		// Attempt to marshal back to JSON and then to a generic map for safety checking
		sBytes, _ := json.Marshal(sRaw)
		var sMap map[string]interface{}
		json.Unmarshal(sBytes, &sMap)

		if err := v.isMapSafe(sMap); err != nil {
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

func (v *Validator) isMapSafe(s map[string]interface{}) error {
	// Look for a nested list of scenarios (Standard Krkn format)
	// e.g. { "pod_disruption_scenarios": [ ... ] }
	for _, val := range s {
		if scenarios, ok := val.([]interface{}); ok {
			for _, scenario := range scenarios {
				if sMap, ok := scenario.(map[string]interface{}); ok {
					if err := v.isScenarioSafe(sMap); err != nil {
						return err
					}
				}
			}
		}
	}
	return nil
}

func (v *Validator) isScenarioSafe(s map[string]interface{}) error {
	// Guardrail 1: Duration check
	duration, ok := s["duration"].(float64) // JSON unmarshals to float64
	if ok {
		if duration <= 0 {
			return fmt.Errorf("safety check failed: duration must be positive")
		}
		if duration > 3600 {
			return fmt.Errorf("safety check failed: duration too long (%.0f seconds), max allowed is 3600", duration)
		}
	}

	// Guardrail 2: Interval check
	interval, ok := s["interval"].(float64)
	if ok {
		if interval <= 0 {
			return fmt.Errorf("safety check failed: interval must be positive")
		}
		if duration > 0 && interval > duration {
			return fmt.Errorf("safety check failed: interval cannot be greater than duration")
		}
	}

	// Guardrail 3: Destructive cluster-wide actions
	scenType, _ := s["type"].(string)
	namespace, _ := s["namespace"].(string)
	
	if (scenType == "node_scenario" || scenType == "node-scenario") && namespace == "" {
		actions, ok := s["actions"].([]interface{})
		if ok {
			for _, actionRaw := range actions {
				action, _ := actionRaw.(string)
				action = strings.ToLower(action)
				if strings.Contains(action, "reboot") || strings.Contains(action, "stop") || strings.Contains(action, "terminate") {
					return fmt.Errorf("safety check failed: destructive node scenario without scope protection")
				}
			}
		}
	}

	return nil
}
