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

package ai

import "fmt"

type LocalProvider struct{}

func (p *LocalProvider) Name() string {
	return "Local/Stub"
}

func (p *LocalProvider) GenerateConfig(prompt string) (string, error) {
	// For prototype simplicity, this is a stub. 
	// In a real implementation, this would call a local Ollama or Llama.cpp instance.
	return "", fmt.Errorf("local provider is not yet implemented")
}

