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
Test suite for NativeScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_native_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.native.native_scenario_plugin import NativeScenarioPlugin


class TestNativeScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for NativeScenarioPlugin
        """
        self.plugin = NativeScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario types
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pod_network_scenarios", "ingress_node_scenarios"])
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
