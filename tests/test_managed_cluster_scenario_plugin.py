#!/usr/bin/env python3

"""
Test suite for ManagedClusterScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_managed_cluster_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.managed_cluster.managed_cluster_scenario_plugin import ManagedClusterScenarioPlugin
from unittest.mock import patch
import yaml
import logging


class TestManagedClusterScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ManagedClusterScenarioPlugin
        """
        self.plugin = ManagedClusterScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["managedcluster_scenarios"])
        self.assertEqual(len(result), 1)

    def test_run_success(self):
        """Test run() returns 0 on successful inject and calls cerberus.get_status"""
        plugin = ManagedClusterScenarioPlugin()

        # Prepare a fake scenario file content
        fake_scenario = {"managedcluster_scenarios": [{"actions": ["managedcluster_start_scenario"]}]}

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(fake_scenario))):
            with patch("yaml.full_load", return_value=fake_scenario):
                with patch.object(ManagedClusterScenarioPlugin, "inject_managedcluster_scenario") as mock_inject:
                    with patch("krkn.scenario_plugins.managed_cluster.managed_cluster_scenario_plugin.cerberus.get_status") as mock_get_status:
                        lib_tel = MagicMock()
                        lib_tel.get_lib_kubernetes.return_value = MagicMock()
                        scenario_tel = MagicMock()

                        ret = plugin.run("uuid", "scenario.yaml", {}, lib_tel, scenario_tel)

        self.assertEqual(ret, 0)
        mock_inject.assert_called_once()
        mock_get_status.assert_called_once()

    def test_run_exception_returns_one_and_logs(self):
        """If inject_managedcluster_scenario raises, run should log and return 1"""
        plugin = ManagedClusterScenarioPlugin()
        fake_scenario = {"managedcluster_scenarios": [{"actions": ["managedcluster_start_scenario"]}]}

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(fake_scenario))):
            with patch("yaml.full_load", return_value=fake_scenario):
                with patch.object(ManagedClusterScenarioPlugin, "inject_managedcluster_scenario", side_effect=Exception("boom")):
                    with patch("logging.error") as mock_log:
                        lib_tel = MagicMock()
                        lib_tel.get_lib_kubernetes.return_value = MagicMock()
                        scenario_tel = MagicMock()

                        ret = plugin.run("uuid", "scenario.yaml", {}, lib_tel, scenario_tel)

        self.assertEqual(ret, 1)
        mock_log.assert_called()

    def test_inject_managedcluster_scenario_dispatches_actions(self):
        """Verify inject_managedcluster_scenario calls the right method on the scenario object."""
        plugin = ManagedClusterScenarioPlugin()
        kubecli = MagicMock()

        # patch get_managedcluster to return a single managedcluster
        with patch("krkn.scenario_plugins.managed_cluster.managed_cluster_scenario_plugin.get_managedcluster", return_value=["mc1"]):
            # For each action, ensure the corresponding method is called
            actions_to_method = {
                "managedcluster_start_scenario": "managedcluster_start_scenario",
                "managedcluster_stop_scenario": "managedcluster_stop_scenario",
                "managedcluster_stop_start_scenario": "managedcluster_stop_start_scenario",
                "managedcluster_termination_scenario": "managedcluster_termination_scenario",
                "managedcluster_reboot_scenario": "managedcluster_reboot_scenario",
                "stop_start_klusterlet_scenario": "stop_start_klusterlet_scenario",
                "start_klusterlet_scenario": "stop_klusterlet_scenario",
                "stop_klusterlet_scenario": "stop_klusterlet_scenario",
                "managedcluster_crash_scenario": "managedcluster_crash_scenario",
            }

            for action, method_name in actions_to_method.items():
                mock_obj = MagicMock()
                # empty managedcluster_scenario -> defaults used inside function
                managedcluster_scenario = {}

                plugin.inject_managedcluster_scenario(action, managedcluster_scenario, mock_obj, kubecli)

                # method should have been called once with defaults (runs=1, single_managedcluster, timeout=120)
                getattr(mock_obj, method_name).assert_called_once_with(1, "mc1", 120)
                # reset mock for next iteration
                mock_obj.reset_mock()

    def test_inject_managedcluster_scenario_unknown_action_logs(self):
        plugin = ManagedClusterScenarioPlugin()
        kubecli = MagicMock()
        mock_obj = MagicMock()

        with patch("krkn.scenario_plugins.managed_cluster.managed_cluster_scenario_plugin.get_managedcluster", return_value=["mc1"]):
            with patch("logging.info") as mock_info:
                plugin.inject_managedcluster_scenario("not_an_action", {}, mock_obj, kubecli)
                mock_info.assert_called()

    def test_get_managedcluster_scenario_object_returns_scenarios(self):
        plugin = ManagedClusterScenarioPlugin()
        kubecli = MagicMock()

        with patch("krkn.scenario_plugins.managed_cluster.managed_cluster_scenario_plugin.Scenarios") as mock_scenarios:
            mock_scenarios.return_value = "scen_obj"
            res = plugin.get_managedcluster_scenario_object(kubecli)

        self.assertEqual(res, "scen_obj")

if __name__ == "__main__":
    unittest.main()
