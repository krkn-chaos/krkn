#!/usr/bin/env python3

"""
Test suite for HogsScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_hogs_scenario_plugin.py -v

"""

import queue
import unittest
from unittest.mock import MagicMock, patch

from krkn_lib.models.krkn import HogConfig, HogType
from krkn_lib.models.k8s import NodeResources

from krkn.scenario_plugins.hogs.hogs_scenario_plugin import HogsScenarioPlugin


class TestHogsScenarioPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = HogsScenarioPlugin()

    def test_get_scenario_types(self):
        result = self.plugin.get_scenario_types()
        self.assertEqual(result, ["hog_scenarios"])
        self.assertEqual(len(result), 1)

    def test_run_scenario_worker_no_samples_no_zero_division(self):
        config = MagicMock(spec=HogConfig)
        config.workers = 2
        config.type = HogType.cpu
        config.namespace = "default"
        config.duration = 3

        lib_k8s = MagicMock()
        lib_k8s.get_node_resources_info.return_value = NodeResources()
        lib_k8s.is_pod_running.return_value = False

        exception_queue = queue.Queue()

        with patch("krkn.scenario_plugins.hogs.hogs_scenario_plugin.time.sleep"), \
             patch("krkn.scenario_plugins.hogs.hogs_scenario_plugin.time.time", side_effect=[0, 1000, 1000, 1000]):
            self.plugin.run_scenario_worker(config, lib_k8s, "test-node", exception_queue)

        if not exception_queue.empty():
            raise exception_queue.get_nowait()
        self.assertTrue(exception_queue.empty(), "ZeroDivisionError or other exception raised when samples list is empty")


if __name__ == "__main__":
    unittest.main()
