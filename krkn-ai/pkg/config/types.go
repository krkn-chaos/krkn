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

package config

import "gopkg.in/yaml.v3"

// KrknConfig represents the root of the Kraken configuration
type KrknConfig struct {
	Kraken                KrakenSection                `yaml:"kraken"`
	Tunings               TuningsSection               `yaml:"tunings"`
	PerformanceMonitoring PerformanceMonitoringSection `yaml:"performance_monitoring"`
	Elastic               ElasticSection               `yaml:"elastic"`
	Telemetry             TelemetrySection             `yaml:"telemetry"`
}

type KrakenSection struct {
	ChaosScenarios []interface{} `yaml:"chaos_scenarios"`
	KubeconfigPath string        `yaml:"kubeconfig_path"`
}

type TuningsSection struct {
	WaitDuration int  `yaml:"wait_duration"`
	Iterations   int  `yaml:"iterations"`
	DaemonMode   bool `yaml:"daemon_mode"`
}

type PerformanceMonitoringSection struct {
	EnableAlerts  bool `yaml:"enable_alerts"`
	EnableMetrics bool `yaml:"enable_metrics"`
}

type ElasticSection struct {
	EnableElastic bool `yaml:"enable_elastic"`
}

type TelemetrySection struct {
	Enabled bool `yaml:"enabled"`
}

// Scenario represents a single chaos experiment scenario (legacy/simplified)
type Scenario struct {
	Type      string   `yaml:"type"`
	Namespace string   `yaml:"namespace,omitempty"`
	Actions   []string `yaml:"actions"`
	Interval  int      `yaml:"interval"`
	Duration  int      `yaml:"duration"`
	Checks    []Check  `yaml:"checks,omitempty"`
}

// Check represents SLO validation checks
type Check struct {
	Name      string `yaml:"name"`
	Condition string `yaml:"condition"`
	Threshold string `yaml:"threshold"`
}

// ToYAML converts the config to a YAML string
func (c *KrknConfig) ToYAML() (string, error) {
	data, err := yaml.Marshal(c)
	if err != nil {
		return "", err
	}
	return string(data), nil
}
