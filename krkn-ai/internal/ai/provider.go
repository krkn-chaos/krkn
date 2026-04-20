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

// AIProvider defines the interface for different AI backends
type AIProvider interface {
	// GenerateConfig takes a user prompt and returns a generated Kraken config string (YAML)
	GenerateConfig(prompt string) (string, error)
	// Name returns the name of the provider
	Name() string
}

