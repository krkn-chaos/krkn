#!/usr/bin/env python
#
# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Test to verify that failed scenarios are accumulated across all scenario types
and not silently overwritten when iterating through multiple scenario types.

Regression test for: https://github.com/krkn-chaos/krkn/issues/1777

Usage:
    python -m coverage run -a -m unittest tests/test_failed_scenarios_accumulation.py -v
"""

import unittest
from unittest.mock import MagicMock
from krkn_lib.models.telemetry import ScenarioTelemetry


class TestFailedScenariosAccumulation(unittest.TestCase):

    def _simulate_scenario_loop(self, chaos_scenarios):
        """
        Simulates the core scenario loop from run_kraken.py (lines 345-380)
        to test that failed_post_scenarios accumulates correctly across
        multiple scenario types.
        """
        failed_post_scenarios = []

        for scenario in chaos_scenarios:
            scenario_type = list(scenario.keys())[0]
            scenarios_list = scenario[scenario_type]
            if scenarios_list:
                # Simulate what create_plugin + run_scenarios returns
                mock_plugin = MagicMock()
                mock_plugin.run_scenarios.return_value = (
                    scenario["_mock_failures"],
                    scenario["_mock_telemetries"],
                )

                failed_scenarios_current, scenario_telemetries = (
                    mock_plugin.run_scenarios(
                        "test-uuid", scenarios_list, {}, None
                    )
                )
                # This is the fix — .extend() instead of = (overwrite)
                failed_post_scenarios.extend(failed_scenarios_current)

        return failed_post_scenarios

    def test_failures_from_earlier_scenarios_are_preserved(self):
        """
        When an earlier scenario type fails but a later one succeeds,
        the earlier failures must still be present in failed_post_scenarios.
        """
        chaos_scenarios = [
            {
                "pod_disruption_scenarios": ["scenarios/etcd.yml"],
                "_mock_failures": ["scenarios/etcd.yml"],
                "_mock_telemetries": [ScenarioTelemetry()],
            },
            {
                "hog_scenarios": ["scenarios/cpu-hog.yml"],
                "_mock_failures": [],
                "_mock_telemetries": [ScenarioTelemetry()],
            },
        ]

        failed = self._simulate_scenario_loop(chaos_scenarios)

        self.assertEqual(len(failed), 1)
        self.assertIn("scenarios/etcd.yml", failed)

    def test_failures_from_multiple_scenarios_are_accumulated(self):
        """
        When multiple scenario types fail, all failures must be collected.
        """
        chaos_scenarios = [
            {
                "pod_disruption_scenarios": ["scenarios/etcd.yml"],
                "_mock_failures": ["scenarios/etcd.yml"],
                "_mock_telemetries": [ScenarioTelemetry()],
            },
            {
                "hog_scenarios": ["scenarios/cpu-hog.yml"],
                "_mock_failures": ["scenarios/cpu-hog.yml"],
                "_mock_telemetries": [ScenarioTelemetry()],
            },
            {
                "node_scenarios": ["scenarios/node.yml"],
                "_mock_failures": [],
                "_mock_telemetries": [ScenarioTelemetry()],
            },
        ]

        failed = self._simulate_scenario_loop(chaos_scenarios)

        self.assertEqual(len(failed), 2)
        self.assertIn("scenarios/etcd.yml", failed)
        self.assertIn("scenarios/cpu-hog.yml", failed)

    def test_no_failures_returns_empty_list(self):
        """
        When all scenarios pass, failed_post_scenarios should be empty.
        """
        chaos_scenarios = [
            {
                "pod_disruption_scenarios": ["scenarios/etcd.yml"],
                "_mock_failures": [],
                "_mock_telemetries": [ScenarioTelemetry()],
            },
            {
                "hog_scenarios": ["scenarios/cpu-hog.yml"],
                "_mock_failures": [],
                "_mock_telemetries": [ScenarioTelemetry()],
            },
        ]

        failed = self._simulate_scenario_loop(chaos_scenarios)

        self.assertEqual(len(failed), 0)

    def test_last_scenario_failure_is_not_only_one_kept(self):
        """
        Regression: before the fix, only the last scenario type's failures
        survived. This test ensures that's no longer the case.
        """
        chaos_scenarios = [
            {
                "pod_disruption_scenarios": ["scenarios/etcd.yml"],
                "_mock_failures": ["scenarios/etcd.yml"],
                "_mock_telemetries": [ScenarioTelemetry()],
            },
            {
                "hog_scenarios": ["scenarios/cpu-hog.yml"],
                "_mock_failures": [],
                "_mock_telemetries": [ScenarioTelemetry()],
            },
            {
                "node_scenarios": ["scenarios/node.yml"],
                "_mock_failures": ["scenarios/node.yml"],
                "_mock_telemetries": [ScenarioTelemetry()],
            },
        ]

        failed = self._simulate_scenario_loop(chaos_scenarios)

        # Before the fix, only ["scenarios/node.yml"] would survive
        self.assertEqual(len(failed), 2)
        self.assertIn("scenarios/etcd.yml", failed)
        self.assertIn("scenarios/node.yml", failed)


if __name__ == "__main__":
    unittest.main()
