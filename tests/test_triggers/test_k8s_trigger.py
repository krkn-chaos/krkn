#!/usr/bin/env python3

"""
Test suite for K8sTrigger class

Usage:
    python -m coverage run -a -m unittest tests/test_triggers/test_k8s_trigger.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from krkn.scenario_plugins.triggers.k8s_trigger import (
    K8sTrigger,
    _coerce,
    _compare,
    _parse_condition,
    _resolve_path,
)
from kubernetes import config as k8s_config
from kubernetes.dynamic.exceptions import (
    NotFoundError,
    ResourceNotFoundError,
)


class TestResolvePath(unittest.TestCase):
    """Tests for the _resolve_path helper."""

    def test_simple_dict_path(self):
        obj = {"status": {"phase": "Running"}}
        self.assertEqual(_resolve_path(obj, "status.phase"), "Running")

    def test_nested_dict(self):
        obj = {"spec": {"replicas": 3}}
        self.assertEqual(_resolve_path(obj, "spec.replicas"), 3)

    def test_list_index(self):
        obj = {"items": ["a", "b", "c"]}
        self.assertEqual(_resolve_path(obj, "items.1"), "b")

    def test_missing_key_raises(self):
        obj = {"status": {}}
        with self.assertRaises(KeyError):
            _resolve_path(obj, "status.phase")

    def test_attribute_access(self):
        inner = MagicMock()
        inner.phase = "Succeeded"
        obj = {"status": inner}
        self.assertEqual(_resolve_path(obj, "status.phase"), "Succeeded")

    def test_single_segment(self):
        obj = {"phase": "Running"}
        self.assertEqual(_resolve_path(obj, "phase"), "Running")


class TestCoerce(unittest.TestCase):
    """Tests for the _coerce helper."""

    def test_integer(self):
        self.assertEqual(_coerce("42"), 42)
        self.assertIsInstance(_coerce("42"), int)

    def test_float(self):
        self.assertEqual(_coerce("3.14"), 3.14)
        self.assertIsInstance(_coerce("3.14"), float)

    def test_true(self):
        self.assertTrue(_coerce("true"))
        self.assertTrue(_coerce("True"))
        self.assertTrue(_coerce("TRUE"))

    def test_false(self):
        self.assertFalse(_coerce("false"))
        self.assertFalse(_coerce("False"))

    def test_none(self):
        self.assertIsNone(_coerce("none"))
        self.assertIsNone(_coerce("null"))
        self.assertIsNone(_coerce("None"))

    def test_string(self):
        self.assertEqual(_coerce("Running"), "Running")


class TestCompare(unittest.TestCase):
    """Tests for the _compare helper."""

    def test_eq_string(self):
        self.assertTrue(_compare("Running", "==", "Running"))
        self.assertFalse(_compare("Pending", "==", "Running"))

    def test_ne_string(self):
        self.assertTrue(_compare("Pending", "!=", "Running"))
        self.assertFalse(_compare("Running", "!=", "Running"))

    def test_eq_numeric_as_string(self):
        self.assertTrue(_compare(3, "==", 3))
        self.assertTrue(_compare("3", "==", "3"))

    def test_gte(self):
        self.assertTrue(_compare(3, ">=", 3))
        self.assertTrue(_compare(4, ">=", 3))
        self.assertFalse(_compare(2, ">=", 3))

    def test_lte(self):
        self.assertTrue(_compare(3, "<=", 3))
        self.assertTrue(_compare(2, "<=", 3))
        self.assertFalse(_compare(4, "<=", 3))

    def test_gt(self):
        self.assertTrue(_compare(4, ">", 3))
        self.assertFalse(_compare(3, ">", 3))

    def test_lt(self):
        self.assertTrue(_compare(2, "<", 3))
        self.assertFalse(_compare(3, "<", 3))

    def test_numeric_comparison_non_numeric_raises(self):
        with self.assertRaises(ValueError):
            _compare("abc", ">", 3)


class TestParseCondition(unittest.TestCase):
    """Tests for the _parse_condition helper."""

    def test_eq(self):
        path, op, val = _parse_condition("status.phase == Running")
        self.assertEqual(path, "status.phase")
        self.assertEqual(op, "==")
        self.assertEqual(val, "Running")

    def test_ne(self):
        path, op, val = _parse_condition("status.phase != Pending")
        self.assertEqual(path, "status.phase")
        self.assertEqual(op, "!=")
        self.assertEqual(val, "Pending")

    def test_gte_with_int(self):
        path, op, val = _parse_condition("status.readyReplicas >= 1")
        self.assertEqual(path, "status.readyReplicas")
        self.assertEqual(op, ">=")
        self.assertEqual(val, 1)

    def test_no_spaces(self):
        path, op, val = _parse_condition("status.phase==Running")
        self.assertEqual(path, "status.phase")
        self.assertEqual(op, "==")
        self.assertEqual(val, "Running")

    def test_missing_operator_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _parse_condition("status.phase Running")
        self.assertIn("operator", str(ctx.exception))

    def test_missing_path_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _parse_condition("== Running")
        self.assertIn("field path", str(ctx.exception))

    def test_missing_value_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _parse_condition("status.phase ==")
        self.assertIn("expected value", str(ctx.exception))

    def test_boolean_value(self):
        _, _, val = _parse_condition("status.ready == true")
        self.assertIs(val, True)


class TestK8sTriggerInit(unittest.TestCase):
    """Tests for K8sTrigger constructor validation."""

    def test_missing_api_version_raises(self):
        with self.assertRaises(ValueError) as ctx:
            K8sTrigger({
                "type": "k8s",
                "kind": "Deployment",
                "name": "nginx",
                "condition": "status.phase == Running",
            })
        self.assertIn("apiVersion", str(ctx.exception))

    def test_missing_kind_raises(self):
        with self.assertRaises(ValueError) as ctx:
            K8sTrigger({
                "type": "k8s",
                "apiVersion": "apps/v1",
                "name": "nginx",
                "condition": "status.phase == Running",
            })
        self.assertIn("kind", str(ctx.exception))

    def test_missing_name_raises(self):
        with self.assertRaises(ValueError) as ctx:
            K8sTrigger({
                "type": "k8s",
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "condition": "status.phase == Running",
            })
        self.assertIn("name", str(ctx.exception))

    def test_missing_condition_raises(self):
        with self.assertRaises(ValueError) as ctx:
            K8sTrigger({
                "type": "k8s",
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": "nginx",
            })
        self.assertIn("condition", str(ctx.exception))

    def test_valid_config(self):
        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": "nginx",
            "namespace": "default",
            "condition": "status.readyReplicas >= 1",
        })
        self.assertEqual(trigger._api_version, "apps/v1")
        self.assertEqual(trigger._kind, "Deployment")
        self.assertEqual(trigger._name, "nginx")
        self.assertEqual(trigger._namespace, "default")
        self.assertEqual(trigger._path, "status.readyReplicas")
        self.assertEqual(trigger._operator, ">=")
        self.assertEqual(trigger._expected, 1)

    def test_namespace_optional(self):
        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "v1",
            "kind": "Node",
            "name": "worker-1",
            "condition": "status.phase == Ready",
        })
        self.assertIsNone(trigger._namespace)


class TestK8sTriggerEvaluate(unittest.TestCase):
    """Tests for K8sTrigger.evaluate() with mocked Kubernetes client."""

    def _make_trigger(self, **overrides):
        config = {
            "type": "k8s",
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": "nginx",
            "namespace": "default",
            "condition": "status.readyReplicas >= 1",
        }
        config.update(overrides)
        return K8sTrigger(config)

    def _mock_resource(self, data: dict):
        """Create a mock resource that supports dict-style path resolution."""
        return data

    @patch.object(K8sTrigger, "_get_client")
    def test_condition_met(self, mock_get_client):
        """Resource matches condition -> returns True."""
        mock_dyn = MagicMock()
        mock_get_client.return_value = mock_dyn
        mock_api = MagicMock()
        mock_dyn.resources.get.return_value = mock_api
        mock_api.get.return_value = self._mock_resource(
            {"status": {"readyReplicas": 3}}
        )

        trigger = self._make_trigger()
        self.assertTrue(trigger.evaluate())

        mock_dyn.resources.get.assert_called_once_with(
            api_version="apps/v1", kind="Deployment"
        )
        mock_api.get.assert_called_once_with(
            name="nginx", namespace="default"
        )

    @patch.object(K8sTrigger, "_get_client")
    def test_condition_not_met(self, mock_get_client):
        """Resource does not match condition -> returns False."""
        mock_dyn = MagicMock()
        mock_get_client.return_value = mock_dyn
        mock_api = MagicMock()
        mock_dyn.resources.get.return_value = mock_api
        mock_api.get.return_value = self._mock_resource(
            {"status": {"readyReplicas": 0}}
        )

        trigger = self._make_trigger()
        self.assertFalse(trigger.evaluate())

    @patch.object(K8sTrigger, "_get_client")
    def test_string_equality(self, mock_get_client):
        """String equality condition works."""
        mock_dyn = MagicMock()
        mock_get_client.return_value = mock_dyn
        mock_api = MagicMock()
        mock_dyn.resources.get.return_value = mock_api
        mock_api.get.return_value = self._mock_resource(
            {"status": {"phase": "Running"}}
        )

        trigger = self._make_trigger(
            condition="status.phase == Running",
            kind="VirtualMachineInstanceMigration",
            apiVersion="kubevirt.io/v1",
        )
        self.assertTrue(trigger.evaluate())

    @patch.object(K8sTrigger, "_get_client")
    def test_resource_not_found(self, mock_get_client):
        """Resource does not exist yet -> returns False."""
        mock_dyn = MagicMock()
        mock_get_client.return_value = mock_dyn
        mock_api = MagicMock()
        mock_dyn.resources.get.return_value = mock_api
        mock_api.get.side_effect = NotFoundError(MagicMock(status=404))

        trigger = self._make_trigger()
        self.assertFalse(trigger.evaluate())

    @patch.object(K8sTrigger, "_get_client")
    def test_api_resource_not_registered(self, mock_get_client):
        """CRD not installed on cluster -> returns False."""
        mock_dyn = MagicMock()
        mock_get_client.return_value = mock_dyn
        mock_dyn.resources.get.side_effect = ResourceNotFoundError(
            "Resource not found"
        )

        trigger = self._make_trigger(
            apiVersion="kubevirt.io/v1",
            kind="VirtualMachineInstanceMigration",
        )
        self.assertFalse(trigger.evaluate())

    @patch.object(K8sTrigger, "_get_client")
    def test_field_path_missing(self, mock_get_client):
        """Field path doesn't exist on resource -> returns False."""
        mock_dyn = MagicMock()
        mock_get_client.return_value = mock_dyn
        mock_api = MagicMock()
        mock_dyn.resources.get.return_value = mock_api
        mock_api.get.return_value = self._mock_resource({"status": {}})

        trigger = self._make_trigger()
        self.assertFalse(trigger.evaluate())

    @patch.object(K8sTrigger, "_get_client")
    def test_unexpected_error(self, mock_get_client):
        """Unexpected API error -> returns False, no crash."""
        mock_dyn = MagicMock()
        mock_get_client.return_value = mock_dyn
        mock_dyn.resources.get.side_effect = ConnectionError("refused")

        trigger = self._make_trigger()
        self.assertFalse(trigger.evaluate())

    @patch.object(K8sTrigger, "_get_client")
    def test_cluster_scoped_resource(self, mock_get_client):
        """No namespace -> calls get() without namespace kwarg."""
        mock_dyn = MagicMock()
        mock_get_client.return_value = mock_dyn
        mock_api = MagicMock()
        mock_dyn.resources.get.return_value = mock_api
        mock_api.get.return_value = self._mock_resource(
            {"status": {"phase": "Ready"}}
        )

        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "v1",
            "kind": "Node",
            "name": "worker-1",
            "condition": "status.phase == Ready",
        })
        trigger.evaluate()

        mock_api.get.assert_called_once_with(name="worker-1")

    @patch.object(K8sTrigger, "_get_client")
    def test_crd_same_code_path(self, mock_get_client):
        """CRD uses the exact same code path as built-in resources."""
        mock_dyn = MagicMock()
        mock_get_client.return_value = mock_dyn
        mock_api = MagicMock()
        mock_dyn.resources.get.return_value = mock_api
        mock_api.get.return_value = self._mock_resource(
            {"status": {"phase": "Running"}}
        )

        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "kubevirt.io/v1",
            "kind": "VirtualMachineInstanceMigration",
            "name": "test-migration",
            "namespace": "vm-ns",
            "condition": "status.phase == Running",
        })
        self.assertTrue(trigger.evaluate())

        mock_dyn.resources.get.assert_called_once_with(
            api_version="kubevirt.io/v1",
            kind="VirtualMachineInstanceMigration",
        )


