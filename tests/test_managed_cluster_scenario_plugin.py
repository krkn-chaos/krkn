#!/usr/bin/env python3

"""
Test suite for ManagedClusterScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_managed_cluster_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import Mock, patch, call
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.managed_cluster.managed_cluster_scenario_plugin import ManagedClusterScenarioPlugin
from krkn.scenario_plugins.managed_cluster import common_functions


class TestManagedClusterScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ManagedClusterScenarioPlugin
        """
        self.plugin = ManagedClusterScenarioPlugin()
        self.mock_kubecli = Mock(spec=KrknKubernetes)

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["managedcluster_scenarios"])
        self.assertEqual(len(result), 1)

    @patch('time.time')
    @patch('builtins.open', create=True)
    @patch('yaml.full_load')
    @patch('krkn.cerberus.get_status')
    def test_run_multiple_actions_executes_all(self, mock_cerberus, mock_yaml, mock_open, mock_time):
        """
        Test that run() executes all actions, not just the first one
        This tests the fix for the early return bug
        """
        mock_time.return_value = 1234567890
        
        # Setup mock scenario config with multiple actions
        mock_yaml.return_value = {
            "managedcluster_scenarios": [
                {
                    "actions": [
                        "managedcluster_start_scenario",
                        "managedcluster_stop_scenario",
                        "managedcluster_reboot_scenario"
                    ],
                    "managedcluster_name": "test-cluster",
                    "runs": 1,
                    "instance_count": 1,
                    "timeout": 120
                }
            ]
        }
        
        mock_lib_telemetry = Mock(spec=KrknTelemetryOpenshift)
        mock_lib_telemetry.get_lib_kubernetes.return_value = self.mock_kubecli
        
        mock_scenario_telemetry = Mock()
        mock_krkn_config = {}
        
        # Mock inject_managedcluster_scenario to track calls
        call_tracker = []
        original_inject = self.plugin.inject_managedcluster_scenario
        def track_inject(action, *args, **kwargs):
            call_tracker.append(action)
        
        with patch.object(self.plugin, 'inject_managedcluster_scenario', side_effect=track_inject):
            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                krkn_config=mock_krkn_config,
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )
        
        # Assert all three actions were called
        self.assertEqual(result, 0)
        self.assertEqual(len(call_tracker), 3)
        self.assertIn("managedcluster_start_scenario", call_tracker)
        self.assertIn("managedcluster_stop_scenario", call_tracker)
        self.assertIn("managedcluster_reboot_scenario", call_tracker)
        
        # Assert cerberus was called 3 times (once per action)
        self.assertEqual(mock_cerberus.call_count, 3)

    @patch('time.time')
    @patch('builtins.open', create=True)
    @patch('yaml.full_load')
    def test_run_stops_on_first_error(self, mock_yaml, mock_open, mock_time):
        """
        Test that run() returns 1 and stops executing on first error
        """
        mock_time.return_value = 1234567890
        
        # Setup mock scenario config with multiple actions
        mock_yaml.return_value = {
            "managedcluster_scenarios": [
                {
                    "actions": [
                        "managedcluster_start_scenario",
                        "managedcluster_stop_scenario",
                        "managedcluster_reboot_scenario"
                    ],
                    "managedcluster_name": "test-cluster",
                    "runs": 1,
                    "instance_count": 1,
                    "timeout": 120
                }
            ]
        }
        
        mock_lib_telemetry = Mock(spec=KrknTelemetryOpenshift)
        mock_lib_telemetry.get_lib_kubernetes.return_value = self.mock_kubecli
        
        mock_scenario_telemetry = Mock()
        mock_krkn_config = {}
        
        # Mock inject_managedcluster_scenario to raise exception on first call
        call_tracker = []
        def track_inject_with_error(action, *args, **kwargs):
            call_tracker.append(action)
            if action == "managedcluster_start_scenario":
                raise Exception("Test failure")
        
        with patch.object(self.plugin, 'inject_managedcluster_scenario', side_effect=track_inject_with_error):
            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                krkn_config=mock_krkn_config,
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )
        
        # Assert failure and only first action was attempted
        self.assertEqual(result, 1)
        self.assertEqual(len(call_tracker), 1)
        self.assertEqual(call_tracker[0], "managedcluster_start_scenario")


