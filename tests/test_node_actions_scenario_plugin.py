#!/usr/bin/env python3

"""
Test suite for NodeActionsScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_node_actions_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, Mock, patch, mock_open, call
import yaml
import tempfile
import os

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.models.k8s import AffectedNodeStatus

from krkn.scenario_plugins.node_actions.node_actions_scenario_plugin import NodeActionsScenarioPlugin


class TestNodeActionsScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for NodeActionsScenarioPlugin
        """
        # Reset node_general global variable before each test
        import krkn.scenario_plugins.node_actions.node_actions_scenario_plugin as plugin_module
        plugin_module.node_general = False

        self.plugin = NodeActionsScenarioPlugin()
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

        self.assertEqual(result, ["node_scenarios"])
        self.assertEqual(len(result), 1)

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.general_node_scenarios')
    def test_get_node_scenario_object_generic(self, mock_general_scenarios):
        """
        Test get_node_scenario_object returns general_node_scenarios for generic cloud type
        """
        node_scenario = {"cloud_type": "generic"}
        mock_general_instance = Mock()
        mock_general_scenarios.return_value = mock_general_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_general_instance)
        mock_general_scenarios.assert_called_once()
        args = mock_general_scenarios.call_args[0]
        self.assertEqual(args[0], self.mock_kubecli)
        self.assertTrue(args[1])  # node_action_kube_check defaults to True
        self.assertIsInstance(args[2], AffectedNodeStatus)

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.general_node_scenarios')
    def test_get_node_scenario_object_no_cloud_type(self, mock_general_scenarios):
        """
        Test get_node_scenario_object returns general_node_scenarios when cloud_type is not specified
        """
        node_scenario = {}
        mock_general_instance = Mock()
        mock_general_scenarios.return_value = mock_general_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_general_instance)
        mock_general_scenarios.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.aws_node_scenarios')
    def test_get_node_scenario_object_aws(self, mock_aws_scenarios):
        """
        Test get_node_scenario_object returns aws_node_scenarios for AWS cloud type
        """
        node_scenario = {"cloud_type": "aws"}
        mock_aws_instance = Mock()
        mock_aws_scenarios.return_value = mock_aws_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_aws_instance)
        mock_aws_scenarios.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.gcp_node_scenarios')
    def test_get_node_scenario_object_gcp(self, mock_gcp_scenarios):
        """
        Test get_node_scenario_object returns gcp_node_scenarios for GCP cloud type
        """
        node_scenario = {"cloud_type": "gcp"}
        mock_gcp_instance = Mock()
        mock_gcp_scenarios.return_value = mock_gcp_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_gcp_instance)
        mock_gcp_scenarios.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.azure_node_scenarios')
    def test_get_node_scenario_object_azure(self, mock_azure_scenarios):
        """
        Test get_node_scenario_object returns azure_node_scenarios for Azure cloud type
        """
        node_scenario = {"cloud_type": "azure"}
        mock_azure_instance = Mock()
        mock_azure_scenarios.return_value = mock_azure_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_azure_instance)
        mock_azure_scenarios.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.azure_node_scenarios')
    def test_get_node_scenario_object_az(self, mock_azure_scenarios):
        """
        Test get_node_scenario_object returns azure_node_scenarios for 'az' cloud type alias
        """
        node_scenario = {"cloud_type": "az"}
        mock_azure_instance = Mock()
        mock_azure_scenarios.return_value = mock_azure_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_azure_instance)
        mock_azure_scenarios.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.docker_node_scenarios')
    def test_get_node_scenario_object_docker(self, mock_docker_scenarios):
        """
        Test get_node_scenario_object returns docker_node_scenarios for Docker cloud type
        """
        node_scenario = {"cloud_type": "docker"}
        mock_docker_instance = Mock()
        mock_docker_scenarios.return_value = mock_docker_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_docker_instance)
        mock_docker_scenarios.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.vmware_node_scenarios')
    def test_get_node_scenario_object_vmware(self, mock_vmware_scenarios):
        """
        Test get_node_scenario_object returns vmware_node_scenarios for VMware cloud type
        """
        node_scenario = {"cloud_type": "vmware"}
        mock_vmware_instance = Mock()
        mock_vmware_scenarios.return_value = mock_vmware_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_vmware_instance)
        mock_vmware_scenarios.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.vmware_node_scenarios')
    def test_get_node_scenario_object_vsphere(self, mock_vmware_scenarios):
        """
        Test get_node_scenario_object returns vmware_node_scenarios for vSphere cloud type alias
        """
        node_scenario = {"cloud_type": "vsphere"}
        mock_vmware_instance = Mock()
        mock_vmware_scenarios.return_value = mock_vmware_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_vmware_instance)
        mock_vmware_scenarios.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.ibm_node_scenarios')
    def test_get_node_scenario_object_ibm(self, mock_ibm_scenarios):
        """
        Test get_node_scenario_object returns ibm_node_scenarios for IBM cloud type
        """
        node_scenario = {"cloud_type": "ibm"}
        mock_ibm_instance = Mock()
        mock_ibm_scenarios.return_value = mock_ibm_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_ibm_instance)
        mock_ibm_scenarios.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.ibm_node_scenarios')
    def test_get_node_scenario_object_ibmcloud(self, mock_ibm_scenarios):
        """
        Test get_node_scenario_object returns ibm_node_scenarios for ibmcloud cloud type alias
        """
        node_scenario = {"cloud_type": "ibmcloud", "disable_ssl_verification": False}
        mock_ibm_instance = Mock()
        mock_ibm_scenarios.return_value = mock_ibm_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_ibm_instance)
        args = mock_ibm_scenarios.call_args[0]
        self.assertFalse(args[3])  # disable_ssl_verification should be False

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.ibmcloud_power_node_scenarios')
    def test_get_node_scenario_object_ibmpower(self, mock_ibmpower_scenarios):
        """
        Test get_node_scenario_object returns ibmcloud_power_node_scenarios for ibmpower cloud type
        """
        node_scenario = {"cloud_type": "ibmpower"}
        mock_ibmpower_instance = Mock()
        mock_ibmpower_scenarios.return_value = mock_ibmpower_instance

        result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertEqual(result, mock_ibmpower_instance)
        mock_ibmpower_scenarios.assert_called_once()

    def test_get_node_scenario_object_openstack(self):
        """
        Test get_node_scenario_object returns openstack_node_scenarios for OpenStack cloud type
        """
        with patch('krkn.scenario_plugins.node_actions.openstack_node_scenarios.openstack_node_scenarios') as mock_openstack:
            node_scenario = {"cloud_type": "openstack"}
            mock_openstack_instance = Mock()
            mock_openstack.return_value = mock_openstack_instance

            result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

            self.assertEqual(result, mock_openstack_instance)
            mock_openstack.assert_called_once()

    def test_get_node_scenario_object_alibaba(self):
        """
        Test get_node_scenario_object returns alibaba_node_scenarios for Alibaba cloud type
        """
        with patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.alibaba_node_scenarios') as mock_alibaba:
            node_scenario = {"cloud_type": "alibaba"}
            mock_alibaba_instance = Mock()
            mock_alibaba.return_value = mock_alibaba_instance

            result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

            self.assertEqual(result, mock_alibaba_instance)
            mock_alibaba.assert_called_once()

    def test_get_node_scenario_object_alicloud(self):
        """
        Test get_node_scenario_object returns alibaba_node_scenarios for alicloud alias
        """
        with patch('krkn.scenario_plugins.node_actions.alibaba_node_scenarios.alibaba_node_scenarios') as mock_alibaba:
            node_scenario = {"cloud_type": "alicloud"}
            mock_alibaba_instance = Mock()
            mock_alibaba.return_value = mock_alibaba_instance

            result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

            self.assertEqual(result, mock_alibaba_instance)
            mock_alibaba.assert_called_once()

    def test_get_node_scenario_object_bm(self):
        """
        Test get_node_scenario_object returns bm_node_scenarios for bare metal cloud type
        """
        with patch('krkn.scenario_plugins.node_actions.bm_node_scenarios.bm_node_scenarios') as mock_bm:
            node_scenario = {
                "cloud_type": "bm",
                "bmc_info": "192.168.1.1",
                "bmc_user": "admin",
                "bmc_password": "password"
            }
            mock_bm_instance = Mock()
            mock_bm.return_value = mock_bm_instance

            result = self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

            self.assertEqual(result, mock_bm_instance)
            args = mock_bm.call_args[0]
            self.assertEqual(args[0], "192.168.1.1")
            self.assertEqual(args[1], "admin")
            self.assertEqual(args[2], "password")

    def test_get_node_scenario_object_unsupported_cloud(self):
        """
        Test get_node_scenario_object raises exception for unsupported cloud type
        """
        node_scenario = {"cloud_type": "unsupported_cloud"}

        with self.assertRaises(Exception) as context:
            self.plugin.get_node_scenario_object(node_scenario, self.mock_kubecli)

        self.assertIn("not currently supported", str(context.exception))
        self.assertIn("unsupported_cloud", str(context.exception))

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.common_node_functions')
    def test_inject_node_scenario_with_node_name(self, mock_common_funcs):
        """
        Test inject_node_scenario with specific node name
        """
        node_scenario = {
            "node_name": "node1,node2",
            "instance_count": 2,
            "runs": 1,
            "timeout": 120,
            "duration": 60,
            "poll_interval": 15
        }
        action = "node_stop_start_scenario"
        mock_scenario_object = Mock()
        mock_scenario_object.affected_nodes_status = AffectedNodeStatus()
        mock_scenario_object.affected_nodes_status.affected_nodes = []

        mock_common_funcs.get_node_by_name.return_value = ["node1", "node2"]

        self.plugin.inject_node_scenario(
            action,
            node_scenario,
            mock_scenario_object,
            self.mock_kubecli,
            self.mock_scenario_telemetry
        )

        mock_common_funcs.get_node_by_name.assert_called_once_with(["node1", "node2"], self.mock_kubecli)
        self.assertEqual(mock_scenario_object.node_stop_start_scenario.call_count, 2)

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.common_node_functions')
    def test_inject_node_scenario_with_label_selector(self, mock_common_funcs):
        """
        Test inject_node_scenario with label selector
        """
        node_scenario = {
            "label_selector": "node-role.kubernetes.io/worker",
            "instance_count": 1
        }
        action = "node_reboot_scenario"
        mock_scenario_object = Mock()
        mock_scenario_object.affected_nodes_status = AffectedNodeStatus()
        mock_scenario_object.affected_nodes_status.affected_nodes = []

        mock_common_funcs.get_node.return_value = ["worker-node-1"]

        self.plugin.inject_node_scenario(
            action,
            node_scenario,
            mock_scenario_object,
            self.mock_kubecli,
            self.mock_scenario_telemetry
        )

        mock_common_funcs.get_node.assert_called_once_with("node-role.kubernetes.io/worker", 1, self.mock_kubecli)
        mock_scenario_object.node_reboot_scenario.assert_called_once()

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.common_node_functions')
    def test_inject_node_scenario_with_exclude_label(self, mock_common_funcs):
        """
        Test inject_node_scenario with exclude label
        """
        node_scenario = {
            "label_selector": "node-role.kubernetes.io/worker",
            "exclude_label": "node-role.kubernetes.io/master",
            "instance_count": 2
        }
        action = "node_stop_scenario"
        mock_scenario_object = Mock()
        mock_scenario_object.affected_nodes_status = AffectedNodeStatus()
        mock_scenario_object.affected_nodes_status.affected_nodes = []

        mock_common_funcs.get_node.side_effect = [
            ["worker-1", "master-1"],
            ["master-1"]
        ]

        self.plugin.inject_node_scenario(
            action,
            node_scenario,
            mock_scenario_object,
            self.mock_kubecli,
            self.mock_scenario_telemetry
        )

        self.assertEqual(mock_common_funcs.get_node.call_count, 2)
        # Should only process worker-1 after excluding master-1
        self.assertEqual(mock_scenario_object.node_stop_scenario.call_count, 1)

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.common_node_functions')
    def test_inject_node_scenario_parallel_mode(self, mock_common_funcs):
        """
        Test inject_node_scenario with parallel processing
        """
        node_scenario = {
            "node_name": "node1,node2,node3",
            "parallel": True
        }
        action = "restart_kubelet_scenario"
        mock_scenario_object = Mock()
        mock_scenario_object.affected_nodes_status = AffectedNodeStatus()
        mock_scenario_object.affected_nodes_status.affected_nodes = []

        mock_common_funcs.get_node_by_name.return_value = ["node1", "node2", "node3"]

        with patch.object(self.plugin, 'multiprocess_nodes') as mock_multiprocess:
            self.plugin.inject_node_scenario(
                action,
                node_scenario,
                mock_scenario_object,
                self.mock_kubecli,
                self.mock_scenario_telemetry
            )

            mock_multiprocess.assert_called_once()
            args = mock_multiprocess.call_args[0]
            self.assertEqual(args[0], ["node1", "node2", "node3"])
            self.assertEqual(args[2], action)

    def test_run_node_node_start_scenario(self):
        """
        Test run_node executes node_start_scenario action
        """
        node_scenario = {"runs": 2, "timeout": 300, "poll_interval": 10}
        action = "node_start_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.node_start_scenario.assert_called_once_with(2, "test-node", 300, 10)

    def test_run_node_node_stop_scenario(self):
        """
        Test run_node executes node_stop_scenario action
        """
        node_scenario = {"runs": 1, "timeout": 120, "poll_interval": 15}
        action = "node_stop_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.node_stop_scenario.assert_called_once_with(1, "test-node", 120, 15)

    def test_run_node_node_stop_start_scenario(self):
        """
        Test run_node executes node_stop_start_scenario action
        """
        node_scenario = {"runs": 1, "timeout": 120, "duration": 60, "poll_interval": 15}
        action = "node_stop_start_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.node_stop_start_scenario.assert_called_once_with(1, "test-node", 120, 60, 15)

    def test_run_node_node_termination_scenario(self):
        """
        Test run_node executes node_termination_scenario action
        """
        node_scenario = {}
        action = "node_termination_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.node_termination_scenario.assert_called_once_with(1, "test-node", 120, 15)

    def test_run_node_node_reboot_scenario(self):
        """
        Test run_node executes node_reboot_scenario action
        """
        node_scenario = {"soft_reboot": True}
        action = "node_reboot_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.node_reboot_scenario.assert_called_once_with(1, "test-node", 120, True)

    def test_run_node_node_disk_detach_attach_scenario(self):
        """
        Test run_node executes node_disk_detach_attach_scenario action
        """
        node_scenario = {"duration": 90}
        action = "node_disk_detach_attach_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.node_disk_detach_attach_scenario.assert_called_once_with(1, "test-node", 120, 90)

    def test_run_node_stop_start_kubelet_scenario(self):
        """
        Test run_node executes stop_start_kubelet_scenario action
        """
        node_scenario = {}
        action = "stop_start_kubelet_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.stop_start_kubelet_scenario.assert_called_once_with(1, "test-node", 120)

    def test_run_node_restart_kubelet_scenario(self):
        """
        Test run_node executes restart_kubelet_scenario action
        """
        node_scenario = {}
        action = "restart_kubelet_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.restart_kubelet_scenario.assert_called_once_with(1, "test-node", 120)

    def test_run_node_stop_kubelet_scenario(self):
        """
        Test run_node executes stop_kubelet_scenario action
        """
        node_scenario = {}
        action = "stop_kubelet_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.stop_kubelet_scenario.assert_called_once_with(1, "test-node", 120)

    def test_run_node_node_crash_scenario(self):
        """
        Test run_node executes node_crash_scenario action
        """
        node_scenario = {}
        action = "node_crash_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.node_crash_scenario.assert_called_once_with(1, "test-node", 120)

    def test_run_node_node_block_scenario(self):
        """
        Test run_node executes node_block_scenario action
        """
        node_scenario = {"duration": 100}
        action = "node_block_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.node_block_scenario.assert_called_once_with(1, "test-node", 120, 100)

    @patch('logging.info')
    def test_run_node_stop_start_helper_node_scenario_openstack(self, mock_logging):
        """
        Test run_node executes stop_start_helper_node_scenario for OpenStack
        """
        node_scenario = {
            "cloud_type": "openstack",
            "helper_node_ip": "192.168.1.100",
            "service": "neutron-server"
        }
        action = "stop_start_helper_node_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_scenario_object.helper_node_stop_start_scenario.assert_called_once_with(1, "192.168.1.100", 120)
        mock_scenario_object.helper_node_service_status.assert_called_once()

    @patch('logging.error')
    def test_run_node_stop_start_helper_node_scenario_non_openstack(self, mock_logging):
        """
        Test run_node logs error for stop_start_helper_node_scenario on non-OpenStack
        """
        node_scenario = {
            "cloud_type": "aws",
            "helper_node_ip": "192.168.1.100"
        }
        action = "stop_start_helper_node_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_logging.assert_called()
        self.assertIn("not supported", str(mock_logging.call_args))

    @patch('logging.error')
    def test_run_node_stop_start_helper_node_scenario_missing_ip(self, mock_logging):
        """
        Test run_node raises exception when helper_node_ip is missing
        """
        node_scenario = {
            "cloud_type": "openstack",
            "helper_node_ip": None
        }
        action = "stop_start_helper_node_scenario"
        mock_scenario_object = Mock()

        with self.assertRaises(Exception) as context:
            self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        self.assertIn("Helper node IP address is not provided", str(context.exception))

    @patch('logging.info')
    def test_run_node_generic_cloud_skip_unsupported_action(self, mock_logging):
        """
        Test run_node skips unsupported actions for generic cloud type
        """
        # Set node_general to True for this test
        import krkn.scenario_plugins.node_actions.node_actions_scenario_plugin as plugin_module
        plugin_module.node_general = True

        node_scenario = {}
        action = "node_stop_scenario"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_logging.assert_called()
        self.assertIn("not set up for generic cloud type", str(mock_logging.call_args))

    @patch('logging.info')
    def test_run_node_unknown_action(self, mock_logging):
        """
        Test run_node logs info for unknown action
        """
        node_scenario = {}
        action = "unknown_action"
        mock_scenario_object = Mock()

        self.plugin.run_node("test-node", mock_scenario_object, action, node_scenario)

        mock_logging.assert_called()
        # Could be either message depending on node_general state
        call_str = str(mock_logging.call_args)
        self.assertTrue(
            "no node action that matches" in call_str or
            "not set up for generic cloud type" in call_str
        )

    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.cerberus')
    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.common_node_functions')
    @patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.general_node_scenarios')
    @patch('builtins.open', new_callable=mock_open)
    @patch('time.time')
    def test_run_successful(self, mock_time, mock_file, mock_general_scenarios, mock_common_funcs, mock_cerberus):
        """
        Test successful run of node actions scenario
        """
        scenario_yaml = {
            "node_scenarios": [
                {
                    "cloud_type": "generic",
                    "node_name": "test-node",
                    "actions": ["stop_kubelet_scenario"]
                }
            ]
        }

        mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(scenario_yaml)
        mock_time.side_effect = [1000, 1100]
        mock_scenario_object = Mock()
        mock_scenario_object.affected_nodes_status = AffectedNodeStatus()
        mock_scenario_object.affected_nodes_status.affected_nodes = []
        mock_general_scenarios.return_value = mock_scenario_object
        mock_common_funcs.get_node_by_name.return_value = ["test-node"]
        mock_cerberus.get_status.return_value = None

        with patch('yaml.full_load', return_value=scenario_yaml):
            result = self.plugin.run(
                "test-uuid",
                "/path/to/scenario.yaml",
                {},
                self.mock_lib_telemetry,
                self.mock_scenario_telemetry
            )

        self.assertEqual(result, 0)
        mock_cerberus.get_status.assert_called_once_with({}, 1000, 1100)

    @patch('logging.error')
    @patch('builtins.open', new_callable=mock_open)
    def test_run_with_exception(self, mock_file, mock_logging):
        """
        Test run handles exceptions and returns 1
        """
        scenario_yaml = {
            "node_scenarios": [
                {
                    "cloud_type": "unsupported"
                }
            ]
        }

        with patch('yaml.full_load', return_value=scenario_yaml):
            result = self.plugin.run(
                "test-uuid",
                "/path/to/scenario.yaml",
                {},
                self.mock_lib_telemetry,
                self.mock_scenario_telemetry
            )

        self.assertEqual(result, 1)
        mock_logging.assert_called()

    @patch('logging.info')
    def test_multiprocess_nodes(self, mock_logging):
        """
        Test multiprocess_nodes executes run_node for multiple nodes in parallel
        """
        nodes = ["node1", "node2", "node3"]
        mock_scenario_object = Mock()
        action = "restart_kubelet_scenario"
        node_scenario = {}

        with patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.ThreadPool') as mock_pool:
            mock_pool_instance = Mock()
            mock_pool.return_value = mock_pool_instance

            self.plugin.multiprocess_nodes(nodes, mock_scenario_object, action, node_scenario)

            mock_pool.assert_called_once_with(processes=3)
            mock_pool_instance.starmap.assert_called_once()
            mock_pool_instance.close.assert_called_once()

    @patch('logging.info')
    def test_multiprocess_nodes_with_exception(self, mock_logging):
        """
        Test multiprocess_nodes handles exceptions gracefully
        """
        nodes = ["node1", "node2"]
        mock_scenario_object = Mock()
        action = "node_reboot_scenario"
        node_scenario = {}

        with patch('krkn.scenario_plugins.node_actions.node_actions_scenario_plugin.ThreadPool') as mock_pool:
            mock_pool.side_effect = Exception("Pool error")

            self.plugin.multiprocess_nodes(nodes, mock_scenario_object, action, node_scenario)

            mock_logging.assert_called()
            self.assertIn("Error on pool multiprocessing", str(mock_logging.call_args))


if __name__ == "__main__":
    unittest.main()
