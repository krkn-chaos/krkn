#!/usr/bin/env python3

"""
Test suite for ApplicationOutageScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_application_outage_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import yaml

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.application_outage.application_outage_scenario_plugin import ApplicationOutageScenarioPlugin
class TestApplicationOutageScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for ApplicationOutageScenarioPlugin
        """
        self.plugin = ApplicationOutageScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["application_outages_scenarios"])
        self.assertEqual(len(result), 1)

    def test_build_exclude_expressions_various_formats(self):
        p = ApplicationOutageScenarioPlugin()

        # None -> empty
        self.assertEqual(p._build_exclude_expressions(None), [])

        # dict format
        expr = p._build_exclude_expressions({"tier": "gold", "env": ["prod", "staging"]})
        self.assertEqual(len(expr), 2)
        self.assertTrue(any(e["key"] == "tier" and e["values"] == ["gold"] for e in expr))
        self.assertTrue(any(e["key"] == "env" and e["values"] == ["prod", "staging"] for e in expr))

        # string with comma and pipe
        expr2 = p._build_exclude_expressions("tier=gold,env=prod|staging")
        self.assertEqual(len(expr2), 2)
        self.assertTrue(any(e["key"] == "env" and e["values"] == ["prod", "staging"] for e in expr2))

        # list of strings
        expr3 = p._build_exclude_expressions(["a=b", "c=d"])
        self.assertEqual(len(expr3), 2)

        # invalid entry warns but does not raise and valid entries processed
        with self.assertLogs(level="WARNING") as cm:
            expr4 = p._build_exclude_expressions("badformat,ok=val")
        self.assertIn("invalid", " ".join(cm.output).lower())
        self.assertEqual(len(expr4), 1)

    def test_run_creates_and_deletes_policy(self):
        plugin = ApplicationOutageScenarioPlugin()
        plugin.rollback_handler = MagicMock()

        cfg = {
            "application_outage": {
                "pod_selector": {"app": "myapp"},
                "block": "[Ingress]",
                "namespace": "ns",
                "duration": 0,
                "exclude_label": {"tier": "gold"},
            }
        }

        kubecli = MagicMock()
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        krkn_conf = {"tunings": {"wait_duration": 0}}

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                with patch("krkn.scenario_plugins.application_outage.application_outage_scenario_plugin.get_random_string", return_value="abcde"):
                    with patch("time.sleep", return_value=None):
                        with patch("krkn.scenario_plugins.application_outage.application_outage_scenario_plugin.cerberus.publish_kraken_status"):
                            ret = plugin.run(run_uuid="u", scenario="s", krkn_config=krkn_conf, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 0)
        # policy name should be deterministic
        expected_policy = "krkn-deny-abcde"
        # create and delete called
        self.assertTrue(kubecli.create_net_policy.called)
        kubecli.delete_net_policy.assert_called_with(expected_policy, "ns")
        # rollback callable should be set
        plugin.rollback_handler.set_rollback_callable.assert_called()

    def test_run_create_policy_raises_returns_1(self):
        plugin = ApplicationOutageScenarioPlugin()
        plugin.rollback_handler = MagicMock()

        cfg = {"application_outage": {"pod_selector": {"app": "x"}, "block": "[Ingress]", "namespace": "ns", "duration": 0}}
        kubecli = MagicMock()
        kubecli.create_net_policy.side_effect = Exception("boom")
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli
        krkn_conf = {"tunings": {"wait_duration": 0}}

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                with patch("krkn.scenario_plugins.application_outage.application_outage_scenario_plugin.get_random_string", return_value="abcde"):
                    ret = plugin.run(run_uuid="u", scenario="s", krkn_config=krkn_conf, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)

    def test_rollback_network_policy_success_and_exception(self):
        lib_tel = MagicMock()
        kubecli = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        rb = SimpleNamespace(namespace="ns", resource_identifier="policy1")
        # success path
        ApplicationOutageScenarioPlugin.rollback_network_policy(rb, lib_tel)
        kubecli.delete_net_policy.assert_called_with("policy1", "ns")

        # exception path (should not raise)
        kubecli2 = MagicMock()
        kubecli2.delete_net_policy.side_effect = Exception("fail")
        lib_tel2 = MagicMock()
        lib_tel2.get_lib_kubernetes.return_value = kubecli2
        ApplicationOutageScenarioPlugin.rollback_network_policy(rb, lib_tel2)


if __name__ == "__main__":
    unittest.main()
