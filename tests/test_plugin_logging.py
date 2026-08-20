#!/usr/bin/env python
"""
Tests for scenario plugin logging with weighted scenarios.

Ensures that the "Scenario plugins for this run" log correctly identifies
scenario types even when using the explicit format where 'scenario_type' is a key.

How to run:
    python -m unittest tests.test_plugin_logging -v
"""

import unittest

from krkn.scenario_config_parser import extract_scenario_types


class TestPluginLogging(unittest.TestCase):
    """Test that plugin logging correctly identifies scenario types."""

    def test_old_format_extracts_correct_type(self):
        """Old format should extract the scenario type correctly."""
        chaos_scenarios = [
            {
                "pod_disruption_scenarios": [
                    "scenarios/openshift/etcd.yml"
                ]
            }
        ]

        types = extract_scenario_types(chaos_scenarios)

        self.assertIn("pod_disruption_scenarios", types)
        self.assertNotIn("scenario_type", types)

    def test_weighted_format_extracts_correct_type(self):
        """Weighted format should extract the scenario type correctly."""
        chaos_scenarios = [
            {
                "pod_disruption_scenarios": {
                    "weight": 3,
                    "files": ["scenarios/openshift/etcd.yml"]
                }
            }
        ]

        types = extract_scenario_types(chaos_scenarios)

        self.assertIn("pod_disruption_scenarios", types)
        self.assertNotIn("scenario_type", types)

    def test_explicit_format_extracts_correct_type(self):
        """Explicit format should extract the scenario type correctly (NOT 'scenario_type')."""
        chaos_scenarios = [
            {
                "scenario_type": "pod_disruption_scenarios",
                "weight": 3,
                "files": ["scenarios/openshift/etcd.yml"]
            }
        ]

        types = extract_scenario_types(chaos_scenarios)

        # Should extract "pod_disruption_scenarios", NOT "scenario_type"
        self.assertIn("pod_disruption_scenarios", types)
        self.assertNotIn("scenario_type", types)

    def test_mixed_formats_extract_all_types(self):
        """Mixed formats should extract all unique scenario types."""
        chaos_scenarios = [
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

        types = extract_scenario_types(chaos_scenarios)

        self.assertEqual(len(types), 3)
        self.assertIn("container_scenarios", types)
        self.assertIn("pod_disruption_scenarios", types)
        self.assertIn("service_disruption_scenarios", types)
        self.assertNotIn("scenario_type", types)

    def test_duplicate_scenario_types_deduplicated(self):
        """Duplicate scenario types should be deduplicated."""
        chaos_scenarios = [
            {
                "pod_disruption_scenarios": {
                    "weight": 3,
                    "files": ["scenarios/openshift/etcd.yml"]
                }
            },
            {
                "scenario_type": "pod_disruption_scenarios",
                "weight": 2,
                "files": ["scenarios/openshift/prom_kill.yml"]
            },
            {
                "pod_disruption_scenarios": [
                    "scenarios/openshift/openshift-apiserver.yml"
                ]
            }
        ]

        types = extract_scenario_types(chaos_scenarios)

        # Should only have one entry for "pod_disruption_scenarios"
        self.assertEqual(len(types), 1)
        self.assertIn("pod_disruption_scenarios", types)

    def test_empty_scenarios_returns_empty_set(self):
        """Empty scenarios list should return empty set."""
        chaos_scenarios = []

        types = extract_scenario_types(chaos_scenarios)

        self.assertEqual(len(types), 0)

    def test_scenario_type_key_not_mistaken_for_plugin(self):
        """The literal string 'scenario_type' should never appear in configured types."""
        # This is a regression test for the bug where explicit format
        # would cause "scenario_type ➡️ no matching plugin found" warnings

        test_cases = [
            # Explicit format
            [{"scenario_type": "pod_disruption_scenarios", "files": ["test.yml"]}],
            # Multiple explicit formats
            [
                {"scenario_type": "pod_disruption_scenarios", "files": ["test1.yml"]},
                {"scenario_type": "hog_scenarios", "files": ["test2.yml"]}
            ],
            # Mixed with explicit format
            [
                {"pod_disruption_scenarios": ["test1.yml"]},
                {"scenario_type": "hog_scenarios", "files": ["test2.yml"]}
            ]
        ]

        for scenarios in test_cases:
            with self.subTest(scenarios=scenarios):
                types = extract_scenario_types(scenarios)
                self.assertNotIn("scenario_type", types,
                    f"'scenario_type' should not be in configured types for: {scenarios}")


class TestPluginLoggingRealWorld(unittest.TestCase):
    """Test plugin logging with real-world config scenarios."""

    def test_production_weighted_config(self):
        """Test with production-like weighted config."""
        chaos_scenarios = [
            {
                "pod_disruption_scenarios": {
                    "weight": 3,
                    "files": [
                        "scenarios/openshift/etcd.yml",
                        "scenarios/openshift/openshift-apiserver.yml",
                        "scenarios/openshift/openshift-kube-apiserver.yml"
                    ]
                }
            },
            {
                "service_disruption_scenarios": {
                    "weight": 2,
                    "files": [
                        "scenarios/openshift/regex_namespace.yaml",
                        "scenarios/openshift/ingress_namespace.yaml"
                    ]
                }
            },
            {
                "node_scenarios": {
                    "weight": 1.5,
                    "files": ["scenarios/openshift/aws_node_scenarios.yml"]
                }
            },
            {
                "hog_scenarios": {
                    "weight": 0.5,
                    "files": [
                        "scenarios/kube/cpu-hog.yml",
                        "scenarios/kube/memory-hog.yml"
                    ]
                }
            },
            {
                "container_scenarios": [
                    "scenarios/openshift/container_etcd.yml"
                ]
            }
        ]

        types = extract_scenario_types(chaos_scenarios)

        expected_types = {
            "pod_disruption_scenarios",
            "service_disruption_scenarios",
            "node_scenarios",
            "hog_scenarios",
            "container_scenarios"
        }

        self.assertEqual(types, expected_types)
        self.assertNotIn("scenario_type", types)

    def test_gradual_migration_config(self):
        """Test with config during gradual migration to weighted format."""
        chaos_scenarios = [
            # New weighted scenarios
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
            # Explicit format
            {
                "scenario_type": "service_disruption_scenarios",
                "weight": 2,
                "files": ["scenarios/openshift/regex_namespace.yaml"]
            }
        ]

        types = extract_scenario_types(chaos_scenarios)

        expected_types = {
            "pod_disruption_scenarios",
            "hog_scenarios",
            "network_chaos_scenarios",
            "service_disruption_scenarios"
        }

        self.assertEqual(types, expected_types)
        self.assertNotIn("scenario_type", types)


if __name__ == '__main__':
    unittest.main()
