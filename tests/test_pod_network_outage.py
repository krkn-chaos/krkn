#!/usr/bin/env python3

"""
Test suite for pod network outage plugin

This test suite covers the get_test_pods function in pod_network_outage_plugin
using mocks to avoid needing actual Kubernetes infrastructure.

Test Coverage:
- get_test_pods with exclude_label filters
- get_test_pods with pod_name taking precedence over label filters
- get_test_pods with both pod_name and exclude_label

IMPORTANT: These tests use mocking and do NOT require any Kubernetes cluster.
All Kubernetes API calls are mocked via unittest.mock.

Usage:
    python -m unittest tests/test_pod_network_outage.py -v

    # Run with coverage
    python -m coverage run -a -m unittest tests/test_pod_network_outage.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock

from krkn.scenario_plugins.native.pod_network_outage.pod_network_outage_plugin import (
    get_test_pods,
)


class TestPodNetworkOutage(unittest.TestCase):
    def test_list_pods_with_exclude_label(self):
        """Test that get_test_pods passes exclude_label to kubecli.list_pods"""
        mock_kubecli = MagicMock()
        mock_kubecli.list_pods.return_value = ["pod2", "pod3"]

        result = get_test_pods(None, "app=test", "test-namespace", mock_kubecli, "skip=true")

        mock_kubecli.list_pods.assert_called_once_with(
            label_selector="app=test",
            namespace="test-namespace",
            exclude_label="skip=true",
        )
        self.assertEqual(result, ["pod2", "pod3"])

    def test_list_pods_without_exclude_label(self):
        """Test that get_test_pods works without exclude_label"""
        mock_kubecli = MagicMock()
        mock_kubecli.list_pods.return_value = ["pod1", "pod2", "pod3"]

        result = get_test_pods(None, "app=test", "test-namespace", mock_kubecli)

        mock_kubecli.list_pods.assert_called_once_with(
            label_selector="app=test",
            namespace="test-namespace",
            exclude_label=None,
        )
        self.assertEqual(result, ["pod1", "pod2", "pod3"])

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
