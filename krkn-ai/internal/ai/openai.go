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

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
)

type OpenAIProvider struct {
	APIKey string
	Model  string
}

type openAIChatRequest struct {
	Model    string                  `json:"model"`
	Messages []openAIChatMessage     `json:"messages"`
	ResponseFormat *openAIResponseFormat `json:"response_format,omitempty"`
}

type openAIChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type openAIResponseFormat struct {
	Type string `json:"type"`
}

type openAIChatResponse struct {
	Choices []struct {
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	} `json:"choices"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error"`
}

func NewOpenAIProvider() *OpenAIProvider {
	return &OpenAIProvider{
		APIKey: os.Getenv("OPENAI_API_KEY"),
		Model:  "gpt-4-turbo-preview", // Updated model
	}
}

func (p *OpenAIProvider) Name() string {
	return "OpenAI"
}

func (p *OpenAIProvider) GenerateConfig(prompt string) (string, error) {
	if p.APIKey == "" {
		return "", fmt.Errorf("OPENAI_API_KEY environment variable not set")
	}

	systemPrompt := `You are an expert Chaos Engineering assistant for the Kraken (krkn-chaos) tool.
Your task is to convert natural language descriptions of chaos experiments into a JSON object matching the Kraken configuration schema.

The schema requires a root object with "scenarios" which is a list.
Each scenario must have:
- type (e.g., pod_scenario, node_scenario, network_scenario)
- namespace (optional, for pod scenarios)
- actions (list of strings, e.g., kill_pods, hog_cpu, block_network)
- interval (int, seconds between actions)
- duration (int, total duration in seconds)
- checks (optional list of {name, condition, threshold})

IMPORTANT: 
- Return ONLY the JSON object. 
- Do not include markdown formatting or explanations. 
- Ensure all integer fields are numbers, not strings.
- Target only specific namespaces if mentioned.`

	reqBody := openAIChatRequest{
		Model: p.Model,
		Messages: []openAIChatMessage{
			{Role: "system", Content: systemPrompt},
			{Role: "user", Content: prompt},
		},
		ResponseFormat: &openAIResponseFormat{Type: "json_object"},
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return "", err
	}

	req, err := http.NewRequest("POST", "https://api.openai.com/v1/chat/completions", bytes.NewBuffer(jsonData))
	if err != nil {
		return "", err
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+p.APIKey)

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("OpenAI API error (Status %d): %s", resp.StatusCode, string(body))
	}

	var aiResp openAIChatResponse
	if err := json.Unmarshal(body, &aiResp); err != nil {
		return "", err
	}

	if aiResp.Error != nil {
		return "", fmt.Errorf("OpenAI error: %s", aiResp.Error.Message)
	}

	if len(aiResp.Choices) == 0 {
		return "", fmt.Errorf("no output from AI")
	}

	return aiResp.Choices[0].Message.Content, nil
}

