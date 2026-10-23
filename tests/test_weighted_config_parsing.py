#!/usr/bin/env python
"""
Basic tests for weighted scenario config parsing.

NOTE: For comprehensive tests covering all edge cases, formats, and YAML integration,
see tests.test_config_parsing_comprehensive

How to run:
    python -m unittest tests.test_weighted_config_parsing -v
    python -m unittest tests.test_config_parsing_comprehensive -v  # Comprehensive suite
"""

import unittest
from krkn.scenario_config_parser import parse_scenario_config


class TestWeightedConfigParsing(unittest.TestCase):
    """Test weighted scenario config format parsing."""

    def test_option1_format_with_weight(self):
        """Test parsing Option 1 format: {scenario_type: {weight: N, files: []}}."""
        scenario = {
            "pod_disruption_scenarios": {
                "weight": 2.5,
                "files": ["scenarios/openshift/etcd.yml"]
            }
        }

        scenario_type, scenarios_list, scenario_weight = parse_scenario_config(scenario)

        self.assertEqual(scenario_type, "pod_disruption_scenarios")
        self.assertEqual(scenarios_list, ["scenarios/openshift/etcd.yml"])
        self.assertEqual(scenario_weight, 2.5)

    def test_option1_format_without_weight_defaults_to_1(self):
        """Test Option 1 format without weight defaults to 1."""
        scenario = {
            "hog_scenarios": {
                "files": ["scenarios/kube/cpu-hog.yml"]
            }
        }

        scenario_type, scenarios_list, scenario_weight = parse_scenario_config(scenario)

        self.assertEqual(scenario_weight, 1.0)

    def test_old_format_backward_compatible(self):
        """Test old format still works with default weight=1."""
        scenario = {
            "pod_disruption_scenarios": [
                "scenarios/openshift/etcd.yml",
                "scenarios/openshift/prom_kill.yml"
            ]
        }

        scenario_type, scenarios_list, scenario_weight = parse_scenario_config(scenario)

        self.assertEqual(scenario_type, "pod_disruption_scenarios")
        self.assertEqual(len(scenarios_list), 2)
        self.assertEqual(scenario_weight, 1.0)

    def test_mixed_formats(self):
        """Test that Option 1 format and old format can coexist."""
        scenarios = [
            {
                "pod_disruption_scenarios": {
                    "weight": 3,
                    "files": ["scenarios/openshift/etcd.yml"]
                }
            },
            {
                "hog_scenarios": ["scenarios/kube/cpu-hog.yml"]
            }
        ]

        results = []
        for scenario in scenarios:
            scenario_type, scenarios_list, scenario_weight = parse_scenario_config(scenario)
            results.append({
                "type": scenario_type,
                "weight": scenario_weight,
                "files": scenarios_list
            })

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["weight"], 3)
        self.assertEqual(results[1]["weight"], 1)


if __name__ == '__main__':
    unittest.main()
