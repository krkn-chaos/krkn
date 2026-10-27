#!/usr/bin/env python3

"""
Test suite for ApplicationOutageScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_application_outage_scenario_plugin.py -v

Assisted By: Claude Code
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

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

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["application_outages_scenarios"])
        self.assertEqual(len(result), 1)

    def _rendered_policy(self, exclude_label=None, raw_yaml=None):
        """Run the scenario with a mocked cluster and return the NetworkPolicy spec sent to the API."""
        config = {
            "application_outage": {
                "duration": 0,
                "namespace": "test-ns",
                "pod_selector": {"app": "foo"},
                "block": ["Ingress"],
                "exclude_label": exclude_label,
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "app_outage.yaml")
            with open(path, "w") as f:
                if raw_yaml is not None:
                    f.write(raw_yaml)
                else:
                    yaml.safe_dump(config, f)
            lib_telemetry = MagicMock(spec=KrknTelemetryOpenshift)
            kubecli = MagicMock(spec=KrknKubernetes)
            lib_telemetry.get_lib_kubernetes.return_value = kubecli
            self.plugin.rollback_handler = MagicMock()
            with patch("time.sleep"):
                result = self.plugin.run("test-uuid", path, lib_telemetry, MagicMock())
        self.assertEqual(result, 0)
        return kubecli.create_net_policy.call_args[0][0]

    def test_exclude_label_values_stay_strings(self):
        """
        NetworkPolicy matchExpressions values must be strings. Label values that
        look like YAML booleans or numbers ("true", "on", "1.0") must not be
        turned into bool/float when the policy template is rendered.
        """
        for exclude_label in (
            {"critical": "true", "version": "1.0"},
            "critical=true,version=1.0",
            ["critical=true", "version=1.0"],
        ):
            with self.subTest(exclude_label=exclude_label):
                spec = self._rendered_policy(exclude_label)
                expressions = spec["spec"]["podSelector"]["matchExpressions"]
                values = {e["key"]: e["values"] for e in expressions}
                self.assertEqual(values, {"critical": ["true"], "version": ["1.0"]})

    def test_exclude_label_yes_no_on_off_values_stay_strings(self):
        spec = self._rendered_policy("tier=on|off|yes|no")
        expressions = spec["spec"]["podSelector"]["matchExpressions"]
        self.assertEqual(expressions[0]["values"], ["on", "off", "yes", "no"])

    def test_exclude_label_policy_shape(self):
        """
        The excluded labels must be NotIn expressions next to the pod_selector
        matchLabels, and only the blocked direction is listed in policyTypes
        """
        spec = self._rendered_policy({"critical": "true"})["spec"]
        self.assertEqual(
            spec["podSelector"],
            {
                "matchLabels": {"app": "foo"},
                "matchExpressions": [
                    {"key": "critical", "operator": "NotIn", "values": ["true"]}
                ],
            },
        )
        self.assertEqual(spec["policyTypes"], ["Ingress"])

    def test_exclude_label_keys_stay_strings(self):
        """Label keys like "true" or "1.0" are valid and must stay strings."""
        spec = self._rendered_policy({"true": "x", "1.0": "y"})
        keys = [e["key"] for e in spec["spec"]["podSelector"]["matchExpressions"]]
        self.assertCountEqual(keys, ["true", "1.0"])

    def test_exclude_label_unquoted_booleans_in_scenario_file(self):
        """
        `critical: true` written unquoted in the scenario file is loaded as a
        bool; it must still match pods labelled "true", not "True"
        """
        raw_yaml = (
            "application_outage:\n"
            "  duration: 0\n"
            "  namespace: test-ns\n"
            "  pod_selector: {app: foo}\n"
            "  block: [Ingress]\n"
            "  exclude_label: {critical: true, debug: false}\n"
        )
        spec = self._rendered_policy(raw_yaml=raw_yaml)
        expressions = spec["spec"]["podSelector"]["matchExpressions"]
        values = {e["key"]: e["values"] for e in expressions}
        self.assertEqual(values, {"critical": ["true"], "debug": ["false"]})

    def test_exclude_label_unquoted_boolean_keys_in_scenario_file(self):
        """
        Label keys written unquoted as true/false in the scenario file load
        as bools; they must reach the policy as "true"/"false"
        """
        raw_yaml = (
            "application_outage:\n"
            "  duration: 0\n"
            "  namespace: test-ns\n"
            "  pod_selector: {app: foo}\n"
            "  block: [Ingress]\n"
            "  exclude_label: {true: x, false: y}\n"
        )
        spec = self._rendered_policy(raw_yaml=raw_yaml)
        expressions = spec["spec"]["podSelector"]["matchExpressions"]
        values = {e["key"]: e["values"] for e in expressions}
        self.assertEqual(values, {"true": ["x"], "false": ["y"]})


if __name__ == "__main__":
    unittest.main()
