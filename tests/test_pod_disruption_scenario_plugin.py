#!/usr/bin/env python3

"""
Test suite for PodDisruptionScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_pod_disruption_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch
import time

from krkn.scenario_plugins.pod_disruption.pod_disruption_scenario_plugin import PodDisruptionScenarioPlugin
from krkn.scenario_plugins.pod_disruption.models.models import InputParams, KilledPodDetail


class TestPodDisruptionScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for PodDisruptionScenarioPlugin
        """
        self.plugin = PodDisruptionScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pod_disruption_scenarios"])
        self.assertEqual(len(result), 1)


class TestKilledPodDetail(unittest.TestCase):
    """Test suite for KilledPodDetail dataclass"""

    def test_killed_pod_detail_creation_with_kill_status(self):
        """Test creating a KilledPodDetail with 'killed' status"""
        timestamp = time.time()
        pod = KilledPodDetail(
            namespace="default",
            name="test-pod",
            timestamp=timestamp,
            status="killed",
            reason=""
        )

        self.assertEqual(pod.namespace, "default")
        self.assertEqual(pod.name, "test-pod")
        self.assertEqual(pod.timestamp, timestamp)
        self.assertEqual(pod.status, "killed")
        self.assertEqual(pod.reason, "")

    def test_killed_pod_detail_creation_with_excluded_status(self):
        """Test creating a KilledPodDetail with 'excluded' status"""
        timestamp = time.time()
        pod = KilledPodDetail(
            namespace="kube-system",
            name="excluded-pod",
            timestamp=timestamp,
            status="excluded",
            reason="matched exclude_label"
        )

        self.assertEqual(pod.namespace, "kube-system")
        self.assertEqual(pod.name, "excluded-pod")
        self.assertEqual(pod.timestamp, timestamp)
        self.assertEqual(pod.status, "excluded")
        self.assertEqual(pod.reason, "matched exclude_label")

    def test_killed_pod_detail_default_reason(self):
        """Test that KilledPodDetail has default empty string for reason"""
        pod = KilledPodDetail(
            namespace="default",
            name="test-pod",
            timestamp=time.time(),
            status="killed"
        )

        self.assertEqual(pod.reason, "")


class TestKillingPodsTracking(unittest.TestCase):
    """Test suite for killing_pods tracking functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.plugin = PodDisruptionScenarioPlugin()
        self.mock_kubecli = MagicMock()

    def test_killing_pods_returns_tuple(self):
        """Test that killing_pods returns a tuple of (killed_pods, return_val)"""
        # Create mock config
        config = MagicMock(spec=InputParams)
        config.namespace_pattern = "default"
        config.label_selector = "app=test"
        config.name_pattern = ""
        config.node_label_selector = ""
        config.node_names = None
        config.exclude_label = ""
        config.kill = 1

        # Mock the pod selection
        test_pod = ("test-pod-1", "default")
        self.plugin.get_pods = MagicMock(return_value=[test_pod])
        self.plugin.wait_for_pods = MagicMock(return_value=0)
        self.mock_kubecli.delete_pod = MagicMock()

        # Call killing_pods
        killed_pods, return_val = self.plugin.killing_pods(config, self.mock_kubecli)

        # Verify it returns a tuple
        self.assertIsInstance(killed_pods, list)
        self.assertIsInstance(return_val, int)
        self.assertEqual(return_val, 0)

    def test_killing_pods_tracks_killed_pods(self):
        """Test that killing_pods tracks each killed pod"""
        config = MagicMock(spec=InputParams)
        config.namespace_pattern = "default"
        config.label_selector = "app=test"
        config.name_pattern = ""
        config.node_label_selector = ""
        config.node_names = None
        config.exclude_label = ""
        config.kill = 2

        # Mock multiple pods
        test_pods = [
            ("test-pod-1", "default"),
            ("test-pod-2", "default")
        ]
        self.plugin.get_pods = MagicMock(return_value=test_pods)
        self.plugin.wait_for_pods = MagicMock(return_value=0)
        self.mock_kubecli.delete_pod = MagicMock()

        # Call killing_pods
        killed_pods, return_val = self.plugin.killing_pods(config, self.mock_kubecli)

        # Verify tracking
        self.assertEqual(len(killed_pods), 2)
        self.assertEqual(killed_pods[0].name, "test-pod-1")
        self.assertEqual(killed_pods[0].namespace, "default")
        self.assertEqual(killed_pods[0].status, "killed")
        self.assertEqual(killed_pods[1].name, "test-pod-2")
        self.assertEqual(killed_pods[1].status, "killed")

    def test_killing_pods_tracks_excluded_pods(self):
        """Test that killing_pods distinguishes excluded pods from killed pods"""
        config = MagicMock(spec=InputParams)
        config.namespace_pattern = "default"
        config.label_selector = "app=test"
        config.name_pattern = ""
        config.node_label_selector = ""
        config.node_names = None
        config.exclude_label = "protected=true"
        config.kill = 2

        # Mock pods where one is excluded
        test_pods = [
            ("test-pod-1", "default"),
            ("protected-pod", "default")
        ]
        excluded_pods = [("protected-pod", "default")]

        self.plugin.get_pods = MagicMock(side_effect=[test_pods, excluded_pods])
        self.plugin.wait_for_pods = MagicMock(return_value=0)
        self.mock_kubecli.delete_pod = MagicMock()

        # Call killing_pods
        killed_pods, return_val = self.plugin.killing_pods(config, self.mock_kubecli)

        # Verify tracking distinguishes killed vs excluded
        self.assertEqual(len(killed_pods), 2)
        killed = [p for p in killed_pods if p.status == "killed"]
        excluded = [p for p in killed_pods if p.status == "excluded"]
        self.assertEqual(len(killed), 1)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(killed[0].name, "test-pod-1")
        self.assertEqual(excluded[0].name, "protected-pod")
        self.assertEqual(excluded[0].reason, "matched exclude_label")

    def test_killing_pods_returns_empty_list_on_insufficient_pods(self):
        """Test that killing_pods returns empty list when insufficient pods found"""
        config = MagicMock(spec=InputParams)
        config.namespace_pattern = "default"
        config.label_selector = "app=test"
        config.name_pattern = ""
        config.node_label_selector = ""
        config.node_names = None
        config.exclude_label = ""
        config.kill = 5

        # Mock no pods found
        self.plugin.get_pods = MagicMock(return_value=[])

        # Call killing_pods
        killed_pods, return_val = self.plugin.killing_pods(config, self.mock_kubecli)

        # Verify
        self.assertEqual(len(killed_pods), 0)
        self.assertEqual(return_val, 1)  # Should return error

    def test_killing_pods_has_timestamps(self):
        """Test that killed pods have timestamps"""
        config = MagicMock(spec=InputParams)
        config.namespace_pattern = "default"
        config.label_selector = "app=test"
        config.name_pattern = ""
        config.node_label_selector = ""
        config.node_names = None
        config.exclude_label = ""
        config.kill = 1

        test_pod = ("test-pod-1", "default")
        self.plugin.get_pods = MagicMock(return_value=[test_pod])
        self.plugin.wait_for_pods = MagicMock(return_value=0)
        self.mock_kubecli.delete_pod = MagicMock()

        before_time = time.time()
        killed_pods, return_val = self.plugin.killing_pods(config, self.mock_kubecli)
        after_time = time.time()

        # Verify timestamp is set and reasonable
        self.assertEqual(len(killed_pods), 1)
        self.assertGreaterEqual(killed_pods[0].timestamp, before_time)
        self.assertLessEqual(killed_pods[0].timestamp, after_time)


if __name__ == "__main__":
    unittest.main()