class TestK8sTriggerDescribe(unittest.TestCase):
    """Tests for K8sTrigger.describe()."""

    def test_describe_with_namespace(self):
        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": "nginx",
            "namespace": "default",
            "condition": "status.readyReplicas >= 1",
        })
        desc = trigger.describe()
        self.assertIn("apps/v1", desc)
        self.assertIn("Deployment", desc)
        self.assertIn("nginx", desc)
        self.assertIn("default", desc)
        self.assertIn("readyReplicas >= 1", desc)

    def test_describe_without_namespace(self):
        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "v1",
            "kind": "Node",
            "name": "worker-1",
            "condition": "status.phase == Ready",
        })
        desc = trigger.describe()
        self.assertIn("Node", desc)
        self.assertIn("worker-1", desc)
        self.assertNotIn("namespace", desc)


class TestK8sTriggerClientInit(unittest.TestCase):
    """Tests for K8sTrigger._get_client() initialization."""

    @patch("krkn.scenario_plugins.triggers.k8s_trigger.DynamicClient")
    @patch("krkn.scenario_plugins.triggers.k8s_trigger.client.ApiClient")
    @patch("krkn.scenario_plugins.triggers.k8s_trigger.config.load_kube_config")
    @patch(
        "krkn.scenario_plugins.triggers.k8s_trigger.config.load_incluster_config",
        side_effect=k8s_config.ConfigException("not in cluster"),
    )
    def test_loads_kubeconfig_outside_cluster(
        self, mock_incluster, mock_kubeconfig, mock_api_client, mock_dyn
    ):
        """Falls back to kubeconfig when not running in-cluster."""
        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "v1",
            "kind": "Pod",
            "name": "test",
            "namespace": "default",
            "condition": "status.phase == Running",
        })
        trigger._get_client()

        mock_incluster.assert_called_once()
        mock_kubeconfig.assert_called_once()

    @patch("krkn.scenario_plugins.triggers.k8s_trigger.DynamicClient")
    @patch("krkn.scenario_plugins.triggers.k8s_trigger.client.ApiClient")
    @patch("krkn.scenario_plugins.triggers.k8s_trigger.config.load_incluster_config")
    def test_loads_incluster_config(
        self, mock_incluster, mock_api_client, mock_dyn
    ):
        """Uses in-cluster config when available."""
        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "v1",
            "kind": "Pod",
            "name": "test",
            "namespace": "default",
            "condition": "status.phase == Running",
        })
        trigger._get_client()

        mock_incluster.assert_called_once()

    @patch("krkn.scenario_plugins.triggers.k8s_trigger.DynamicClient")
    @patch("krkn.scenario_plugins.triggers.k8s_trigger.client.ApiClient")
    @patch("krkn.scenario_plugins.triggers.k8s_trigger.config.load_kube_config")
    @patch(
        "krkn.scenario_plugins.triggers.k8s_trigger.config.load_incluster_config",
        side_effect=k8s_config.ConfigException("not in cluster"),
    )
    def test_client_cached(
        self, mock_incluster, mock_kubeconfig, mock_api_client, mock_dyn
    ):
        """Client is created once and reused on subsequent calls."""
        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "v1",
            "kind": "Pod",
            "name": "test",
            "namespace": "default",
            "condition": "status.phase == Running",
        })
        c1 = trigger._get_client()
        c2 = trigger._get_client()

        self.assertIs(c1, c2)
        self.assertEqual(mock_kubeconfig.call_count, 1)


if __name__ == "__main__":
    unittest.main()
