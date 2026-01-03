#!/usr/bin/env python3

"""
Test suite for ShutDownScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_shut_down_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import Mock, patch, mock_open

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.models.k8s import AffectedNodeStatus

from krkn.scenario_plugins.shut_down.shut_down_scenario_plugin import ShutDownScenarioPlugin


class TestShutDownScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ShutDownScenarioPlugin
        """
        self.plugin = ShutDownScenarioPlugin()
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.mock_lib_telemetry = Mock(spec=KrknTelemetryOpenshift)
        self.mock_lib_telemetry.get_lib_kubernetes.return_value = self.mock_kubecli
        self.mock_scenario_telemetry = Mock(spec=ScenarioTelemetry)
        self.mock_scenario_telemetry.affected_nodes = []

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["cluster_shut_down_scenarios"])
        self.assertEqual(len(result), 1)

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.cerberus')
    @patch('time.time')
    @patch('time.sleep')
    @patch('builtins.open', new_callable=mock_open)
    def test_run_success_aws(self, mock_file, mock_sleep, mock_time, mock_cerberus):
        """
        Test successful run of shut down scenario with AWS cloud type
        """
        scenario_yaml = {
            "cluster_shut_down_scenario": {
                "runs": 1,
                "shut_down_duration": 60,
                "cloud_type": "aws",
                "timeout": 300
            }
        }

        mock_time.side_effect = [1000, 2000]
        self.mock_kubecli.list_nodes.return_value = ["node1", "node2"]

        with patch('yaml.full_load', return_value=scenario_yaml):
            with patch.object(self.plugin, 'cluster_shut_down') as mock_cluster_shutdown:
                result = self.plugin.run(
                    "test-uuid",
                    "/path/to/scenario.yaml",
                    {},
                    self.mock_lib_telemetry,
                    self.mock_scenario_telemetry
                )

        self.assertEqual(result, 0)
        mock_cluster_shutdown.assert_called_once()
        mock_cerberus.publish_kraken_status.assert_called_once()

    @patch('logging.error')
    @patch('builtins.open', new_callable=mock_open)
    def test_run_with_exception(self, mock_file, mock_logging):
        """
        Test run handles exceptions and returns 1
        """
        mock_file.return_value.__enter__.side_effect = Exception("File read error")

        result = self.plugin.run(
            "test-uuid",
            "/path/to/scenario.yaml",
            {},
            self.mock_lib_telemetry,
            self.mock_scenario_telemetry
        )

        self.assertEqual(result, 1)
        mock_logging.assert_called_once()
        logged_message = mock_logging.call_args[0][0]
        self.assertIn("File read error", logged_message)
        self.assertIn("/path/to/scenario.yaml", logged_message)

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.AWS')
    @patch('time.sleep')
    @patch('time.time')
    def test_cluster_shut_down_aws(self, mock_time, mock_sleep, mock_aws_class):
        """
        Test cluster_shut_down with AWS cloud type
        """
        shut_down_config = {
            "runs": 1,
            "shut_down_duration": 60,
            "cloud_type": "aws",
            "timeout": 300
        }

        mock_cloud_object = Mock()
        mock_aws_class.return_value = mock_cloud_object
        mock_cloud_object.get_instance_id.return_value = "i-123"  
        mock_cloud_object.wait_until_stopped.return_value = True
        mock_cloud_object.wait_until_running.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["node1", "node2"]
        affected_nodes_status = AffectedNodeStatus()
        mock_time.return_value = 1000

        with patch.object(self.plugin, 'multiprocess_nodes') as mock_multiprocess:
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        mock_aws_class.assert_called_once()
        self.assertEqual(mock_multiprocess.call_count, 2)
        self.assertEqual(len(affected_nodes_status.affected_nodes), 2)

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.GCP')
    @patch('time.sleep')
    @patch('time.time')
    def test_cluster_shut_down_gcp(self, mock_time, mock_sleep, mock_gcp_class):
        """
        Test cluster_shut_down with GCP cloud type
        """
        shut_down_config = {
            "runs": 1,
            "shut_down_duration": 30,
            "cloud_type": "gcp",
            "timeout": 300
        }

        mock_cloud_object = Mock()
        mock_gcp_class.return_value = mock_cloud_object
        mock_cloud_object.get_instance_id.side_effect = ["gcp-1", "gcp-2"]
        mock_cloud_object.wait_until_stopped.return_value = True
        mock_cloud_object.wait_until_running.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["node1", "node2"]
        affected_nodes_status = AffectedNodeStatus()
        mock_time.return_value = 1000

        with patch.object(self.plugin, 'multiprocess_nodes') as mock_multiprocess:
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        mock_gcp_class.assert_called_once()
        # Verify that the 'processes' parameter is set to 1 for GCP cloud type
        calls = mock_multiprocess.call_args_list
        for call_args in calls:
            self.assertEqual(call_args[0][2], 1)

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.Azure')
    @patch('time.sleep')
    @patch('time.time')
    def test_cluster_shut_down_azure(self, mock_time, mock_sleep, mock_azure_class):
        """
        Test cluster_shut_down with Azure cloud type
        """
        shut_down_config = {
            "runs": 1,
            "shut_down_duration": 45,
            "cloud_type": "azure",
            "timeout": 300
        }

        mock_cloud_object = Mock()
        mock_azure_class.return_value = mock_cloud_object
        mock_cloud_object.get_instance_id.side_effect = ["azure-1"]
        mock_cloud_object.wait_until_stopped.return_value = True
        mock_cloud_object.wait_until_running.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["node1"]
        affected_nodes_status = AffectedNodeStatus()
        mock_time.return_value = 1000

        with patch.object(self.plugin, 'multiprocess_nodes'):
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        mock_azure_class.assert_called_once()

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.Azure')
    @patch('time.sleep')
    @patch('time.time')
    def test_cluster_shut_down_az_alias(self, mock_time, mock_sleep, mock_azure_class):
        """
        Test cluster_shut_down with 'az' cloud type alias for Azure
        """
        shut_down_config = {
            "runs": 1,
            "shut_down_duration": 30,
            "cloud_type": "az",
            "timeout": 300
        }

        mock_cloud_object = Mock()
        mock_azure_class.return_value = mock_cloud_object
        mock_cloud_object.get_instance_id.side_effect = ["azure-1"]
        mock_cloud_object.wait_until_stopped.return_value = True
        mock_cloud_object.wait_until_running.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["node1"]
        affected_nodes_status = AffectedNodeStatus()
        mock_time.return_value = 1000

        with patch.object(self.plugin, 'multiprocess_nodes'):
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        mock_azure_class.assert_called_once()

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.OPENSTACKCLOUD')
    @patch('time.sleep')
    @patch('time.time')
    def test_cluster_shut_down_openstack(self, mock_time, mock_sleep, mock_openstack_class):
        """
        Test cluster_shut_down with OpenStack cloud type
        """
        shut_down_config = {
            "runs": 1,
            "shut_down_duration": 60,
            "cloud_type": "openstack",
            "timeout": 300
        }

        mock_cloud_object = Mock()
        mock_openstack_class.return_value = mock_cloud_object
        mock_cloud_object.get_instance_id.side_effect = ["os-1"]
        mock_cloud_object.wait_until_stopped.return_value = True
        mock_cloud_object.wait_until_running.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["node1"]
        affected_nodes_status = AffectedNodeStatus()
        mock_time.return_value = 1000

        with patch.object(self.plugin, 'multiprocess_nodes'):
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        mock_openstack_class.assert_called_once()

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.IbmCloud')
    @patch('time.sleep')
    @patch('time.time')
    def test_cluster_shut_down_ibm(self, mock_time, mock_sleep, mock_ibm_class):
        """
        Test cluster_shut_down with IBM cloud type
        """
        shut_down_config = {
            "runs": 1,
            "shut_down_duration": 60,
            "cloud_type": "ibm",
            "timeout": 300
        }

        mock_cloud_object = Mock()
        mock_ibm_class.return_value = mock_cloud_object
        mock_cloud_object.get_instance_id.side_effect = ["ibm-1"]
        mock_cloud_object.wait_until_stopped.return_value = True
        mock_cloud_object.wait_until_running.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["node1"]
        affected_nodes_status = AffectedNodeStatus()
        mock_time.return_value = 1000

        with patch.object(self.plugin, 'multiprocess_nodes'):
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        mock_ibm_class.assert_called_once()

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.IbmCloud')
    @patch('time.sleep')
    @patch('time.time')
    def test_cluster_shut_down_ibmcloud_alias(self, mock_time, mock_sleep, mock_ibm_class):
        """
        Test cluster_shut_down with 'ibmcloud' cloud type alias
        """
        shut_down_config = {
            "runs": 1,
            "shut_down_duration": 60,
            "cloud_type": "ibmcloud",
            "timeout": 300
        }

        mock_cloud_object = Mock()
        mock_ibm_class.return_value = mock_cloud_object
        mock_cloud_object.get_instance_id.side_effect = ["ibm-1"]
        mock_cloud_object.wait_until_stopped.return_value = True
        mock_cloud_object.wait_until_running.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["node1"]
        affected_nodes_status = AffectedNodeStatus()
        mock_time.return_value = 1000

        with patch.object(self.plugin, 'multiprocess_nodes'):
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        mock_ibm_class.assert_called_once()

    @patch('logging.error')
    def test_cluster_shut_down_unsupported_cloud(self, mock_logging):
        """
        Test cluster_shut_down raises exception for unsupported cloud type
        """
        shut_down_config = {
            "runs": 1,
            "shut_down_duration": 60,
            "cloud_type": "unsupported",
            "timeout": 300
        }

        affected_nodes_status = AffectedNodeStatus()

        with self.assertRaises(RuntimeError):
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        mock_logging.assert_called()
        logged_message = mock_logging.call_args[0][0]  
        self.assertIn("not currently supported", logged_message)
    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.AWS')
    @patch('time.sleep')
    @patch('time.time')
    def test_cluster_shut_down_multiple_runs(self, mock_time, mock_sleep, mock_aws_class):
        """
        Test cluster_shut_down with multiple runs
        """
        shut_down_config = {
            "runs": 2,
            "shut_down_duration": 30,
            "cloud_type": "aws",
            "timeout": 300
        }

        mock_cloud_object = Mock()
        mock_aws_class.return_value = mock_cloud_object
        mock_cloud_object.get_instance_id.return_value = "i-123"
        mock_cloud_object.wait_until_stopped.return_value = True
        mock_cloud_object.wait_until_running.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["node1"]
        affected_nodes_status = AffectedNodeStatus()
        mock_time.return_value = 1000

        with patch.object(self.plugin, 'multiprocess_nodes') as mock_multiprocess:
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        # Each run should call multiprocess_nodes twice (stop and start)
        self.assertEqual(mock_multiprocess.call_count, 4)

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.ThreadPool')
    def test_multiprocess_nodes_simple_list(self, mock_threadpool):
        """
        Test multiprocess_nodes with simple list of nodes
        """
        mock_pool_instance = Mock()
        mock_threadpool.return_value = mock_pool_instance

        nodes = ["node1", "node2", "node3"]
        mock_cloud_function = Mock()

        self.plugin.multiprocess_nodes(mock_cloud_function, nodes, processes=0)

        mock_threadpool.assert_called_once_with(processes=3)
        mock_pool_instance.map.assert_called_once_with(mock_cloud_function, nodes)
        mock_pool_instance.close.assert_called_once()

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.ThreadPool')
    def test_multiprocess_nodes_with_custom_processes(self, mock_threadpool):
        """
        Test multiprocess_nodes with custom process count
        """
        mock_pool_instance = Mock()
        mock_threadpool.return_value = mock_pool_instance

        nodes = ["node1", "node2", "node3", "node4"]
        mock_cloud_function = Mock()

        self.plugin.multiprocess_nodes(mock_cloud_function, nodes, processes=2)

        mock_threadpool.assert_called_once_with(processes=2)
        mock_pool_instance.map.assert_called_once_with(mock_cloud_function, nodes)
        mock_pool_instance.close.assert_called_once()

    @patch('logging.info')
    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.ThreadPool')
    def test_multiprocess_nodes_tuple_list(self, mock_threadpool, mock_logging):
        """
        Test multiprocess_nodes with tuple list (node_info, node_id pairs)
        """
        mock_pool_instance = Mock()
        mock_threadpool.return_value = mock_pool_instance

        nodes = [("info1", "id1"), ("info2", "id2")]
        mock_cloud_function = Mock()

        self.plugin.multiprocess_nodes(mock_cloud_function, nodes, processes=0)

        mock_threadpool.assert_called_once_with(processes=2)
        mock_pool_instance.starmap.assert_called_once()
        # Verify starmap was called with zipped arguments
        call_args = mock_pool_instance.starmap.call_args[0]
        self.assertEqual(call_args[0], mock_cloud_function)
        mock_pool_instance.close.assert_called_once()

    @patch('logging.info')
    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.ThreadPool')
    def test_multiprocess_nodes_with_exception(self, mock_threadpool, mock_logging):
        """
        Test multiprocess_nodes handles exceptions gracefully
        """
        mock_threadpool.side_effect = Exception("Pool creation error")

        nodes = ["node1", "node2"]
        mock_cloud_function = Mock()

        self.plugin.multiprocess_nodes(mock_cloud_function, nodes, processes=0)

        mock_logging.assert_called()
        logged_args, logged_kwargs = mock_logging.call_args  
        self.assertIn("Error on pool multiprocessing", logged_args[0])
    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.AWS')
    @patch('time.sleep')
    @patch('time.time')
    def test_cluster_shut_down_node_stop_timing(self, mock_time, mock_sleep, mock_aws_class):
        """
        Test that cloud_stopping_time is set correctly
        """
        shut_down_config = {
            "runs": 1,
            "shut_down_duration": 60,
            "cloud_type": "aws",
            "timeout": 300
        }

        mock_cloud_object = Mock()
        mock_aws_class.return_value = mock_cloud_object
        mock_cloud_object.get_instance_id.return_value = "i-123"
        mock_cloud_object.wait_until_stopped.return_value = True
        mock_cloud_object.wait_until_running.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["node1"]
        affected_nodes_status = AffectedNodeStatus()

        # Simulate time progression - provide enough values for all time.time() calls
        mock_time.side_effect = [1000, 1050, 1100, 1150, 1200]

        with patch.object(self.plugin, 'multiprocess_nodes'):
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        # Verify affected node was created
        self.assertEqual(len(affected_nodes_status.affected_nodes), 1)

    @patch('krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.AWS')
    @patch('time.sleep')
    @patch('time.time')
    def test_cluster_shut_down_wait_for_initialization(self, mock_time, mock_sleep, mock_aws_class):
        """
        Test that cluster_shut_down waits 150s for component initialization
        """
        shut_down_config = {
            "runs": 1,
            "shut_down_duration": 60,
            "cloud_type": "aws",
            "timeout": 300
        }

        mock_cloud_object = Mock()
        mock_aws_class.return_value = mock_cloud_object
        mock_cloud_object.get_instance_id.return_value = "i-123"
        mock_cloud_object.wait_until_stopped.return_value = True
        mock_cloud_object.wait_until_running.return_value = True

        self.mock_kubecli.list_nodes.return_value = ["node1"]
        affected_nodes_status = AffectedNodeStatus()
        mock_time.return_value = 1000

        with patch.object(self.plugin, 'multiprocess_nodes'):
            self.plugin.cluster_shut_down(shut_down_config, self.mock_kubecli, affected_nodes_status)

        # Verify sleep was called with correct durations
        sleep_calls = [call_args[0][0] for call_args in mock_sleep.call_args_list]
        self.assertIn(60, sleep_calls)  # shut_down_duration
        self.assertIn(150, sleep_calls)  # component initialization wait


if __name__ == "__main__":
    unittest.main()
