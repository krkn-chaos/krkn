#!/usr/bin/env python3
"""
Test suite for the Object State Health Check Plugin.

Usage:
    python -m unittest tests/test_object_state_health_check_plugin.py -v
"""

import logging
import queue
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from krkn.health_checks.object_state_health_check_plugin import ObjectStateHealthCheckPlugin


class TestObjectStateHealthCheckPlugin(unittest.TestCase):

    def setUp(self):
        self.mock_krkn_lib = MagicMock()
        self.plugin = ObjectStateHealthCheckPlugin(
            iterations=1,
            krkn_lib=self.mock_krkn_lib
        )

    def test_get_health_check_types(self):
        """Plugin returns expected health check types."""
        types = self.plugin.get_health_check_types()
        self.assertIn("object_state_health_check", types)
        self.assertIn("k8s_object_health_check", types)

    def test_get_config_key(self):
        """Plugin returns correct config key."""
        self.assertEqual(self.plugin.get_config_key(), "object_state_checks")

    def test_increment_iterations(self):
        """increment_iterations increases the counter."""
        initial = self.plugin.current_iterations
        self.plugin.increment_iterations()
        self.assertEqual(self.plugin.current_iterations, initial + 1)

    def test_run_once_no_config(self):
        """run_once with no config returns passed."""
        result = self.plugin.run_once({})
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["failures"]), 0)

    def test_run_once_blank_run_during_skips(self):
        """Blank run_during values skip the object state check."""
        for run_during in ("", "   ", []):
            with self.subTest(run_during=run_during):
                result = self.plugin.run_once({"run_during": run_during, "config": [{"namespace": "default"}]})

                self.assertTrue(result["passed"])
                self.assertEqual(result["details"], {})
                self.mock_krkn_lib.list_pods.assert_not_called()

    def test_run_once_blank_namespace_skips(self):
        """Checks without a namespace are skipped without failing."""
        result = self.plugin.run_once({
            "config": [{
                "name": "missing-namespace",
                "kind": "Pod",
                "namespace": "",
                "condition": {"type": "Ready", "status": "True"}
            }]
        })

        self.assertTrue(result["passed"])
        self.assertEqual(result["details"], {})
        self.mock_krkn_lib.list_pods.assert_not_called()

    def test_check_object_condition_passed(self):
        """_check_object_condition returns True when condition matches."""
        obj = {
            "kind": "Pod",
            "metadata": {"name": "test-pod", "namespace": "default"},
            "status": {
                "conditions": [
                    {"type": "Ready", "status": "True", "reason": "AllGood"}
                ]
            }
        }

        passed, message = self.plugin._check_object_condition(obj, "Ready", "True")
        self.assertTrue(passed)
        self.assertIn("test-pod", message)

    def test_check_object_condition_failed(self):
        """_check_object_condition returns False when condition doesn't match."""
        obj = {
            "kind": "Pod",
            "metadata": {"name": "test-pod", "namespace": "default"},
            "status": {
                "conditions": [
                    {"type": "Ready", "status": "False", "reason": "NotReady", "message": "Pod not ready"}
                ]
            }
        }

        passed, message = self.plugin._check_object_condition(obj, "Ready", "True")
        self.assertFalse(passed)
        self.assertIn("False", message)
        self.assertIn("NotReady", message)

    def test_check_object_condition_missing_type(self):
        """_check_object_condition returns False when condition type not found."""
        obj = {
            "kind": "Deployment",
            "metadata": {"name": "test-deploy", "namespace": "default"},
            "status": {
                "conditions": [
                    {"type": "Progressing", "status": "True"}
                ]
            }
        }

        passed, message = self.plugin._check_object_condition(obj, "Available", "True")
        self.assertFalse(passed)
        self.assertIn("does not have condition type", message)
        self.assertIn("Available", message)

    def test_check_object_condition_no_conditions(self):
        """_check_object_condition handles objects with no conditions."""
        obj = {
            "kind": "Pod",
            "metadata": {"name": "test-pod", "namespace": "default"},
            "status": {}
        }

        passed, message = self.plugin._check_object_condition(obj, "Ready", "True")
        self.assertFalse(passed)
        self.assertIn("has no conditions", message)

    def test_get_objects_pods(self):
        """_get_objects retrieves pods correctly when API returns dicts."""
        self.mock_krkn_lib.list_pods.return_value = [
            {"metadata": {"name": "pod-1"}},
            {"metadata": {"name": "pod-2"}},
        ]

        objects = self.plugin._get_objects("Pod", "default")
        self.assertEqual(len(objects), 2)
        self.mock_krkn_lib.list_pods.assert_called_once_with("default")

    def test_get_objects_pods_as_strings(self):
        """_get_objects handles when API returns strings (names) instead of dicts."""
        # Some krkn_lib methods return strings
        self.mock_krkn_lib.list_pods.return_value = ["pod-1", "pod-2"]

        # Mock get_object_by_name to return full pod objects
        pod_1 = {
            "kind": "Pod",
            "metadata": {"name": "pod-1", "namespace": "default"},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]}
        }
        pod_2 = {
            "kind": "Pod",
            "metadata": {"name": "pod-2", "namespace": "default"},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]}
        }

        self.mock_krkn_lib.get_object_by_name.side_effect = [pod_1, pod_2]

        objects = self.plugin._get_objects("Pod", "default")
        self.assertEqual(len(objects), 2)
        self.assertEqual(objects[0]["metadata"]["name"], "pod-1")
        self.assertEqual(objects[1]["metadata"]["name"], "pod-2")

    def test_get_objects_with_label_selector(self):
        """_get_objects uses label selector for pods."""
        self.mock_krkn_lib.list_pods.return_value = [
            {"metadata": {"name": "pod-1"}},
        ]

        objects = self.plugin._get_objects(
            "Pod", "default", label_selector="app=test"
        )
        self.assertEqual(len(objects), 1)
        self.mock_krkn_lib.list_pods.assert_called_once_with("default", "app=test")

    def test_get_objects_with_name_pattern(self):
        """_get_objects filters by name pattern."""
        self.mock_krkn_lib.list_pods.return_value = [
            {"metadata": {"name": "etcd-1"}},
            {"metadata": {"name": "etcd-2"}},
            {"metadata": {"name": "nginx-1"}},
        ]

        objects = self.plugin._get_objects("Pod", "default", object_name="etcd-.*")
        self.assertEqual(len(objects), 2)
        self.assertEqual(objects[0]["metadata"]["name"], "etcd-1")
        self.assertEqual(objects[1]["metadata"]["name"], "etcd-2")

    def test_get_objects_deployments(self):
        """_get_objects retrieves deployments."""
        self.mock_krkn_lib.list_deployments.return_value = [
            {"metadata": {"name": "deploy-1"}},
        ]

        objects = self.plugin._get_objects("Deployment", "default")
        self.assertEqual(len(objects), 1)
        self.mock_krkn_lib.list_deployments.assert_called_once_with("default")

    def test_check_single_config_no_kind(self):
        """_check_single_config fails when no kind specified."""
        config = {"name": "test-check"}
        result = self.plugin._check_single_config(config)

        self.assertFalse(result["passed"])
        self.assertIn("No 'kind' specified", result["message"])

    def test_check_single_config_no_objects_found(self):
        """_check_single_config fails when no objects match."""
        self.mock_krkn_lib.list_pods.return_value = []

        config = {
            "name": "test-check",
            "kind": "Pod",
            "namespace": "default",
            "object_name": "nonexistent",
            "condition": {"type": "Ready", "status": "True"}
        }
        result = self.plugin._check_single_config(config)

        self.assertFalse(result["passed"])
        self.assertIn("No Pod objects found", result["message"])

    def test_check_single_config_success(self):
        """_check_single_config succeeds when all objects pass."""
        self.mock_krkn_lib.list_pods.return_value = [
            {
                "kind": "Pod",
                "metadata": {"name": "pod-1", "namespace": "default"},
                "status": {
                    "conditions": [{"type": "Ready", "status": "True"}]
                }
            }
        ]

        config = {
            "name": "pod-ready-check",
            "kind": "Pod",
            "namespace": "default",
            "object_name": "pod-.*",
            "condition": {"type": "Ready", "status": "True"}
        }
        result = self.plugin._check_single_config(config)

        self.assertTrue(result["passed"])
        self.assertEqual(result["objects_checked"], 1)

    def test_run_once_multiple_checks(self):
        """run_once handles multiple check configurations."""
        self.mock_krkn_lib.list_pods.return_value = [
            {
                "kind": "Pod",
                "metadata": {"name": "pod-1", "namespace": "default"},
                "status": {
                    "conditions": [{"type": "Ready", "status": "True"}]
                }
            }
        ]

        config = {
            "config": [
                {
                    "name": "check-1",
                    "kind": "Pod",
                    "namespace": "default",
                    "condition": {"type": "Ready", "status": "True"}
                },
                {
                    "name": "check-2",
                    "kind": "Pod",
                    "namespace": "default",
                    "condition": {"type": "Ready", "status": "True"}
                }
            ]
        }

        result = self.plugin.run_once(config)
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["details"]), 2)
        self.assertIn("check-1", result["details"])
        self.assertIn("check-2", result["details"])

    def test_run_once_with_failures(self):
        """run_once reports failures correctly."""
        self.mock_krkn_lib.list_pods.return_value = [
            {
                "kind": "Pod",
                "metadata": {"name": "pod-1", "namespace": "default"},
                "status": {
                    "conditions": [{"type": "Ready", "status": "False"}]
                }
            }
        ]

        config = {
            "config": [
                {
                    "name": "failing-check",
                    "kind": "Pod",
                    "namespace": "default",
                    "condition": {"type": "Ready", "status": "True"}
                }
            ]
        }

        result = self.plugin.run_once(config)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(result["failures"][0]["check_name"], "failing-check")

    def test_multiple_objects_all_must_pass(self):
        """When multiple objects match, ALL must pass for check to pass."""
        # Setup: 3 pods matching pattern, one is not ready
        self.mock_krkn_lib.list_pods.return_value = [
            {
                "kind": "Pod",
                "metadata": {"name": "etcd-0", "namespace": "kube-system"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]}
            },
            {
                "kind": "Pod",
                "metadata": {"name": "etcd-1", "namespace": "kube-system"},
                "status": {"conditions": [{"type": "Ready", "status": "False", "reason": "NotReady"}]}
            },
            {
                "kind": "Pod",
                "metadata": {"name": "etcd-2", "namespace": "kube-system"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]}
            }
        ]

        config = {
            "config": [
                {
                    "name": "etcd-check",
                    "kind": "Pod",
                    "object_name": "etcd-.*",
                    "namespace": "kube-system",
                    "condition": {"type": "Ready", "status": "True"}
                }
            ]
        }

        result = self.plugin.run_once(config)

        # Check should FAIL because ONE pod (etcd-1) is not ready
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["failures"]), 1)

        # Verify details show 3 objects were checked
        self.assertEqual(result["details"]["etcd-check"]["objects_checked"], 3)
        self.assertFalse(result["details"]["etcd-check"]["passed"])

        # Message should contain only failed pod (etcd-1), not the passing ones (etcd-0, etcd-2)
        message = result["details"]["etcd-check"]["message"]
        self.assertIn("etcd-1", message)
        self.assertNotIn("etcd-0", message)  # This pod passed, should not be in failed objects list
        self.assertNotIn("etcd-2", message)  # This pod passed, should not be in failed objects list

    def test_multiple_objects_all_healthy(self):
        """When multiple objects match and all are healthy, check passes."""
        self.mock_krkn_lib.list_pods.return_value = [
            {
                "kind": "Pod",
                "metadata": {"name": "etcd-0", "namespace": "kube-system"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]}
            },
            {
                "kind": "Pod",
                "metadata": {"name": "etcd-1", "namespace": "kube-system"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]}
            },
            {
                "kind": "Pod",
                "metadata": {"name": "etcd-2", "namespace": "kube-system"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]}
            }
        ]

        config = {
            "config": [
                {
                    "name": "etcd-check",
                    "kind": "Pod",
                    "object_name": "etcd-.*",
                    "namespace": "kube-system",
                    "condition": {"type": "Ready", "status": "True"}
                }
            ]
        }

        result = self.plugin.run_once(config)

        # Check should PASS because ALL pods are ready
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["failures"]), 0)
        self.assertEqual(result["details"]["etcd-check"]["objects_checked"], 3)
        self.assertTrue(result["details"]["etcd-check"]["passed"])


if __name__ == "__main__":
    unittest.main()
