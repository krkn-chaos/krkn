#!/usr/bin/env python3

import unittest
from unittest.mock import MagicMock

from krkn.scenario_plugins.network_chaos_ng.models import NetworkFilterConfig
from krkn.scenario_plugins.network_chaos_ng.modules.node_network_filter import (
    NodeNetworkFilterModule,
)


def build_config(**overrides):
    base = dict(
        id="node_network_filter",
        wait_duration=1,
        test_duration=1,
        label_selector="",
        service_account="",
        instance_count=1,
        execution="serial",
        namespace="default",
        taints=[],
        ingress=False,
        egress=True,
        interfaces=[],
        target="node-a",
        ports=[2049],
        image="quay.io/krkn-chaos/krkn-network-chaos:latest",
        protocols=["tcp"],
    )
    base.update(overrides)
    return NetworkFilterConfig(**base)


class TestNodeNetworkFilterModule(unittest.TestCase):
    def setUp(self):
        self.kubecli = MagicMock()
        self.lib_kubernetes = MagicMock()
        self.kubecli.get_lib_kubernetes.return_value = self.lib_kubernetes
        self.lib_kubernetes.list_nodes.return_value = ["node-a", "node-b", "node-c"]

    def test_list_target(self):
        config = build_config(target=["node-a", "node-b"])
        module = NodeNetworkFilterModule(config, self.kubecli)

        targets = module.get_targets()

        self.assertEqual(targets, ["node-a", "node-b"])

    def test_comma_separated_string(self):
        config = build_config(target="node-a, node-b")
        module = NodeNetworkFilterModule(config, self.kubecli)

        targets = module.get_targets()

        self.assertEqual(targets, ["node-a", "node-b"])

    def test_wildcard_string(self):
        config = build_config(target="node-*")
        module = NodeNetworkFilterModule(config, self.kubecli)

        targets = module.get_targets()

        self.assertEqual(targets, ["node-a", "node-b", "node-c"])

    def test_regex_string(self):
        config = build_config(target="regex:node-[ab]")
        module = NodeNetworkFilterModule(config, self.kubecli)

        targets = module.get_targets()

        self.assertEqual(targets, ["node-a", "node-b"])

    def test_missing_node_raises(self):
        config = build_config(target=["node-x"])
        module = NodeNetworkFilterModule(config, self.kubecli)

        with self.assertRaises(Exception):
            module.get_targets()


if __name__ == "__main__":
    unittest.main()

