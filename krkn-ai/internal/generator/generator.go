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

package generator

import (
	"fmt"

	"github.com/krkn-chaos/krkn-ai/internal/ai"
	"github.com/krkn-chaos/krkn-ai/internal/validator"
	"github.com/krkn-chaos/krkn-ai/pkg/config"
)

type Generator struct {
	provider  ai.AIProvider
	validator *validator.Validator
}

func NewGenerator(p ai.AIProvider) *Generator {
	return &Generator{
		provider:  p,
		validator: validator.NewValidator(),
	}
}

func (g *Generator) Generate(prompt string) (string, *config.KrknConfig, error) {
	// 1. Call AI Provider
	aiOutput, err := g.provider.GenerateConfig(prompt)
	if err != nil {
		return "", nil, fmt.Errorf("AI generation failed: %v", err)
	}

	// 2. Validate and Convert
	krknCfg, err := g.validator.ValidateAndConvert(aiOutput)
	if err != nil {
		return aiOutput, nil, fmt.Errorf("validation failed: %v", err)
	}

	// 3. Convert to YAML
	yamlStr, err := krknCfg.ToYAML()
	if err != nil {
		return aiOutput, krknCfg, fmt.Errorf("YAML conversion failed: %v", err)
	}

	return yamlStr, krknCfg, nil
}

