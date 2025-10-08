import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krkn.scenario_plugins.native.pod_network_outage.kubernetes_functions import (
    list_pods,
)
from krkn.scenario_plugins.native.pod_network_outage.pod_network_outage_plugin import (
    get_test_pods,
)


class TestPodNetworkOutage(unittest.TestCase):
    def test_list_pods_with_exclude_label(self):
        """Test that list_pods correctly excludes pods with matching exclude_label"""
        # Create mock pod items
        pod1 = MagicMock()
        pod1.metadata.name = "pod1"
        pod1.metadata.labels = {"app": "test", "skip": "true"}

        pod2 = MagicMock()
        pod2.metadata.name = "pod2"
        pod2.metadata.labels = {"app": "test"}

        pod3 = MagicMock()
        pod3.metadata.name = "pod3"
        pod3.metadata.labels = {"app": "test", "skip": "false"}

        # Create mock API response
        mock_response = MagicMock()
        mock_response.items = [pod1, pod2, pod3]

        # Create mock client
        mock_cli = MagicMock()
        mock_cli.list_namespaced_pod.return_value = mock_response

        # Test without exclude_label
        result = list_pods(mock_cli, "test-namespace", "app=test")
        self.assertEqual(result, ["pod1", "pod2", "pod3"])

        # Test with exclude_label
        result = list_pods(mock_cli, "test-namespace", "app=test", "skip=true")
        self.assertEqual(result, ["pod2", "pod3"])

    def test_get_test_pods_with_exclude_label(self):
        """Test that get_test_pods passes exclude_label to list_pods correctly"""
        # Create mock kubecli
        mock_kubecli = MagicMock()
        mock_kubecli.list_pods.return_value = ["pod2", "pod3"]

        # Test get_test_pods with exclude_label
        result = get_test_pods(
            None, "app=test", "test-namespace", mock_kubecli, "skip=true"
        )

        # Verify list_pods was called with the correct parameters
        mock_kubecli.list_pods.assert_called_once_with(
            label_selector="app=test",
            namespace="test-namespace",
            exclude_label="skip=true",
        )

        # Verify the result
        self.assertEqual(result, ["pod2", "pod3"])

    def test_get_test_pods_with_pod_name_and_exclude_label(self):
        """Test that get_test_pods prioritizes pod_name over label filters"""
        # Create mock kubecli
        mock_kubecli = MagicMock()
        mock_kubecli.list_pods.return_value = ["pod1", "pod2", "pod3"]

        # Test get_test_pods with both pod_name and exclude_label
        # The pod_name should take precedence
        result = get_test_pods(
            "pod1", "app=test", "test-namespace", mock_kubecli, "skip=true"
        )

        # Verify list_pods was called with the correct parameters
        mock_kubecli.list_pods.assert_called_once_with(
            label_selector="app=test",
            namespace="test-namespace",
            exclude_label="skip=true",
        )

        # Verify the result contains only the specified pod
        self.assertEqual(result, ["pod1"])


if __name__ == "__main__":
    unittest.main()
