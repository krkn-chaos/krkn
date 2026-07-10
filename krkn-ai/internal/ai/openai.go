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

package ai

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

type OpenAIProvider struct {
	APIKey string
	Model  string
}

type openAIChatRequest struct {
	Model          string                `json:"model"`
	Messages       []openAIChatMessage   `json:"messages"`
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
		Model:  "gpt-4-turbo-preview",
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

The schema requires a root object with these sections:
- kraken: 
    chaos_scenarios: (list of scenario objects)
    kubeconfig_path: (string, default "~/.kube/config")
- tunings:
    wait_duration: (int)
    iterations: (int)
- performance_monitoring:
    enable_alerts: (bool)
    enable_metrics: (bool)

Each scenario in chaos_scenarios MUST be a dictionary with a single key identifying the scenario type (e.g. "pod_disruption_scenarios", "node_scenarios") and its value being a list of scenario data.

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

	// Added 30s timeout
	client := &http.Client{
		Timeout: 30 * time.Second,
	}
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
