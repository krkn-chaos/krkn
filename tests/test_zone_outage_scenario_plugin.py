#!/usr/bin/env python3

"""
Test suite for ZoneOutageScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_zone_outage_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import yaml

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin import ZoneOutageScenarioPlugin


class TestZoneOutageScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ZoneOutageScenarioPlugin
        """
        self.plugin = ZoneOutageScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["zone_outages_scenarios"])
        self.assertEqual(len(result), 1)

    def test_node_based_zone_success_and_exception(self):
        plugin = ZoneOutageScenarioPlugin()
        kubecli = MagicMock()
        # two nodes returned
        kubecli.list_killable_nodes.return_value = ["n1", "n2"]

        # cloud object methods
        plugin.cloud_object = MagicMock()
        plugin.cloud_object.node_stop_scenario = MagicMock()
        plugin.cloud_object.node_start_scenario = MagicMock()

        scenario_config = {"zone": "z1", "duration": 0, "timeout": 1}
        with patch("time.sleep", return_value=None):
            ret = plugin.node_based_zone(scenario_config, kubecli)

        self.assertEqual(ret, 0)
        self.assertEqual(plugin.cloud_object.node_stop_scenario.call_count, 2)
        self.assertEqual(plugin.cloud_object.node_start_scenario.call_count, 2)

        # exception path: kubecli raises
        kubecli2 = MagicMock()
        kubecli2.list_killable_nodes.side_effect = Exception("boom")
        with patch("time.sleep", return_value=None):
            ret2 = plugin.node_based_zone(scenario_config, kubecli2)
        self.assertEqual(ret2, 1)

    def test_network_based_zone_with_and_without_default_acl(self):
        plugin = ZoneOutageScenarioPlugin()
        plugin.cloud_object = MagicMock()

        # describe returns associations containing our subnet and an original acl id
        plugin.cloud_object.describe_network_acls.return_value = (
            [{"SubnetId": "sub1", "NetworkAclAssociationId": "assoc1"}],
            "orig_acl",
        )
        plugin.cloud_object.replace_network_acl_association.return_value = "new_assoc"

        # Case A: default_acl_id provided -> should not call create/delete
        cfgA = {"vpc_id": "v", "subnet_id": ["sub1"], "duration": 0, "default_acl_id": "defacl"}
        with patch("time.sleep", return_value=None):
            plugin.network_based_zone(cfgA)

        plugin.cloud_object.replace_network_acl_association.assert_called()
        plugin.cloud_object.create_default_network_acl.assert_not_called()
        plugin.cloud_object.delete_network_acl.assert_not_called()

        # Case B: no default_acl_id -> create_default_network_acl called and delete_network_acl called after
        plugin2 = ZoneOutageScenarioPlugin()
        plugin2.cloud_object = MagicMock()
        plugin2.cloud_object.describe_network_acls.return_value = (
            [{"SubnetId": "sub1", "NetworkAclAssociationId": "assoc1"}],
            "orig_acl",
        )
        plugin2.cloud_object.create_default_network_acl.return_value = "created_acl"
        plugin2.cloud_object.replace_network_acl_association.return_value = "new_assoc"

        cfgB = {"vpc_id": "v", "subnet_id": ["sub1"], "duration": 0}
        with patch("time.sleep", return_value=None):
            plugin2.network_based_zone(cfgB)

        plugin2.cloud_object.create_default_network_acl.assert_called_with("v")
        plugin2.cloud_object.delete_network_acl.assert_called_with("created_acl")

    def test_run_unsupported_cloud_and_gcp_flow(self):
        plugin = ZoneOutageScenarioPlugin()
        # unsupported cloud
        cfg = {"zone_outage": {"cloud_type": "azure"}}
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                ret = plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=MagicMock(), scenario_telemetry=MagicMock())
        self.assertEqual(ret, 1)

        # gcp path: ensure affected_nodes are propagated
        cfg2 = {"zone_outage": {"cloud_type": "gcp", "zone": "z1"}}
        fake_affected = MagicMock()
        fake_affected.affected_nodes = ["n1"]

        def fake_gcp(kubecli, kube_check, affected_nodes_status):
            # set the provided object to include an affected nodes list
            affected_nodes_status.affected_nodes = ["n1"]
            obj = MagicMock()
            obj.affected_nodes_status = affected_nodes_status
            return obj

        scenario_telemetry = SimpleNamespace(affected_nodes=[])
        lib_tel = MagicMock()
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg2))):
            with patch("yaml.full_load", return_value=cfg2):
                with patch("krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.gcp_node_scenarios", side_effect=fake_gcp):
                    with patch("krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.time.sleep", return_value=None):
                        with patch("krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.cerberus.publish_kraken_status"):
                            ret2 = plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=scenario_telemetry)

        self.assertEqual(ret2, 0)
        self.assertIn("n1", scenario_telemetry.affected_nodes)

    def test_run_aws_calls_network_and_publishes(self):
        plugin = ZoneOutageScenarioPlugin()
        # stub network_based_zone to avoid needing cloud implementation
        plugin.network_based_zone = MagicMock()

        cfg = {"zone_outage": {"cloud_type": "aws", "vpc_id": "v", "subnet_id": ["s1"], "duration": 0}}

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                # patch AWS so it doesn't try to use boto3 during tests
                with patch("krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.AWS", return_value=MagicMock()):
                    with patch("krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.cerberus.publish_kraken_status") as mock_pub:
                        ret = plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=MagicMock(), scenario_telemetry=MagicMock())

        self.assertEqual(ret, 0)
        plugin.network_based_zone.assert_called()
        mock_pub.assert_called()

    def test_run_exception_in_publish_returns_1(self):
        plugin = ZoneOutageScenarioPlugin()
        cfg = {"zone_outage": {"cloud_type": "gcp", "zone": "z1"}}

        def fake_gcp(kubecli, kube_check, affected_nodes_status):
            obj = MagicMock()
            obj.affected_nodes_status = affected_nodes_status
            obj.affected_nodes_status.affected_nodes = []
            return obj

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                with patch("krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.gcp_node_scenarios", side_effect=fake_gcp):
                    with patch("krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.time.sleep", return_value=None):
                        with patch("krkn.scenario_plugins.zone_outage.zone_outage_scenario_plugin.cerberus.publish_kraken_status", side_effect=Exception("boom")):
                            ret = plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=MagicMock(), scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)


if __name__ == "__main__":
    unittest.main()
