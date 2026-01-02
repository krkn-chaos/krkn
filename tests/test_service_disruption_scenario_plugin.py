#!/usr/bin/env python3

"""
Test suite for ServiceDisruptionScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_service_disruption_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock,patch
import yaml
from types import SimpleNamespace

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.service_disruption.service_disruption_scenario_plugin import ServiceDisruptionScenarioPlugin


class TestServiceDisruptionScenarioPluginExtended(unittest.TestCase):

    def setUp(self):
        self.plugin = ServiceDisruptionScenarioPlugin()

    def test_run_namespace_and_label_conflict(self):
        cfg = {"scenarios": [{"namespace": "ns", "label_selector": "app=foo"}]}
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                ret = self.plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=MagicMock(), scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)

    def test_run_not_enough_namespaces(self):
        cfg = {"scenarios": [{"namespace": "ns", "delete_count": 1}]}
        kubecli = MagicMock()
        kubecli.check_namespaces.return_value = []
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                ret = self.plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)

    def test_run_delete_objects_exception(self):
        cfg = {"scenarios": [{"namespace": "ns", "delete_count": 1}]}
        kubecli = MagicMock()
        kubecli.check_namespaces.return_value = ["ns1"]
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        # make delete_objects raise
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                with patch.object(ServiceDisruptionScenarioPlugin, 'delete_objects', side_effect=Exception("boom")):
                    ret = self.plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)

    def test_run_success_calls_delete_and_publish(self):
        cfg = {"scenarios": [{"namespace": "ns", "delete_count": 1, "sleep": 0}]}
        kubecli = MagicMock()
        kubecli.check_namespaces.return_value = ["ns1"]
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        # delete_objects returns empty dict (successful)
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                with patch.object(ServiceDisruptionScenarioPlugin, 'delete_objects', return_value={} ) as mock_del:
                    with patch("krkn.scenario_plugins.service_disruption.service_disruption_scenario_plugin.cerberus.publish_kraken_status") as mock_pub:
                        ret = self.plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 0)
        mock_del.assert_called()
        mock_pub.assert_called()

    def test_delete_all_helpers_success_and_exception(self):
        plugin = ServiceDisruptionScenarioPlugin()
        kubecli = MagicMock()

        kubecli.get_deployment_ns.return_value = ["d1"]
        res = plugin.delete_all_deployment_namespace(kubecli, "ns")
        self.assertEqual(res, ["d1"])

        kubecli.get_daemonset.return_value = ["dm1"]
        res = plugin.delete_all_daemonset_namespace(kubecli, "ns")
        self.assertEqual(res, ["dm1"])

        kubecli.get_all_statefulset.return_value = ["sfs1"]
        res = plugin.delete_all_statefulsets_namespace(kubecli, "ns")
        self.assertEqual(res, ["sfs1"])

        kubecli.get_all_replicasets.return_value = ["rs1"]
        res = plugin.delete_all_replicaset_namespace(kubecli, "ns")
        self.assertEqual(res, ["rs1"])

        kubecli.get_all_services.return_value = ["svc1"]
        res = plugin.delete_all_services_namespace(kubecli, "ns")
        self.assertEqual(res, ["svc1"])

        # now make one raise
        kubecli2 = MagicMock()
        kubecli2.get_deployment_ns.side_effect = Exception("boom")
        with self.assertRaises(Exception):
            plugin.delete_all_deployment_namespace(kubecli2, "ns")

    def test_get_list_running_pods(self):
        plugin = ServiceDisruptionScenarioPlugin()
        kubecli = MagicMock()
        kubecli.list_pods.return_value = ["p1", "p2"]
        kubecli.get_pod_info.side_effect = [SimpleNamespace(status="Running"), SimpleNamespace(status="Pending")]

        res = plugin.get_list_running_pods(kubecli, "ns")
        self.assertEqual(res, ["p1"])

    def test_check_all_running_deployment_success_and_timeout(self):
        plugin = ServiceDisruptionScenarioPlugin()
        kubecli = MagicMock()

        # success case: objects match immediately
        killed = {"ns": {"deployments": ["d1"]}}
        kubecli.get_deployment_ns.return_value = ["d1"]
        with patch.object(ServiceDisruptionScenarioPlugin, 'check_all_running_pods') as mock_wait:
            res = plugin.check_all_running_deployment(killed.copy(), 30, kubecli)
        self.assertEqual(res, [])

        # timeout case: wait_time = 0 should immediately error and return dict
        killed2 = {"ns": {"deployments": ["d1"]}}
        res2 = plugin.check_all_running_deployment(killed2.copy(), 0, kubecli)
        self.assertEqual(res2, killed2)

    def test_delete_objects_combines_all_helpers(self):
        plugin = ServiceDisruptionScenarioPlugin()
        kubecli = MagicMock()
        kubecli.get_all_services.return_value = ["svc1"]
        kubecli.get_daemonset.return_value = ["dm1"]
        kubecli.get_all_statefulset.return_value = ["sfs1"]
        kubecli.get_all_replicasets.return_value = ["rs1"]
        kubecli.get_deployment_ns.return_value = ["d1"]

        objs = plugin.delete_objects(kubecli, "ns")
        self.assertEqual(objs["services"], ["svc1"])
        self.assertEqual(objs["daemonsets"], ["dm1"])
        self.assertEqual(objs["statefulsets"], ["sfs1"])
        self.assertEqual(objs["replicasets"], ["rs1"])
        self.assertEqual(objs["deployments"], ["d1"])

    def test_delete_helpers_raise(self):
        plugin = ServiceDisruptionScenarioPlugin()
        kubecli = MagicMock()

        kubecli.get_daemonset.side_effect = Exception("boom-dm")
        with self.assertRaises(Exception):
            plugin.delete_all_daemonset_namespace(kubecli, "ns")

        kubecli2 = MagicMock()
        kubecli2.get_all_statefulset.side_effect = Exception("boom-sfs")
        with self.assertRaises(Exception):
            plugin.delete_all_statefulsets_namespace(kubecli2, "ns")

        kubecli3 = MagicMock()
        kubecli3.get_all_replicasets.side_effect = Exception("boom-rs")
        with self.assertRaises(Exception):
            plugin.delete_all_replicaset_namespace(kubecli3, "ns")

        kubecli4 = MagicMock()
        kubecli4.get_all_services.side_effect = Exception("boom-svc")
        with self.assertRaises(Exception):
            plugin.delete_all_services_namespace(kubecli4, "ns")

    def test_check_all_running_pods_waits_and_exits(self):
        plugin = ServiceDisruptionScenarioPlugin()
        kubecli = MagicMock()
        # first call returns Pending, then Running
        kubecli.list_pods.return_value = ["p1"]
        kubecli.get_pod_info.side_effect = [SimpleNamespace(status="Pending", name="p1"), SimpleNamespace(status="Running", name="p1")]

        with patch("time.sleep", return_value=None):
            plugin.check_all_running_pods(kubecli, "ns", 10)

    def test_check_all_running_deployment_all_types(self):
        plugin = ServiceDisruptionScenarioPlugin()
        kubecli = MagicMock()
        killed = {
            "ns": {
                "deployments": ["d1"],
                "replicasets": ["r1"],
                "statefulsets": ["s1"],
                "services": ["svc1"],
                "daemonsets": ["dm1"],
            }
        }

        kubecli.get_deployment_ns.return_value = ["d1"]
        kubecli.get_all_replicasets.return_value = ["r1"]
        kubecli.get_all_statefulset.return_value = ["s1"]
        kubecli.get_all_services.return_value = ["svc1"]
        kubecli.get_daemonset.return_value = ["dm1"]

        with patch("time.sleep", return_value=None):
            res = plugin.check_all_running_deployment(killed.copy(), 30, kubecli)

        self.assertEqual(res, [])

    def test_run_multiple_delete_count_success_and_insufficient(self):
        plugin = ServiceDisruptionScenarioPlugin()
        cfg = {"scenarios": [{"namespace": "ns", "delete_count": 2, "runs": 1, "sleep": 0}]}
        kubecli = MagicMock()
        # two namespaces available
        kubecli.check_namespaces.return_value = ["ns1", "ns2"]
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                with patch.object(ServiceDisruptionScenarioPlugin, 'delete_objects', return_value={}) as mock_del:
                    with patch("krkn.scenario_plugins.service_disruption.service_disruption_scenario_plugin.cerberus.publish_kraken_status"):
                        ret = plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 0)
        self.assertEqual(mock_del.call_count, 2)

        # insufficient namespaces
        kubecli2 = MagicMock()
        kubecli2.check_namespaces.return_value = ["ns1"]
        lib_tel2 = MagicMock()
        lib_tel2.get_lib_kubernetes.return_value = kubecli2
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                ret2 = plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=lib_tel2, scenario_telemetry=MagicMock())

        self.assertEqual(ret2, 1)

    def test_run_logs_wait_between_deletions(self):
        plugin = ServiceDisruptionScenarioPlugin()
        cfg = {"scenarios": [{"namespace": "ns", "delete_count": 1, "sleep": 5}]}
        kubecli = MagicMock()
        kubecli.check_namespaces.return_value = ["ns1"]
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                with patch.object(ServiceDisruptionScenarioPlugin, 'delete_objects', return_value={}) as mock_del:
                    with patch("time.sleep", return_value=None) as mock_sleep:
                        with patch("krkn.scenario_plugins.service_disruption.service_disruption_scenario_plugin.cerberus.publish_kraken_status"):
                            ret = plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 0)
        mock_sleep.assert_called()

    def test_check_all_running_deployment_timeout_logs_error(self):
        plugin = ServiceDisruptionScenarioPlugin()
        kubecli = MagicMock()
        # have lists present but not matching objects to force timeout path
        killed = {"ns": {"deployments": ["d1"]}}
        kubecli.get_deployment_ns.return_value = []

        with patch("time.sleep", return_value=None):
            res = plugin.check_all_running_deployment(killed.copy(), 1, kubecli)

        self.assertEqual(res, killed)


class TestServiceDisruptionScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ServiceDisruptionScenarioPlugin
        """
        self.plugin = ServiceDisruptionScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["service_disruption_scenarios"])
        self.assertEqual(len(result), 1)

if __name__ == "__main__":
    unittest.main()
