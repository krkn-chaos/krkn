#!/usr/bin/env python3

"""
Test suite for baremetal node scenarios

Covers BM and bm_node_scenarios using mocks to avoid actual IPMI/OpenShift calls.

Usage:
    python -m coverage run -a -m unittest tests/test_bm_node_scenarios.py -v

Assisted By: Claude Code
"""

import unittest
import sys
from unittest.mock import MagicMock, patch

# Mock external dependencies before any imports that use them
sys.modules["openshift"] = MagicMock()
sys.modules["paramiko"] = MagicMock()
sys.modules["pyipmi"] = MagicMock()
sys.modules["pyipmi.interfaces"] = MagicMock()

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus
from krkn.scenario_plugins.node_actions.bm_node_scenarios import BM, bm_node_scenarios


class TestBM(unittest.TestCase):
    """Test cases for the BM helper class"""

    def setUp(self):
        self.bm_info = {
            "node1": {
                "bmc_addr": "ipmi://192.168.1.100",
                "bmc_user": "admin",
                "bmc_password": "secret",
                "disks": ["sdb", "sdc"],
            }
        }
        self.bm = BM(self.bm_info, user="global_user", passwd="global_pass")

    def test_init(self):
        bm = BM({"k": "v"}, "user", "pass")
        self.assertEqual(bm.user, "user")
        self.assertEqual(bm.passwd, "pass")
        self.assertEqual(bm.bm_info, {"k": "v"})

    # --- get_bm_disks ---

    def test_get_bm_disks_returns_configured_disks(self):
        self.assertEqual(self.bm.get_bm_disks("node1"), ["sdb", "sdc"])

    def test_get_bm_disks_returns_empty_when_node_missing(self):
        self.assertEqual(self.bm.get_bm_disks("unknown_node"), [])

    def test_get_bm_disks_returns_empty_when_no_disks_key(self):
        bm = BM({"node1": {"bmc_addr": "ipmi://host"}}, "user", "pass")
        self.assertEqual(bm.get_bm_disks("node1"), [])

    def test_get_bm_disks_returns_empty_when_bm_info_is_none(self):
        bm = BM(None, "user", "pass")
        self.assertEqual(bm.get_bm_disks("node1"), [])

    # --- get_bmc_addr ---

    def test_get_bmc_addr_returns_config_address(self):
        self.assertEqual(self.bm.get_bmc_addr("node1"), "ipmi://192.168.1.100")

    @patch("krkn.scenario_plugins.node_actions.bm_node_scenarios.oc")
    def test_get_bmc_addr_fetches_from_bmh_when_not_in_config(self, mock_oc):
        bm = BM({}, "user", "pass")

        mock_node_obj = MagicMock()
        mock_node_obj.model.spec.providerID = "openstack://region/bmh-name/uid123"

        mock_bmh_obj = MagicMock()
        mock_bmh_obj.model.spec.bmc.addr = "192.168.1.200"
        mock_bmh_obj.model.spec.bmc.address = "192.168.1.200"

        def selector_side_effect(selector_str):
            mock_sel = MagicMock()
            if selector_str.startswith("node/"):
                mock_sel.object.return_value = mock_node_obj
            else:
                mock_sel.object.return_value = mock_bmh_obj
            return mock_sel

        mock_oc.selector.side_effect = selector_side_effect

        result = bm.get_bmc_addr("node1")
        self.assertEqual(result, "192.168.1.200")

    @patch("krkn.scenario_plugins.node_actions.bm_node_scenarios.oc")
    def test_get_bmc_addr_raises_when_bmc_addr_empty(self, mock_oc):
        bm = BM({}, "user", "pass")

        mock_node_obj = MagicMock()
        mock_node_obj.model.spec.providerID = "openstack://region/bmh-name/uid123"

        mock_bmh_obj = MagicMock()
        mock_bmh_obj.model.spec.bmc.addr = ""  # empty triggers the error
        mock_bmh_obj.model.spec.bmc.address = ""

        def selector_side_effect(selector_str):
            mock_sel = MagicMock()
            if selector_str.startswith("node/"):
                mock_sel.object.return_value = mock_node_obj
            else:
                mock_sel.object.return_value = mock_bmh_obj
            return mock_sel

        mock_oc.selector.side_effect = selector_side_effect

        with self.assertRaises(RuntimeError):
            bm.get_bmc_addr("node1")

    # --- get_ipmi_connection ---

    @patch("krkn.scenario_plugins.node_actions.bm_node_scenarios.pyipmi")
    def test_get_ipmi_connection_plain_host_uses_default_port(self, mock_pyipmi):
        mock_connection = MagicMock()
        mock_pyipmi.create_connection.return_value = mock_connection

        result = self.bm.get_ipmi_connection("192.168.1.100", "node1")

        self.assertEqual(result, mock_connection)
        mock_connection.session.set_session_type_rmcp.assert_called_once_with(
            "192.168.1.100", 623
        )

    @patch("krkn.scenario_plugins.node_actions.bm_node_scenarios.pyipmi")
    def test_get_ipmi_connection_parses_host_with_port(self, mock_pyipmi):
        mock_connection = MagicMock()
        mock_pyipmi.create_connection.return_value = mock_connection

        self.bm.get_ipmi_connection("192.168.1.100:6623", "node1")

        mock_connection.session.set_session_type_rmcp.assert_called_once_with(
            "192.168.1.100", 6623
        )

    @patch("krkn.scenario_plugins.node_actions.bm_node_scenarios.pyipmi")
    def test_get_ipmi_connection_strips_protocol(self, mock_pyipmi):
        mock_connection = MagicMock()
        mock_pyipmi.create_connection.return_value = mock_connection

        self.bm.get_ipmi_connection("ipmi://192.168.1.100:623", "node1")

        mock_connection.session.set_session_type_rmcp.assert_called_once_with(
            "192.168.1.100", 623
        )

    @patch("krkn.scenario_plugins.node_actions.bm_node_scenarios.pyipmi")
    def test_get_ipmi_connection_uses_device_specific_credentials(self, mock_pyipmi):
        mock_connection = MagicMock()
        mock_pyipmi.create_connection.return_value = mock_connection

        self.bm.get_ipmi_connection("192.168.1.100", "node1")

        mock_connection.session.set_auth_type_user.assert_called_once_with(
            "admin", "secret"
        )

    @patch("krkn.scenario_plugins.node_actions.bm_node_scenarios.pyipmi")
    def test_get_ipmi_connection_falls_back_to_global_credentials(self, mock_pyipmi):
        bm = BM({}, "global_user", "global_pass")
        mock_connection = MagicMock()
        mock_pyipmi.create_connection.return_value = mock_connection

        bm.get_ipmi_connection("192.168.1.100", "unknown_node")

        mock_connection.session.set_auth_type_user.assert_called_once_with(
            "global_user", "global_pass"
        )

    def test_get_ipmi_connection_raises_when_credentials_are_none(self):
        bm = BM({}, None, None)
        with self.assertRaises(RuntimeError):
            bm.get_ipmi_connection("192.168.1.100", "node1")

    def test_get_ipmi_connection_raises_when_user_is_none(self):
        bm = BM({}, None, "somepassword")
        with self.assertRaises(RuntimeError):
            bm.get_ipmi_connection("192.168.1.100", "node1")

    def test_get_ipmi_connection_raises_when_password_is_none(self):
        bm = BM({}, "someuser", None)
        with self.assertRaises(RuntimeError):
            bm.get_ipmi_connection("192.168.1.100", "node1")

    # --- start / stop / reboot ---

    def test_start_instances_calls_power_up(self):
        mock_conn = MagicMock()
        self.bm.get_ipmi_connection = MagicMock(return_value=mock_conn)

        self.bm.start_instances("192.168.1.100", "node1")

        mock_conn.chassis_control_power_up.assert_called_once()

    def test_stop_instances_calls_power_down(self):
        mock_conn = MagicMock()
        self.bm.get_ipmi_connection = MagicMock(return_value=mock_conn)

        self.bm.stop_instances("192.168.1.100", "node1")

        mock_conn.chassis_control_power_down.assert_called_once()

    def test_reboot_instances_calls_power_cycle(self):
        mock_conn = MagicMock()
        self.bm.get_ipmi_connection = MagicMock(return_value=mock_conn)

        self.bm.reboot_instances("192.168.1.100", "node1")

        mock_conn.chassis_control_power_cycle.assert_called_once()

    # --- wait_until_running ---

    @patch("time.time")
    @patch("time.sleep")
    def test_wait_until_running_updates_affected_node(self, _mock_sleep, mock_time):
        mock_time.side_effect = [100.0, 115.0]
        mock_conn = MagicMock()
        mock_conn.get_chassis_status.return_value.power_on = True  # already on, loop skipped
        self.bm.get_ipmi_connection = MagicMock(return_value=mock_conn)

        affected_node = MagicMock(spec=AffectedNode)
        self.bm.wait_until_running("192.168.1.100", "node1", affected_node)

        affected_node.set_affected_node_status.assert_called_once_with("running", 15.0)

    @patch("time.time")
    @patch("time.sleep")
    def test_wait_until_running_no_affected_node(self, _mock_sleep, mock_time):
        mock_time.side_effect = [100.0, 105.0]
        mock_conn = MagicMock()
        mock_conn.get_chassis_status.return_value.power_on = True
        self.bm.get_ipmi_connection = MagicMock(return_value=mock_conn)

        self.bm.wait_until_running("192.168.1.100", "node1", None)  # must not raise

    @patch("time.time")
    @patch("time.sleep")
    def test_wait_until_running_polls_until_powered_on(self, mock_sleep, mock_time):
        mock_time.side_effect = [100.0, 110.0]
        status_off = MagicMock()
        status_off.power_on = False
        status_on = MagicMock()
        status_on.power_on = True

        mock_conn = MagicMock()
        mock_conn.get_chassis_status.side_effect = [status_off, status_on]
        self.bm.get_ipmi_connection = MagicMock(return_value=mock_conn)

        self.bm.wait_until_running("192.168.1.100", "node1", None)

        self.assertEqual(mock_conn.get_chassis_status.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    # --- wait_until_stopped ---

    @patch("time.time")
    @patch("time.sleep")
    def test_wait_until_stopped_updates_affected_node(self, _mock_sleep, mock_time):
        mock_time.side_effect = [100.0, 120.0]
        mock_conn = MagicMock()
        mock_conn.get_chassis_status.return_value.power_on = False  # already off
        self.bm.get_ipmi_connection = MagicMock(return_value=mock_conn)

        affected_node = MagicMock(spec=AffectedNode)
        self.bm.wait_until_stopped("192.168.1.100", "node1", affected_node)

        affected_node.set_affected_node_status.assert_called_once_with("stopped", 20.0)

    @patch("time.time")
    @patch("time.sleep")
    def test_wait_until_stopped_no_affected_node(self, _mock_sleep, mock_time):
        mock_time.side_effect = [100.0, 105.0]
        mock_conn = MagicMock()
        mock_conn.get_chassis_status.return_value.power_on = False
        self.bm.get_ipmi_connection = MagicMock(return_value=mock_conn)

        self.bm.wait_until_stopped("192.168.1.100", "node1", None)

    @patch("time.time")
    @patch("time.sleep")
    def test_wait_until_stopped_polls_until_powered_off(self, mock_sleep, mock_time):
        mock_time.side_effect = [100.0, 105.0]
        status_on = MagicMock()
        status_on.power_on = True
        status_off = MagicMock()
        status_off.power_on = False

        mock_conn = MagicMock()
        mock_conn.get_chassis_status.side_effect = [status_on, status_off]
        self.bm.get_ipmi_connection = MagicMock(return_value=mock_conn)

        self.bm.wait_until_stopped("192.168.1.100", "node1", None)

        self.assertEqual(mock_conn.get_chassis_status.call_count, 2)
        mock_sleep.assert_called_once_with(1)


class TestBMNodeScenarios(unittest.TestCase):
    """Test cases for the bm_node_scenarios orchestration class"""

    def setUp(self):
        self.kubecli = MagicMock(spec=KrknKubernetes)
        self.affected_nodes_status = AffectedNodeStatus()

        self.scenario = bm_node_scenarios(
            bm_info={"node1": {"bmc_addr": "192.168.1.100"}},
            user="admin",
            passwd="secret",
            kubecli=self.kubecli,
            node_action_kube_check=True,
            affected_nodes_status=self.affected_nodes_status,
        )
        self.mock_bm = MagicMock()
        self.scenario.bm = self.mock_bm

    def _make_scenario(self, kube_check=True):
        scenario = bm_node_scenarios(
            bm_info={},
            user="u",
            passwd="p",
            kubecli=self.kubecli,
            node_action_kube_check=kube_check,
            affected_nodes_status=AffectedNodeStatus(),
        )
        scenario.bm = MagicMock()
        scenario.bm.get_bmc_addr.return_value = "192.168.1.100"
        return scenario

    # --- node_start_scenario ---

    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status")
    def test_node_start_scenario_success(self, mock_wait_ready):
        self.mock_bm.get_bmc_addr.return_value = "192.168.1.100"

        self.scenario.node_start_scenario(1, "node1", timeout=300, poll_interval=10)

        self.mock_bm.get_bmc_addr.assert_called_once_with("node1")
        self.mock_bm.start_instances.assert_called_once_with("192.168.1.100", "node1")
        self.mock_bm.wait_until_running.assert_called_once()
        mock_wait_ready.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)
        self.assertEqual(self.affected_nodes_status.affected_nodes[0].node_name, "node1")

    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status")
    def test_node_start_scenario_skips_kube_check_when_disabled(self, mock_wait_ready):
        scenario = self._make_scenario(kube_check=False)

        scenario.node_start_scenario(1, "node1", timeout=300, poll_interval=10)

        mock_wait_ready.assert_not_called()

    def test_node_start_scenario_raises_on_failure(self):
        self.mock_bm.get_bmc_addr.side_effect = Exception("IPMI error")

        with self.assertRaises(Exception):
            self.scenario.node_start_scenario(1, "node1", timeout=300, poll_interval=10)

    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status")
    def test_node_start_scenario_loops_per_kill_count(self, _mock_wait):
        self.mock_bm.get_bmc_addr.return_value = "192.168.1.100"

        self.scenario.node_start_scenario(3, "node1", timeout=300, poll_interval=10)

        self.assertEqual(self.mock_bm.start_instances.call_count, 3)
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 3)

    # --- node_stop_scenario ---

    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status")
    def test_node_stop_scenario_success(self, mock_wait_unknown):
        self.mock_bm.get_bmc_addr.return_value = "192.168.1.100"

        self.scenario.node_stop_scenario(1, "node1", timeout=300, poll_interval=10)

        self.mock_bm.stop_instances.assert_called_once_with("192.168.1.100", "node1")
        self.mock_bm.wait_until_stopped.assert_called_once()
        mock_wait_unknown.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status")
    def test_node_stop_scenario_skips_kube_check_when_disabled(self, mock_wait_unknown):
        scenario = self._make_scenario(kube_check=False)

        scenario.node_stop_scenario(1, "node1", timeout=300, poll_interval=10)

        mock_wait_unknown.assert_not_called()

    def test_node_stop_scenario_raises_on_failure(self):
        self.mock_bm.get_bmc_addr.side_effect = Exception("IPMI error")

        with self.assertRaises(Exception):
            self.scenario.node_stop_scenario(1, "node1", timeout=300, poll_interval=10)

    # --- node_termination_scenario ---

    def test_node_termination_scenario_is_noop(self):
        self.scenario.node_termination_scenario(1, "node1", timeout=300, poll_interval=10)

        self.mock_bm.start_instances.assert_not_called()
        self.mock_bm.stop_instances.assert_not_called()
        self.mock_bm.reboot_instances.assert_not_called()

    # --- node_reboot_scenario ---

    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status")
    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status")
    def test_node_reboot_scenario_success(self, mock_wait_unknown, mock_wait_ready):
        self.mock_bm.get_bmc_addr.return_value = "192.168.1.100"

        self.scenario.node_reboot_scenario(1, "node1", timeout=300)

        self.mock_bm.reboot_instances.assert_called_once_with("192.168.1.100", "node1")
        mock_wait_unknown.assert_called_once()
        mock_wait_ready.assert_called_once()
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 1)

    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status")
    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status")
    def test_node_reboot_scenario_skips_kube_check_when_disabled(
        self, mock_wait_unknown, mock_wait_ready
    ):
        scenario = self._make_scenario(kube_check=False)

        scenario.node_reboot_scenario(1, "node1", timeout=300)

        mock_wait_unknown.assert_not_called()
        mock_wait_ready.assert_not_called()

    def test_node_reboot_scenario_raises_on_failure(self):
        self.mock_bm.get_bmc_addr.side_effect = Exception("IPMI error")

        with self.assertRaises(Exception):
            self.scenario.node_reboot_scenario(1, "node1", timeout=300)

    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_ready_status")
    @patch("krkn.scenario_plugins.node_actions.common_node_functions.wait_for_unknown_status")
    def test_node_reboot_scenario_loops_per_kill_count(self, _wait_unknown, _wait_ready):
        self.mock_bm.get_bmc_addr.return_value = "192.168.1.100"

        self.scenario.node_reboot_scenario(3, "node1", timeout=300)

        self.assertEqual(self.mock_bm.reboot_instances.call_count, 3)
        self.assertEqual(len(self.affected_nodes_status.affected_nodes), 3)

    # --- get_disk_attachment_info ---

    def test_get_disk_attachment_info_returns_user_disks_present_on_node(self):
        self.mock_bm.get_bm_disks.return_value = ["sdb", "sdc"]
        self.kubecli.exec_command_on_node.return_value = "sdb\nsdc\nsdd\n"

        result = self.scenario.get_disk_attachment_info(1, "node1")

        self.assertEqual(result, ["sdb", "sdc"])
        self.kubecli.delete_pod.assert_called_once()

    def test_get_disk_attachment_info_returns_all_node_disks_when_no_user_disks(self):
        self.mock_bm.get_bm_disks.return_value = []
        self.kubecli.exec_command_on_node.return_value = "sdb\nsdc\n"

        result = self.scenario.get_disk_attachment_info(1, "node1")

        self.assertEqual(result, ["sdb", "sdc"])

    def test_get_disk_attachment_info_filters_out_user_disks_not_on_node(self):
        self.mock_bm.get_bm_disks.return_value = ["sdb", "sde"]  # sde not found on node
        self.kubecli.exec_command_on_node.return_value = "sdb\nsdc\n"

        result = self.scenario.get_disk_attachment_info(1, "node1")

        self.assertEqual(result, ["sdb"])

    def test_get_disk_attachment_info_raises_on_exec_failure(self):
        self.mock_bm.get_bm_disks.return_value = []
        self.kubecli.exec_command_on_node.side_effect = Exception("pod exec failed")

        with self.assertRaises(RuntimeError):
            self.scenario.get_disk_attachment_info(1, "node1")

        # finally block must always clean up the pod
        self.kubecli.delete_pod.assert_called_once()

    # --- disk_detach_scenario ---

    def test_disk_detach_scenario_sends_offline_command(self):
        self.kubecli.exec_command_on_node.return_value = ""

        self.scenario.disk_detach_scenario(1, "node1", ["sdb", "sdc"], timeout=300)

        self.kubecli.exec_command_on_node.assert_called_once()
        cmd = self.kubecli.exec_command_on_node.call_args[0][1][0]
        self.assertIn("offline", cmd)
        self.assertIn("sdb", cmd)
        self.assertIn("sdc", cmd)
        self.kubecli.delete_pod.assert_called_once()

    def test_disk_detach_scenario_raises_and_cleans_up_on_failure(self):
        self.kubecli.exec_command_on_node.side_effect = Exception("exec failed")

        with self.assertRaises(RuntimeError):
            self.scenario.disk_detach_scenario(1, "node1", ["sdb"], timeout=300)

        self.kubecli.delete_pod.assert_called_once()

    # --- disk_attach_scenario ---

    def test_disk_attach_scenario_sends_running_command(self):
        self.kubecli.exec_command_on_node.return_value = ""

        self.scenario.disk_attach_scenario(1, "node1", ["sdb", "sdc"])

        self.kubecli.exec_command_on_node.assert_called_once()
        cmd = self.kubecli.exec_command_on_node.call_args[0][1][0]
        self.assertIn("running", cmd)
        self.assertIn("sdb", cmd)
        self.assertIn("sdc", cmd)
        self.kubecli.delete_pod.assert_called_once()

    def test_disk_attach_scenario_raises_and_cleans_up_on_failure(self):
        self.kubecli.exec_command_on_node.side_effect = Exception("exec failed")

        with self.assertRaises(RuntimeError):
            self.scenario.disk_attach_scenario(1, "node1", ["sdb"])

        self.kubecli.delete_pod.assert_called_once()

    # --- node_disk_detach_attach_scenario ---

    @patch("time.sleep")
    def test_node_disk_detach_attach_scenario_full_flow(self, mock_sleep):
        self.scenario.get_disk_attachment_info = MagicMock(return_value=["sdb"])
        self.scenario.disk_detach_scenario = MagicMock()
        self.scenario.disk_attach_scenario = MagicMock()

        self.scenario.node_disk_detach_attach_scenario(1, "node1", timeout=300, duration=60)

        self.scenario.disk_detach_scenario.assert_called_once_with(1, "node1", ["sdb"], 300)
        mock_sleep.assert_called_once_with(60)
        self.scenario.disk_attach_scenario.assert_called_once_with(1, "node1", ["sdb"])

    def test_node_disk_detach_attach_scenario_skips_when_no_disks(self):
        self.scenario.get_disk_attachment_info = MagicMock(return_value=[])
        self.scenario.disk_detach_scenario = MagicMock()
        self.scenario.disk_attach_scenario = MagicMock()

        self.scenario.node_disk_detach_attach_scenario(1, "node1", timeout=300, duration=60)

        self.scenario.disk_detach_scenario.assert_not_called()
        self.scenario.disk_attach_scenario.assert_not_called()

    def test_node_disk_detach_attach_scenario_skips_when_none_returned(self):
        self.scenario.get_disk_attachment_info = MagicMock(return_value=None)
        self.scenario.disk_detach_scenario = MagicMock()
        self.scenario.disk_attach_scenario = MagicMock()

        self.scenario.node_disk_detach_attach_scenario(1, "node1", timeout=300, duration=60)

        self.scenario.disk_detach_scenario.assert_not_called()
        self.scenario.disk_attach_scenario.assert_not_called()


if __name__ == "__main__":
    unittest.main()
