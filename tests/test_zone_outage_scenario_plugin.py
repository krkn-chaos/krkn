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
Test suite for ZoneOutageScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest \
        tests/test_zone_outage_scenario_plugin.py -v

Assisted By: Claude Code
"""

import base64
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from krkn.rollback.config import RollbackContent
from krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin import (
    ZoneOutageScenarioPlugin,
)


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

            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
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

            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
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
            
            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
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

            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )

            # Assert failure is properly propagated
            self.assertEqual(result, 1)


class TestRollbackGcpZoneOutage(unittest.TestCase):
    """Tests for the GCP zone outage rollback functionality"""

    @patch(
        "krkn.scenario_plugins.node_actions."
        "gcp_node_scenarios.gcp_node_scenarios"
    )
    def test_rollback_gcp_zone_outage_success(self, mock_gcp_class):
        """
        Test successful rollback starts all stopped nodes
        """
        rollback_data = {
            "nodes": ["node-1", "node-2", "node-3"],
            "timeout": 180,
            "kube_check": True,
        }
        encoded = base64.b64encode(
            json.dumps(rollback_data).encode("utf-8")
        ).decode("utf-8")

        rollback_content = RollbackContent(
            resource_identifier=encoded,
        )

        mock_lib_telemetry = MagicMock()
        mock_kubecli = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_kubecli

        mock_cloud_instance = MagicMock()
        mock_gcp_class.return_value = mock_cloud_instance

        ZoneOutageScenarioPlugin.rollback_gcp_zone_outage(
            rollback_content, mock_lib_telemetry
        )

        self.assertEqual(
            mock_cloud_instance.node_start_scenario.call_count, 3
        )
        mock_cloud_instance.node_start_scenario.assert_any_call(
            1, "node-1", 180, None
        )
        mock_cloud_instance.node_start_scenario.assert_any_call(
            1, "node-2", 180, None
        )
        mock_cloud_instance.node_start_scenario.assert_any_call(
            1, "node-3", 180, None
        )

    @patch(
        "krkn.scenario_plugins.node_actions."
        "gcp_node_scenarios.gcp_node_scenarios"
    )
    def test_rollback_gcp_zone_outage_partial_failure(self, mock_gcp_class):
        """
        Test rollback continues when one node fails to start
        """
        rollback_data = {
            "nodes": ["node-1", "node-2"],
            "timeout": 180,
            "kube_check": True,
        }
        encoded = base64.b64encode(
            json.dumps(rollback_data).encode("utf-8")
        ).decode("utf-8")

        rollback_content = RollbackContent(
            resource_identifier=encoded,
        )

        mock_lib_telemetry = MagicMock()
        mock_kubecli = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_kubecli

        mock_cloud_instance = MagicMock()
        mock_gcp_class.return_value = mock_cloud_instance
        mock_cloud_instance.node_start_scenario.side_effect = [
            Exception("GCP API error"),
            None,
        ]

        ZoneOutageScenarioPlugin.rollback_gcp_zone_outage(
            rollback_content, mock_lib_telemetry
        )

        self.assertEqual(
            mock_cloud_instance.node_start_scenario.call_count, 2
        )

    def test_rollback_gcp_zone_outage_invalid_data(self):
        """
        Test rollback raises exception for invalid base64 data
        """
        rollback_content = RollbackContent(
            resource_identifier="invalid_base64_data",
        )

        mock_lib_telemetry = MagicMock()

        with self.assertRaises(Exception):
            ZoneOutageScenarioPlugin.rollback_gcp_zone_outage(
                rollback_content, mock_lib_telemetry
            )


class TestZoneOutageRun(unittest.TestCase):
    """Tests for the run method of ZoneOutageScenarioPlugin"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_scenario_file(self, config=None):
        """Helper to create a temporary scenario YAML file"""
        default_config = {
            "zone_outage": {
                "cloud_type": "gcp",
                "zone": "us-central1-a",
                "duration": 1,
                "timeout": 10,
                "kube_check": True,
            }
        }
        if config:
            default_config["zone_outage"].update(config)
        scenario_file = self.tmp_path / "test_scenario.yaml"
        with open(scenario_file, "w") as f:
            yaml.dump(default_config, f)
        return str(scenario_file)

    def _create_mocks(self):
        """Helper to create mock objects for testing"""
        mock_lib_telemetry = MagicMock()
        mock_lib_kubernetes = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = (
            mock_lib_kubernetes
        )
        mock_scenario_telemetry = MagicMock()
        return mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry

    @patch("time.sleep")
    @patch(
        "krkn.scenario_plugins.zone_outage."
        "zone_outage_scenario_plugin.gcp_node_scenarios"
    )
    def test_run_gcp_success(self, mock_gcp_class, mock_sleep):
        """Test successful GCP zone outage scenario execution"""
        scenario_file = self._create_scenario_file()
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        mock_lib_kubernetes.list_killable_nodes.return_value = ["node-1"]
        mock_cloud = MagicMock()
        mock_gcp_class.return_value = mock_cloud

        plugin = ZoneOutageScenarioPlugin()
        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        self.assertEqual(result, 0)
        mock_lib_kubernetes.list_killable_nodes.assert_called_once()
        mock_cloud.node_stop_scenario.assert_called()
        mock_cloud.node_start_scenario.assert_called()

    def test_run_unsupported_cloud_type(self):
        """Test run returns 1 for unsupported cloud type"""
        scenario_file = self._create_scenario_file(
            {"cloud_type": "unsupported"}
        )
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        plugin = ZoneOutageScenarioPlugin()
        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        self.assertEqual(result, 1)

    def test_run_gcp_exception(self):
        """Test run handles exceptions gracefully"""
        scenario_file = self._create_scenario_file()
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        mock_lib_telemetry.get_lib_kubernetes.side_effect = Exception(
            "Connection error"
        )

        plugin = ZoneOutageScenarioPlugin()
        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
