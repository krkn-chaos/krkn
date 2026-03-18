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
Test suite for TimeActionsScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_time_actions_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.time_actions.time_actions_scenario_plugin import TimeActionsScenarioPlugin


class TestTimeActionsScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for TimeActionsScenarioPlugin
        """
        self.plugin = TimeActionsScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["time_scenarios"])
        self.assertEqual(len(result), 1)

    @patch("krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.logging")
    @patch("builtins.open", side_effect=RuntimeError("disk quota exceeded"))
    def test_exception_variable_bound_in_except_handler(self, mock_open, mock_logging):
        """run() must bind exception variable so logging shows actual error, not NameError"""
        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario="fake_scenario.yaml",
            lib_telemetry=MagicMock(),
            scenario_telemetry=MagicMock(),
        )

        self.assertEqual(result, 1)
        logged_msg = mock_logging.error.call_args[0][0]
        self.assertIn("disk quota exceeded", logged_msg)
        self.assertNotIn("NameError", logged_msg)


if __name__ == "__main__":
    unittest.main()
