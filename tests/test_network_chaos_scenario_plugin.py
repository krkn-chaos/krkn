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
Test suite for NetworkChaosScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_network_chaos_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.network_chaos.network_chaos_scenario_plugin import NetworkChaosScenarioPlugin


class TestNetworkChaosScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for NetworkChaosScenarioPlugin
        """
        self.plugin = NetworkChaosScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["network_chaos_scenarios"])
        self.assertEqual(len(result), 1)

    def test_get_job_pods_empty_list_raises_exception(self):
        """
        Test get_job_pods raises descriptive error when no pods match the label selector
        """
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_kubecli.list_pods.return_value = []

        mock_api_response = MagicMock()
        mock_api_response.metadata.labels = {"controller-uid": "test-uid-123"}

        with self.assertRaises(Exception) as context:
            self.plugin.get_job_pods(mock_api_response, mock_kubecli)

        self.assertIn("No pods found matching label selector", str(context.exception))
        self.assertIn("controller-uid=test-uid-123", str(context.exception))

    def test_get_job_pods_returns_first_pod(self):
        """
        Test get_job_pods returns the first pod when pods are found
        """
        mock_kubecli = MagicMock(spec=KrknKubernetes)
        mock_kubecli.list_pods.return_value = ["pod-1", "pod-2"]

        mock_api_response = MagicMock()
        mock_api_response.metadata.labels = {"controller-uid": "test-uid-456"}

        result = self.plugin.get_job_pods(mock_api_response, mock_kubecli)

        self.assertEqual(result, "pod-1")
        mock_kubecli.list_pods.assert_called_once_with(
            label_selector="controller-uid=test-uid-456", namespace="default"
        )


if __name__ == "__main__":
    unittest.main()
