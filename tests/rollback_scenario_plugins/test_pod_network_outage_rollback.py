import unittest
import logging
from unittest.mock import MagicMock, call
from krkn.rollback.config import RollbackContent
from krkn.scenario_plugins.native.pod_network_outage.pod_network_outage_plugin import (
    rollback_pod_network_outage,
    _clear_rollback_caches,  # Import cache clearing function
)

class TestPodNetworkOutageRollback(unittest.TestCase):
    
    def setUp(self):
        """Clear rollback caches before each test to avoid cross-test contamination."""
        _clear_rollback_caches()
    
    def test_rollback_executes_cleanup_commands(self):
        mock_kubecli = MagicMock()
        mock_tel = MagicMock()
        mock_tel.get_lib_kubernetes.return_value = mock_kubecli

        # Simulate two nodes
        mock_kubecli.list_nodes.return_value = ["node1", "node2"]

        # Simulate leftover pods list
        mock_kubecli.list_pods.return_value = ["modtools-123", "normalpod"]

        # Simulate pod readiness for cleanup pod
        ready_pod = MagicMock()
        ready_pod.status.phase = "Running"
        ready_pod.status.container_statuses = [MagicMock(ready=True)]
        mock_kubecli.read_pod.return_value = ready_pod

        # Prevent exec_cmd_in_pod from raising
        mock_kubecli.exec_cmd_in_pod.return_value = ""

        content = RollbackContent(resource_identifier="mypod", namespace="default")
        
        rollback_pod_network_outage(content, mock_tel)

        # Cleanup pod(s) created once per node
        self.assertEqual(mock_kubecli.create_pod.call_count, 2)

        # Cleanup pod names start with the expected prefix
        for call_args in mock_kubecli.create_pod.call_args_list:
            pod_body = call_args.args[0]  # first positional arg
            self.assertTrue(
                pod_body["metadata"]["name"].startswith("rollback-clean-mypod-"),
                f"Unexpected cleanup pod name: {pod_body['metadata']['name']}",
            )

        # Expected cleanup commands issued (bridges + IFB)
        mock_kubecli.exec_cmd_in_pod.assert_any_call(
            ["/host", "ovs-ofctl", "-O", "OpenFlow13", "del-flows", "br-int", "priority=65535"],
            unittest.mock.ANY,
            "default",
            base_command="chroot",
        )
        mock_kubecli.exec_cmd_in_pod.assert_any_call(
            ["/host", "ovs-ofctl", "-O", "OpenFlow13", "del-flows", "br0", "priority=65535"],
            unittest.mock.ANY,
            "default",
            base_command="chroot",
        )
        mock_kubecli.exec_cmd_in_pod.assert_any_call(
            ["/host", "modprobe", "-r", "ifb"],
            unittest.mock.ANY,
            "default",
            base_command="chroot",
        )

        # Only modtools pod is deleted
        mock_kubecli.delete_pod.assert_any_call("modtools-123", "default")
        self.assertNotIn(
            call("normalpod", "default"),
            mock_kubecli.delete_pod.mock_calls,
        )

        # Cleanup pods deletion attempted (2 cleanup + 1 modtools)
        self.assertGreaterEqual(mock_kubecli.delete_pod.call_count, 3)
        
        logging.info("Rollback logic verified successfully!")

if __name__ == "__main__":
    unittest.main()