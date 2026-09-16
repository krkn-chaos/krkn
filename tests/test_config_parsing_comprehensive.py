#!/usr/bin/env python
"""
Comprehensive tests for chaos scenario config parsing with weighted scenarios.

Tests all supported config formats:
1. Old format: {scenario_type: [files]}
2. Weighted format: {scenario_type: {weight: N, files: []}}
3. Explicit format: {scenario_type: str, weight: N, files: []}

How to run:
    python -m unittest tests.test_config_parsing_comprehensive -v
    python -m unittest tests.test_config_parsing_comprehensive.TestOldFormatCompatibility -v
    python -m unittest tests.test_config_parsing_comprehensive.TestWeightedFormat -v
    python -m unittest tests.test_config_parsing_comprehensive.TestEdgeCases -v
"""

import unittest
import tempfile
import yaml
import os

from krkn.scenario_config_parser import parse_scenario_config


class TestOldFormatCompatibility(unittest.TestCase):
    """Test that old config format still works (backward compatibility)."""

    def test_old_format_single_file(self):
        """Old format with a single file."""
        scenario = {
            "pod_disruption_scenarios": [
                "scenarios/openshift/etcd.yml"
            ]
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(scenario_type, "pod_disruption_scenarios")
        self.assertEqual(files, ["scenarios/openshift/etcd.yml"])
        self.assertEqual(weight, 1)

    def test_old_format_multiple_files(self):
        """Old format with multiple files."""
        scenario = {
            "pod_disruption_scenarios": [
                "scenarios/openshift/etcd.yml",
                "scenarios/openshift/prom_kill.yml",
                "scenarios/openshift/openshift-apiserver.yml"
            ]
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(scenario_type, "pod_disruption_scenarios")
        self.assertEqual(len(files), 3)
        self.assertEqual(weight, 1)
        self.assertIn("scenarios/openshift/etcd.yml", files)

    def test_old_format_empty_list(self):
        """Old format with empty file list."""
        scenario = {
            "hog_scenarios": []
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(scenario_type, "hog_scenarios")
        self.assertEqual(files, [])
        self.assertEqual(weight, 1)

    def test_old_format_various_scenario_types(self):
        """Test old format works for different scenario types."""
        test_cases = [
            "pod_disruption_scenarios",
            "node_scenarios",
            "hog_scenarios",
            "service_disruption_scenarios",
            "network_chaos_scenarios",
            "container_scenarios"
        ]

        for scenario_type_name in test_cases:
            scenario = {
                scenario_type_name: ["scenarios/test.yml"]
            }
            scenario_type, files, weight = parse_scenario_config(scenario)

            self.assertEqual(scenario_type, scenario_type_name)
            self.assertEqual(weight, 1)


class TestWeightedFormat(unittest.TestCase):
    """Test the new weighted scenario format."""

    def test_weighted_format_basic(self):
        """Basic weighted format with weight and files."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": 3,
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(scenario_type, "pod_disruption_scenarios")
        self.assertEqual(files, ["scenarios/openshift/etcd.yml"])
        self.assertEqual(weight, 3)

    def test_weighted_format_float_weight(self):
        """Weighted format with float weight."""
        scenario = {
            "node_scenarios": {
                "weight": 1.5,
                "files": ["scenarios/openshift/aws_node_scenarios.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 1.5)

    def test_weighted_format_fractional_weight(self):
        """Weighted format with fractional weight less than 1."""
        scenario = {
            "hog_scenarios": {
                "weight": 0.5,
                "files": ["scenarios/kube/cpu-hog.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 0.5)

    def test_weighted_format_multiple_files(self):
        """Weighted format with multiple files."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": 3,
                "files": [
                    "scenarios/openshift/etcd.yml",
                    "scenarios/openshift/openshift-apiserver.yml",
                    "scenarios/openshift/openshift-kube-apiserver.yml"
                ]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 3)
        self.assertEqual(len(files), 3)

    def test_weighted_format_missing_weight_defaults_to_1(self):
        """Weighted format without explicit weight defaults to 1."""
        scenario = {
            "hog_scenarios": {
                "files": ["scenarios/kube/cpu-hog.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 1)

    def test_weighted_format_weight_zero(self):
        """Weighted format with weight=0 defaults to 1 (validated)."""
        scenario = {
            "test_scenarios": {
                "weight": 0,
                "files": ["scenarios/test.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        # Weight validation: 0 is invalid, defaults to 1
        self.assertEqual(weight, 1.0)

    def test_weighted_format_large_weight(self):
        """Weighted format with large weight."""
        scenario = {
            "critical_scenarios": {
                "weight": 10,
                "files": ["scenarios/critical.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 10)


class TestExplicitFormat(unittest.TestCase):
    """Test the explicit format with scenario_type as a field."""

    def test_explicit_format_with_weight(self):
        """Explicit format: scenario_type, weight, files."""
        scenario = {
            "scenario_type": "pod_disruption_scenarios",
            "weight": 3,
            "files": ["scenarios/openshift/etcd.yml"]
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(scenario_type, "pod_disruption_scenarios")
        self.assertEqual(weight, 3)
        self.assertEqual(files, ["scenarios/openshift/etcd.yml"])

    def test_explicit_format_without_weight(self):
        """Explicit format without weight defaults to 1."""
        scenario = {
            "scenario_type": "hog_scenarios",
            "files": ["scenarios/kube/cpu-hog.yml"]
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 1)

    def test_explicit_format_multiple_files(self):
        """Explicit format with multiple files."""
        scenario = {
            "scenario_type": "service_disruption_scenarios",
            "weight": 2,
            "files": [
                "scenarios/openshift/regex_namespace.yaml",
                "scenarios/openshift/ingress_namespace.yaml"
            ]
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(weight, 2)
        self.assertEqual(len(files), 2)


class TestMixedFormats(unittest.TestCase):
    """Test mixing different config formats in the same configuration."""

    def test_all_three_formats_together(self):
        """Mix old format, weighted format, and explicit format."""
        scenarios = [
            # Old format
            {
                "container_scenarios": [
                    "scenarios/openshift/container_etcd.yml"
                ]
            },
            # Weighted format
            {
                "pod_disruption_scenarios": {
                    "weight": 3,
                    "files": ["scenarios/openshift/etcd.yml"]
                }
            },
            # Explicit format
            {
                "scenario_type": "service_disruption_scenarios",
                "weight": 2,
                "files": ["scenarios/openshift/regex_namespace.yaml"]
            }
        ]

        results = [parse_scenario_config(s) for s in scenarios]

        # Verify each format parsed correctly
        self.assertEqual(results[0], ("container_scenarios", ["scenarios/openshift/container_etcd.yml"], 1))
        self.assertEqual(results[1], ("pod_disruption_scenarios", ["scenarios/openshift/etcd.yml"], 3))
        self.assertEqual(results[2], ("service_disruption_scenarios", ["scenarios/openshift/regex_namespace.yaml"], 2))

    def test_weighted_and_unweighted_scenarios(self):
        """Mix weighted and unweighted scenarios."""
        scenarios = [
            {
                "pod_disruption_scenarios": {
                    "weight": 3,
                    "files": ["scenarios/openshift/etcd.yml"]
                }
            },
            {
                "hog_scenarios": {
                    "files": ["scenarios/kube/cpu-hog.yml"]  # No weight
                }
            },
            {
                "container_scenarios": ["scenarios/openshift/container_etcd.yml"]  # Old format
            }
        ]

        results = [parse_scenario_config(s) for s in scenarios]

        self.assertEqual(results[0][2], 3)   # Weight=3
        self.assertEqual(results[1][2], 1)   # Default weight=1
        self.assertEqual(results[2][2], 1)   # Default weight=1


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and potential error conditions."""

    def test_empty_files_in_weighted_format(self):
        """Weighted format with empty files list."""
        scenario = {
            "test_scenarios": {
                "weight": 2,
                "files": []
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(files, [])
        self.assertEqual(weight, 2)

    def test_missing_files_key_in_weighted_format(self):
        """Weighted format missing 'files' key (should return empty list)."""
        scenario = {
            "test_scenarios": {
                "weight": 2
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        self.assertEqual(files, [])
        self.assertEqual(weight, 2)

    def test_weight_as_string_integer(self):
        """Weight provided as string that looks like integer is converted to float."""
        # Note: YAML parsing would convert "3" to int, but test the logic
        scenario = {
            "test_scenarios": {
                "weight": "3",  # String, not int
                "files": ["test.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        # Weight validation converts numeric strings to float
        self.assertEqual(weight, 3.0)

    def test_negative_weight(self):
        """Negative weight defaults to 1 (validated)."""
        scenario = {
            "test_scenarios": {
                "weight": -1,
                "files": ["test.yml"]
            }
        }
        scenario_type, files, weight = parse_scenario_config(scenario)

        # Weight validation: negative is invalid, defaults to 1
        self.assertEqual(weight, 1.0)


class TestYAMLIntegration(unittest.TestCase):
    """Test parsing actual YAML config files."""

    def test_parse_old_format_yaml(self):
        """Parse old format from actual YAML."""
        yaml_content = """
kraken:
  chaos_scenarios:
    - pod_disruption_scenarios:
        - scenarios/openshift/etcd.yml
        - scenarios/openshift/prom_kill.yml
    - hog_scenarios:
        - scenarios/kube/cpu-hog.yml
"""
        config = yaml.safe_load(yaml_content)
        scenarios = config['kraken']['chaos_scenarios']

        results = [parse_scenario_config(s) for s in scenarios]

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "pod_disruption_scenarios")
        self.assertEqual(len(results[0][1]), 2)
        self.assertEqual(results[0][2], 1)

    def test_parse_weighted_format_yaml(self):
        """Parse weighted format from actual YAML."""
        yaml_content = """
kraken:
  chaos_scenarios:
    - pod_disruption_scenarios:
        weight: 3
        files:
          - scenarios/openshift/etcd.yml
    - service_disruption_scenarios:
        weight: 2
        files:
          - scenarios/openshift/regex_namespace.yaml
    - hog_scenarios:
        weight: 0.5
        files:
          - scenarios/kube/cpu-hog.yml
"""
        config = yaml.safe_load(yaml_content)
        scenarios = config['kraken']['chaos_scenarios']

        results = [parse_scenario_config(s) for s in scenarios]

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0][2], 3)     # Weight=3
        self.assertEqual(results[1][2], 2)     # Weight=2
        self.assertEqual(results[2][2], 0.5)   # Weight=0.5

    def test_parse_mixed_format_yaml(self):
        """Parse mixed formats from actual YAML."""
        yaml_content = """
kraken:
  chaos_scenarios:
    - pod_disruption_scenarios:
        weight: 3
        files:
          - scenarios/openshift/etcd.yml
    - hog_scenarios:
        - scenarios/kube/cpu-hog.yml
    - scenario_type: service_disruption_scenarios
      weight: 2
      files:
        - scenarios/openshift/regex_namespace.yaml
"""
        config = yaml.safe_load(yaml_content)
        scenarios = config['kraken']['chaos_scenarios']

        results = [parse_scenario_config(s) for s in scenarios]

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0][2], 3)   # Weighted format
        self.assertEqual(results[1][2], 1)   # Old format
        self.assertEqual(results[2][2], 2)   # Explicit format

    def test_parse_from_temp_file(self):
        """Parse config from a temporary YAML file."""
        yaml_content = """
kraken:
  chaos_scenarios:
    - pod_disruption_scenarios:
        weight: 3
        files:
          - scenarios/openshift/etcd.yml
    - container_scenarios:
        - scenarios/openshift/container_etcd.yml
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_file = f.name

        try:
            with open(temp_file, 'r') as f:
                config = yaml.safe_load(f)

            scenarios = config['kraken']['chaos_scenarios']
            results = [parse_scenario_config(s) for s in scenarios]

            self.assertEqual(len(results), 2)
            self.assertEqual(results[0][2], 3)  # Weighted
            self.assertEqual(results[1][2], 1)  # Old format
        finally:
            os.unlink(temp_file)


class TestRealWorldScenarios(unittest.TestCase):
    """Test realistic scenario configurations."""

    def test_production_critical_weighting(self):
        """Test production-like config with critical scenarios weighted heavily."""
        scenarios = [
            {
                "pod_disruption_scenarios": {
                    "weight": 5,  # Very critical
                    "files": [
                        "scenarios/openshift/etcd.yml",
                        "scenarios/openshift/openshift-apiserver.yml",
                        "scenarios/openshift/openshift-kube-apiserver.yml"
                    ]
                }
            },
            {
                "service_disruption_scenarios": {
                    "weight": 3,  # Important
                    "files": [
                        "scenarios/openshift/regex_namespace.yaml",
                        "scenarios/openshift/ingress_namespace.yaml"
                    ]
                }
            },
            {
                "hog_scenarios": {
                    "weight": 0.25,  # Less important
                    "files": [
                        "scenarios/kube/cpu-hog.yml",
                        "scenarios/kube/memory-hog.yml"
                    ]
                }
            }
        ]

        results = [parse_scenario_config(s) for s in scenarios]

        # Verify weights
        self.assertEqual(results[0][2], 5)
        self.assertEqual(results[1][2], 3)
        self.assertEqual(results[2][2], 0.25)

        # Verify all files parsed
        self.assertEqual(len(results[0][1]), 3)
        self.assertEqual(len(results[1][1]), 2)
        self.assertEqual(len(results[2][1]), 2)

    def test_gradual_adoption_config(self):
        """Test config during gradual adoption (some weighted, some not)."""
        scenarios = [
            # New weighted critical scenarios
            {
                "pod_disruption_scenarios": {
                    "weight": 3,
                    "files": ["scenarios/openshift/etcd.yml"]
                }
            },
            # Old format (not yet migrated)
            {
                "hog_scenarios": ["scenarios/kube/cpu-hog.yml"]
            },
            {
                "network_chaos_scenarios": ["scenarios/openshift/network_chaos.yaml"]
            },
            # Another weighted scenario
            {
                "service_disruption_scenarios": {
                    "weight": 2,
                    "files": ["scenarios/openshift/regex_namespace.yaml"]
                }
            }
        ]

        results = [parse_scenario_config(s) for s in scenarios]

        # Weighted scenarios have custom weights
        self.assertEqual(results[0][2], 3)
        self.assertEqual(results[3][2], 2)

        # Old format scenarios default to weight=1
        self.assertEqual(results[1][2], 1)
        self.assertEqual(results[2][2], 1)


if __name__ == '__main__':
    unittest.main()
