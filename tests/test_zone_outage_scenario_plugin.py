#!/usr/bin/env python3

"""
Test suite for ZoneOutageScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_zone_outage_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin import ZoneOutageScenarioPlugin


class TestZoneOutageScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ZoneOutageScenarioPlugin
        Creates a fresh plugin instance for each test to avoid state pollution
        """
        self.plugin = ZoneOutageScenarioPlugin()

    def tearDown(self):
        """
        Clean up after each test to prevent state leakage between tests
        """
        # Clear any cloud_object that might have been set
        if hasattr(self.plugin, 'cloud_object'):
            delattr(self.plugin, 'cloud_object')
        # Create a completely fresh instance for the next test
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["zone_outages_scenarios"])
        self.assertEqual(len(result), 1)

    @unittest.mock.patch('builtins.open', create=True)
    @unittest.mock.patch('yaml.full_load')
    @unittest.mock.patch('krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.gcp_node_scenarios')
    @unittest.mock.patch('krkn.cerberus.publish_kraken_status')
    def test_run_propagates_node_based_zone_failure(self, mock_cerberus, mock_gcp_scenarios, mock_yaml, mock_open):
        """
        Test that run() properly propagates failure from node_based_zone method
        This tests the fix for the ignored return value bug
        """
        # Setup mock scenario config for GCP
        mock_yaml.return_value = {
            "zone_outage": {
                "cloud_type": "gcp",
                "zone": "us-central1-a",
                "duration": 60,
                "timeout": 180,
                "kube_check": True
            }
        }

        mock_lib_telemetry = MagicMock()
        mock_kubecli = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_kubecli

        # Mock GCP scenarios
        mock_gcp_instance = MagicMock()
        mock_affected_nodes_status = MagicMock()
        mock_affected_nodes_status.affected_nodes = []
        mock_gcp_instance.affected_nodes_status = mock_affected_nodes_status
        mock_gcp_scenarios.return_value = mock_gcp_instance

        # Mock node_based_zone to return failure
        with unittest.mock.patch.object(self.plugin, 'node_based_zone', return_value=1):
            mock_scenario_telemetry = MagicMock()
            mock_scenario_telemetry.affected_nodes = []  # Must be a list for .extend()
            mock_krkn_config = {}

            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                krkn_config=mock_krkn_config,
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )

            # Assert failure is properly propagated
            self.assertEqual(result, 1)

    @unittest.mock.patch('builtins.open', create=True)
    @unittest.mock.patch('yaml.full_load')
    @unittest.mock.patch('krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.gcp_node_scenarios')
    @unittest.mock.patch('krkn.cerberus.publish_kraken_status')
    def test_run_succeeds_when_node_based_zone_succeeds(self, mock_cerberus, mock_gcp_scenarios, mock_yaml, mock_open):
        """
        Test that run() returns 0 when node_based_zone succeeds
        """
        # Setup mock scenario config for GCP
        mock_yaml.return_value = {
            "zone_outage": {
                "cloud_type": "gcp",
                "zone": "us-central1-a",
                "duration": 60,
                "timeout": 180,
                "kube_check": True
            }
        }

        mock_lib_telemetry = MagicMock()
        mock_kubecli = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_kubecli

        # Mock GCP scenarios
        mock_gcp_instance = MagicMock()
        mock_affected_nodes_status = MagicMock()
        mock_affected_nodes_status.affected_nodes = []
        mock_gcp_instance.affected_nodes_status = mock_affected_nodes_status
        mock_gcp_scenarios.return_value = mock_gcp_instance

        # Mock node_based_zone to return success
        with unittest.mock.patch.object(self.plugin, 'node_based_zone', return_value=0):
            mock_scenario_telemetry = MagicMock()
            mock_scenario_telemetry.affected_nodes = []  # Must be a list for .extend()
            mock_krkn_config = {}

            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                krkn_config=mock_krkn_config,
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )

            # Assert success
            self.assertEqual(result, 0)

    @unittest.mock.patch('builtins.open', create=True)
    @unittest.mock.patch('yaml.full_load')
    @unittest.mock.patch('krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.AWS')
    @unittest.mock.patch('krkn.cerberus.publish_kraken_status')
    def test_run_aws_network_based_zone(self, mock_cerberus, mock_aws_class, mock_yaml, mock_open):
        """
        Test that run() handles AWS network-based zone outage correctly
        """
        # Setup mock scenario config for AWS
        mock_yaml.return_value = {
            "zone_outage": {
                "cloud_type": "aws",
                "vpc_id": "vpc-12345",
                "subnet_id": ["subnet-1", "subnet-2"],
                "duration": 60
            }
        }
        
        mock_aws_instance = MagicMock()
        mock_aws_class.return_value = mock_aws_instance
        
        # Mock the network_based_zone method to return success
        with unittest.mock.patch.object(self.plugin, 'network_based_zone', return_value=0):
            mock_lib_telemetry = MagicMock()
            mock_scenario_telemetry = MagicMock()
            mock_scenario_telemetry.affected_nodes = []  # Must be a list for .extend()
            mock_krkn_config = {}
            
            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                krkn_config=mock_krkn_config,
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )
            
            # Assert success
            self.assertEqual(result, 0)

    @unittest.mock.patch('builtins.open', create=True)
    @unittest.mock.patch('yaml.full_load')
    @unittest.mock.patch('krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.AWS')
    @unittest.mock.patch('krkn.cerberus.publish_kraken_status')
    def test_run_aws_network_based_zone_failure(self, mock_cerberus, mock_aws_class, mock_yaml, mock_open):
        """
        Test that run() properly propagates failure from network_based_zone method
        """
        # Setup mock scenario config for AWS
        mock_yaml.return_value = {
            "zone_outage": {
                "cloud_type": "aws",
                "vpc_id": "vpc-12345",
                "subnet_id": ["subnet-1", "subnet-2"],
                "duration": 60
            }
        }

        mock_aws_instance = MagicMock()
        mock_aws_class.return_value = mock_aws_instance

        # Mock the network_based_zone method to return failure
        with unittest.mock.patch.object(self.plugin, 'network_based_zone', return_value=1):
            mock_lib_telemetry = MagicMock()
            mock_scenario_telemetry = MagicMock()
            mock_scenario_telemetry.affected_nodes = []  # Must be a list for .extend()
            mock_krkn_config = {}

            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                krkn_config=mock_krkn_config,
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )

            # Assert failure is properly propagated
            self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