class TestCommonFunctions(unittest.TestCase):
    """
    Test suite for common_functions module
    """

    def setUp(self):
        """
        Set up test fixtures for common_functions tests
        """
        self.mock_kubecli = Mock(spec=KrknKubernetes)

    def test_get_managedcluster_with_specific_name_exists(self):
        """
        Test get_managedcluster returns the specified cluster when it exists
        """
        self.mock_kubecli.list_killable_managedclusters.return_value = ["cluster1", "cluster2", "cluster3"]

        result = common_functions.get_managedcluster(
            "cluster1", "", 1, self.mock_kubecli
        )

        self.assertEqual(result, ["cluster1"])
        self.mock_kubecli.list_killable_managedclusters.assert_called_once_with()

    def test_get_managedcluster_with_specific_name_not_exists(self):
        """
        Test get_managedcluster falls back to label selector when specified cluster doesn't exist
        """
        self.mock_kubecli.list_killable_managedclusters.side_effect = [
            ["cluster2", "cluster3"],
            ["cluster2", "cluster3"]
        ]

        result = common_functions.get_managedcluster(
            "cluster1", "env=test", 1, self.mock_kubecli
        )

        self.assertEqual(len(result), 1)
        self.assertIn(result[0], ["cluster2", "cluster3"])

    def test_get_managedcluster_with_label_selector(self):
        """
        Test get_managedcluster returns clusters matching label selector
        """
        self.mock_kubecli.list_killable_managedclusters.side_effect = [
            ["cluster1", "cluster2", "cluster3"],
            ["cluster1", "cluster2", "cluster3"],
        ]

        result = common_functions.get_managedcluster(
            "", "env=production", 2, self.mock_kubecli
        )

        self.assertEqual(len(result), 2)
        # Should be called once without and once with label_selector
        self.assertEqual(
            self.mock_kubecli.list_killable_managedclusters.call_count,
            2,
        )
        self.mock_kubecli.list_killable_managedclusters.assert_has_calls(
            [call(), call("env=production")]
        )

    def test_get_managedcluster_no_available_clusters(self):
        """
        Test get_managedcluster raises exception when no clusters are available
        """
        self.mock_kubecli.list_killable_managedclusters.return_value = []

        with self.assertRaises(Exception) as context:
            common_functions.get_managedcluster(
                "", "env=nonexistent", 1, self.mock_kubecli
            )

        self.assertIn("Available managedclusters with the provided label selector do not exist", str(context.exception))

    def test_get_managedcluster_kill_count_equals_available(self):
        """
        Test get_managedcluster returns all clusters when instance_kill_count equals available clusters
        """
        available_clusters = ["cluster1", "cluster2", "cluster3"]
        self.mock_kubecli.list_killable_managedclusters.return_value = available_clusters

        result = common_functions.get_managedcluster(
            "", "env=test", 3, self.mock_kubecli
        )

        self.assertEqual(result, available_clusters)
        self.assertEqual(len(result), 3)

    @patch('logging.info')
    def test_get_managedcluster_return_empty_when_count_is_zero(self, mock_logging):
        """
        Test get_managedcluster returns empty list when instance_kill_count is 0
        """
        available_clusters = ["cluster1", "cluster2", "cluster3"]
        self.mock_kubecli.list_killable_managedclusters.return_value = available_clusters

        result = common_functions.get_managedcluster(
            "", "env=test", 0, self.mock_kubecli
        )

        self.assertEqual(result, [])
        mock_logging.assert_called()

    @patch('random.randint')
    def test_get_managedcluster_random_selection(self, mock_randint):
        """
        Test get_managedcluster randomly selects the specified number of clusters
        """
        available_clusters = ["cluster1", "cluster2", "cluster3", "cluster4", "cluster5"]
        self.mock_kubecli.list_killable_managedclusters.return_value = available_clusters.copy()
        mock_randint.side_effect = [1, 0, 2]

        result = common_functions.get_managedcluster(
            "", "env=test", 3, self.mock_kubecli
        )

        self.assertEqual(len(result), 3)
        for cluster in result:
            self.assertIn(cluster, available_clusters)
        # Ensure no duplicates
        self.assertEqual(len(result), len(set(result)))

    @patch('logging.info')
    def test_get_managedcluster_logs_available_clusters(self, mock_logging):
        """
        Test get_managedcluster logs available clusters with label selector
        """
        available_clusters = ["cluster1", "cluster2"]
        self.mock_kubecli.list_killable_managedclusters.return_value = available_clusters

        common_functions.get_managedcluster(
            "", "env=test", 1, self.mock_kubecli
        )

        mock_logging.assert_called()
        call_args = str(mock_logging.call_args)
        self.assertIn("Available managedclusters with the label selector", call_args)

    @patch('logging.info')
    def test_get_managedcluster_logs_when_name_not_found(self, mock_logging):
        """
        Test get_managedcluster logs when specified cluster name doesn't exist
        """
        self.mock_kubecli.list_killable_managedclusters.side_effect = [
            ["cluster2"],
            ["cluster2"]
        ]

        common_functions.get_managedcluster(
            "nonexistent-cluster", "env=test", 1, self.mock_kubecli
        )
        # Check that logging was called multiple times (including the info message about unavailable cluster)
        self.assertGreaterEqual(mock_logging.call_count, 1)  
        # Check all calls for the expected message
        all_calls = [str(call) for call in mock_logging.call_args_list]
        found_message = any("managedcluster with provided managedcluster_name does not exist" in call
                           for call in all_calls)
        self.assertTrue(found_message)

    def test_wait_for_available_status(self):
        """
        Test wait_for_available_status calls watch_managedcluster_status with correct parameters
        """
        common_functions.wait_for_available_status(
            "test-cluster", 300, self.mock_kubecli
        )

        self.mock_kubecli.watch_managedcluster_status.assert_called_once_with(
            "test-cluster", "True", 300
        )

    def test_wait_for_unavailable_status(self):
        """
        Test wait_for_unavailable_status calls watch_managedcluster_status with correct parameters
        """
        common_functions.wait_for_unavailable_status(
            "test-cluster", 300, self.mock_kubecli
        )

        self.mock_kubecli.watch_managedcluster_status.assert_called_once_with(
            "test-cluster", "Unknown", 300
        )


if __name__ == "__main__":
    unittest.main()
