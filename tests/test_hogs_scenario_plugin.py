#!/usr/bin/env python3

"""
Test suite for HogsScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_hogs_scenario_plugin.py -v
"""

import unittest
from unittest.mock import MagicMock, patch

from krkn_lib.models.krkn import HogConfig

from krkn.scenario_plugins.hogs.hogs_scenario_plugin import HogsScenarioPlugin


class TestHogsScenarioPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = HogsScenarioPlugin()

    def test_get_scenario_types(self):
        result = self.plugin.get_scenario_types()
        self.assertEqual(result, ["hog_scenarios"])
        self.assertEqual(len(result), 1)

    def test_run_scenario_no_selector_targets_single_node(self):
        config = MagicMock(spec=HogConfig)
        config.node_selector = None
        config.number_of_nodes = None

        lib_telemetry = MagicMock()
        lib_k8s = MagicMock()
        lib_telemetry.get_lib_kubernetes.return_value = lib_k8s
        lib_k8s.list_nodes.return_value = ["node1", "node2", "node3"]

        with patch.object(self.plugin, "run_scenario") as mock_run_scenario:
            with patch("krkn.scenario_plugins.hogs.hogs_scenario_plugin.yaml.safe_load", return_value={"node_selector": None}), \
                 patch("krkn.scenario_plugins.hogs.hogs_scenario_plugin.HogConfig.from_yaml_dict", return_value=config), \
                 patch("builtins.open", unittest.mock.mock_open(read_data="")):
                self.plugin.run(run_uuid="run-uuid", scenario="scenario.yaml", lib_telemetry=lib_telemetry, scenario_telemetry=MagicMock())

            called_nodes = mock_run_scenario.call_args[0][2]
            self.assertEqual(len(called_nodes), 1, "Expected exactly one node when no selector is provided")


if __name__ == "__main__":
    unittest.main()
