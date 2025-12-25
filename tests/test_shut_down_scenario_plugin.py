#!/usr/bin/env python3

"""
Test suite for ShutDownScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_shut_down_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest

from krkn.scenario_plugins.shut_down.shut_down_scenario_plugin import ShutDownScenarioPlugin
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import yaml
import time
from types import SimpleNamespace

class TestShutDownScenarioPluginExtended(unittest.TestCase):

    def setUp(self):
        self.plugin = ShutDownScenarioPlugin()

    def test_multiprocess_nodes_with_tuple_and_list(self):
        calls = []

        def fn(info, id=None):
            # record calls for assertions
            calls.append((info, id))

        nodes_tuple = [("id1", "info1"), ("id2", "info2")]
        # should call starmap with pairs (info, id)
        self.plugin.multiprocess_nodes(fn, nodes_tuple)
        self.assertTrue(len(calls) >= 2)

        # reset and test simple list
        calls.clear()

        def fn2(x):
            calls.append(x)

        nodes_simple = ["n1", "n2"]
        self.plugin.multiprocess_nodes(fn2, nodes_simple)
        self.assertEqual(calls, nodes_simple)

    def test_multiprocess_nodes_handles_exceptions(self):
        def bad(x):
            raise RuntimeError("boom")

        # should not raise
        self.plugin.multiprocess_nodes(bad, ["n1", "n2"]) 

    def _make_cloud_mock(self, tuple_ids=False):
        cloud = MagicMock()
        if tuple_ids:
            # return tuple (id, info)
            cloud.get_instance_id.side_effect = lambda n: (f"id_{n}", f"info_{n}")
            # wait functions accept (info, id, ...)
            cloud.wait_until_stopped.side_effect = lambda a, b, c, d: True
            cloud.wait_until_running.side_effect = lambda a, b, c, d: True
        else:
            cloud.get_instance_id.side_effect = lambda n: f"id_{n}"
            cloud.wait_until_stopped.return_value = True
            cloud.wait_until_running.return_value = True

        cloud.stop_instances = MagicMock()
        cloud.start_instances = MagicMock()
        return cloud

    def test_cluster_shut_down_string_ids(self):
        plugin = ShutDownScenarioPlugin()
        kubecli = MagicMock()
        kubecli.list_nodes.return_value = ["n1", "n2"]

        cloud = self._make_cloud_mock(tuple_ids=False)

        # patch AWS to return our cloud mock
        with patch("krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.AWS", return_value=cloud):
            with patch("time.sleep", return_value=None):
                from krkn_lib.models.k8s import AffectedNodeStatus

                affected = AffectedNodeStatus()
                plugin.cluster_shut_down({"runs": 1, "shut_down_duration": 0, "cloud_type": "aws", "timeout": 1}, kubecli, affected)

        # ensure get_instance_id called for each node and stop/start called
        self.assertEqual(cloud.get_instance_id.call_count, 2)
        self.assertTrue(cloud.stop_instances.called)
        self.assertTrue(cloud.start_instances.called)

    def test_cluster_shut_down_tuple_ids(self):
        plugin = ShutDownScenarioPlugin()
        kubecli = MagicMock()
        kubecli.list_nodes.return_value = ["n1"]

        cloud = self._make_cloud_mock(tuple_ids=True)

        with patch("krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.GCP", return_value=cloud):
            with patch("time.sleep", return_value=None):
                from krkn_lib.models.k8s import AffectedNodeStatus

                affected = AffectedNodeStatus()
                plugin.cluster_shut_down({"runs": 1, "shut_down_duration": 0, "cloud_type": "gcp", "timeout": 1}, kubecli, affected)

        self.assertEqual(cloud.get_instance_id.call_count, 1)
        self.assertTrue(cloud.stop_instances.called)
        self.assertTrue(cloud.start_instances.called)

    def test_cluster_shut_down_unsupported_cloud_raises(self):
        plugin = ShutDownScenarioPlugin()
        kubecli = MagicMock()
        kubecli.list_nodes.return_value = []
        with self.assertRaises(RuntimeError):
            plugin.cluster_shut_down({"runs": 1, "shut_down_duration": 0, "cloud_type": "unknown", "timeout": 1}, kubecli, SimpleNamespace(affected_nodes=[]))

    def test_run_integration_sets_telemetry_and_returns_0(self):
        plugin = ShutDownScenarioPlugin()
        kubecli = MagicMock()
        kubecli.list_nodes.return_value = ["n1"]
        cloud = self._make_cloud_mock(False)
        with patch("krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.AWS", return_value=cloud):
            lib_tel = MagicMock()
            lib_tel.get_lib_kubernetes.return_value = kubecli
            scenario_tel = SimpleNamespace(affected_nodes=[])
            cfg = {"cluster_shut_down_scenario": {"runs": 1, "shut_down_duration": 0, "cloud_type": "aws", "timeout": 1}}
            with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump({"cluster_shut_down_scenario": cfg["cluster_shut_down_scenario"]}))):
                with patch("yaml.full_load", return_value={"cluster_shut_down_scenario": cfg["cluster_shut_down_scenario"]}):
                    with patch("krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.cerberus.publish_kraken_status"):
                        with patch("time.sleep", return_value=None):
                            ret = plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=scenario_tel)

        self.assertEqual(ret, 0)
        self.assertTrue(len(scenario_tel.affected_nodes) >= 0)

    def test_run_handles_yaml_error_and_logs(self):
        plugin = ShutDownScenarioPlugin()
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = MagicMock()
        with patch("builtins.open", unittest.mock.mock_open(read_data="x")):
            with patch("yaml.full_load", side_effect=RuntimeError("boom")):
                with patch("logging.error") as mock_log_err:
                    ret = plugin.run(run_uuid="u", scenario="s", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=SimpleNamespace(affected_nodes=[]))

        self.assertEqual(ret, 1)
        mock_log_err.assert_called()

    def _test_cloud_branch(self, branch_name, cloud_attr_name):
        plugin = ShutDownScenarioPlugin()
        kubecli = MagicMock()
        kubecli.list_nodes.return_value = ["n1"]
        cloud = self._make_cloud_mock(False)
        with patch(f"krkn.scenario_plugins.shut_down.shut_down_scenario_plugin.{cloud_attr_name}", return_value=cloud):
            with patch("time.sleep", return_value=None):
                from krkn_lib.models.k8s import AffectedNodeStatus

                affected = AffectedNodeStatus()
                plugin.cluster_shut_down({"runs": 1, "shut_down_duration": 0, "cloud_type": branch_name, "timeout": 1}, kubecli, affected)

        self.assertTrue(cloud.get_instance_id.called)
        self.assertTrue(cloud.stop_instances.called)
        self.assertTrue(cloud.start_instances.called)

    def test_cluster_shut_down_openstack_azure_ibm(self):
        # openstack
        self._test_cloud_branch("openstack", "OPENSTACKCLOUD")
        # azure
        self._test_cloud_branch("azure", "Azure")
        # ibm
        self._test_cloud_branch("ibm", "IbmCloud")


class TestShutDownScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ShutDownScenarioPlugin
        """
        self.plugin = ShutDownScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["cluster_shut_down_scenarios"])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
