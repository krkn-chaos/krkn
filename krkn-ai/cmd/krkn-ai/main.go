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

package main

import (
	"fmt"
	"os"

	"github.com/krkn-chaos/krkn-ai/internal/ai"
	"github.com/krkn-chaos/krkn-ai/internal/generator"
	"github.com/spf13/cobra"
)

var (
	prompt string
	output string
)

func main() {
	var rootCmd = &cobra.Command{
		Use:   "krkn-ai",
		Short: "AI Powered Chaos Configuration Generator for Kraken",
		Long:  `krkn-ai is a CLI tool that uses AI to convert natural language descriptions of chaos experiments into valid Kraken scenario configurations.`,
	}

	var generateCmd = &cobra.Command{
		Use:   "generate",
		Short: "Generate a chaos configuration",
		RunE: func(cmd *cobra.Command, args []string) error {
			if prompt == "" {
				return fmt.Errorf("prompt is required. Use --prompt \"your instruction\"")
			}

			// Initialize default provider (OpenAI)
			provider := ai.NewOpenAIProvider()
			gen := generator.NewGenerator(provider)

			fmt.Printf("Generating configuration using %s provider...\n", provider.Name())
			
			yamlStr, _, err := gen.Generate(prompt)
			if err != nil {
				// If validation fails, we might still want to see what AI returned for debugging
				if yamlStr != "" {
					fmt.Println("\nRaw AI Output (Failed Validation):")
					fmt.Println(yamlStr)
				}
				return err
			}

			fmt.Println("\nSuccessfully generated Kraken Config:")
			fmt.Println("---------------------------------------")
			fmt.Println(yamlStr)
			fmt.Println("---------------------------------------")

			if output != "" {
				err := os.WriteFile(output, []byte(yamlStr), 0644)
				if err != nil {
					return fmt.Errorf("failed to save output file: %v", err)
				}
				fmt.Printf("Configuration saved to: %s\n", output)
			}

			return nil
		},
	}

	generateCmd.Flags().StringVarP(&prompt, "prompt", "p", "", "Natural language description of the chaos experiment")
	generateCmd.Flags().StringVarP(&output, "output", "o", "", "Output filename to save the generated YAML")
	generateCmd.MarkFlagRequired("prompt")

	rootCmd.AddCommand(generateCmd)

	if err := rootCmd.Execute(); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}

