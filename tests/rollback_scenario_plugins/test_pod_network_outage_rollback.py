import unittest
from unittest.mock import MagicMock, call
from krkn.rollback.config import RollbackContent
from krkn.scenario_plugins.native.pod_network_outage.pod_network_outage_plugin import (
    rollback_pod_network_outage
)

class TestPodNetworkOutageRollback(unittest.TestCase):

    def test_rollback_executes_cleanup_commands(self):
        mock_kubecli = MagicMock()
        mock_tel = MagicMock()
        mock_tel.get_lib_kubernetes.return_value = mock_kubecli

        # Simulate two nodes
        mock_kubecli.list_nodes.return_value = ["node1", "node2"]

        # Simulate leftover pods list
        mock_kubecli.list_pods.return_value = ["modtools-123", "normalpod"]

        # Simulate pod containers (even if rollback doesn't use them)
        mock_kubecli.get_pod_containers.return_value = ["c1", "c2"]

        content = RollbackContent(resource_identifier="mypod", namespace="default")

        rollback_pod_network_outage(content, mock_tel)

        # ---- VALIDATE CLEANUP POD CREATION ----
        self.assertGreater(
            mock_kubecli.create_pod.call_count, 
            0, 
            "Rollback did not create cleanup pods"
        )

        # ---- VALIDATE EXEC COMMANDS (OpenFlow + IFB unload) ----
        self.assertGreater(
            mock_kubecli.exec_cmd_in_pod.call_count,
            0,
            "Rollback did not call exec_cmd_in_pod"
        )

        # ---- VALIDATE MODTOOLS POD CLEANUP ----
        mock_kubecli.delete_pod.assert_any_call("modtools-123", "default")

        print("Rollback logic verified successfully!")

if __name__ == "__main__":
    unittest.main()
