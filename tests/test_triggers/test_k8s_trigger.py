#!/usr/bin/env python3

"""
Test suite for K8sTrigger class

Usage:
    python -m coverage run -a -m unittest tests/test_triggers/test_k8s_trigger.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch

from krkn.scenario_plugins.triggers.k8s_trigger import (
    K8sTrigger,
    _coerce,
    _compare,
    _parse_condition,
    _resolve_path,
)
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

    def test_eq_numeric_float_int(self):
        """1.0 == 1 should be True via numeric comparison."""
        self.assertTrue(_compare(1.0, "==", 1))
        self.assertTrue(_compare("1.0", "==", "1"))

    def test_ne_numeric_float_int(self):
        """1.0 != 1 should be False via numeric comparison."""
        self.assertFalse(_compare(1.0, "!=", 1))

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

    def _mock_kubecli(self):
        kubecli = MagicMock()
        kubecli.dyn_client = MagicMock()
        return kubecli

    def test_missing_kubecli_raises(self):
        with self.assertRaises(ValueError) as ctx:
            K8sTrigger({
                "type": "k8s",
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": "nginx",
                "condition": "status.phase == Running",
            }, kubecli=None)
        self.assertIn("kubecli", str(ctx.exception))

    def test_missing_api_version_raises(self):
        with self.assertRaises(ValueError) as ctx:
            K8sTrigger({
                "type": "k8s",
                "kind": "Deployment",
                "name": "nginx",
                "condition": "status.phase == Running",
            }, kubecli=self._mock_kubecli())
        self.assertIn("apiVersion", str(ctx.exception))

    def test_missing_kind_raises(self):
        with self.assertRaises(ValueError) as ctx:
            K8sTrigger({
                "type": "k8s",
                "apiVersion": "apps/v1",
                "name": "nginx",
                "condition": "status.phase == Running",
            }, kubecli=self._mock_kubecli())
        self.assertIn("kind", str(ctx.exception))

    def test_missing_name_raises(self):
        with self.assertRaises(ValueError) as ctx:
            K8sTrigger({
                "type": "k8s",
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "condition": "status.phase == Running",
            }, kubecli=self._mock_kubecli())
        self.assertIn("name", str(ctx.exception))

    def test_missing_condition_raises(self):
        with self.assertRaises(ValueError) as ctx:
            K8sTrigger({
                "type": "k8s",
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": "nginx",
            }, kubecli=self._mock_kubecli())
        self.assertIn("condition", str(ctx.exception))

    def test_valid_config(self):
        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": "nginx",
            "namespace": "default",
            "condition": "status.readyReplicas >= 1",
        }, kubecli=self._mock_kubecli())
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
        }, kubecli=self._mock_kubecli())
        self.assertIsNone(trigger._namespace)


class TestK8sTriggerEvaluate(unittest.TestCase):
    """Tests for K8sTrigger.evaluate() with mocked kubecli."""

    def _make_kubecli(self):
        """Create a mock kubecli with a mock dyn_client."""
        kubecli = MagicMock()
        kubecli.dyn_client = MagicMock()
        return kubecli

    def _make_trigger(self, kubecli=None, **overrides):
        if kubecli is None:
            kubecli = self._make_kubecli()
        config = {
            "type": "k8s",
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": "nginx",
            "namespace": "default",
            "condition": "status.readyReplicas >= 1",
        }
        config.update(overrides)
        return K8sTrigger(config, kubecli=kubecli), kubecli

    def test_condition_met(self):
        """Resource matches condition -> returns True."""
        trigger, kubecli = self._make_trigger()
        mock_api = MagicMock()
        kubecli.dyn_client.resources.get.return_value = mock_api
        mock_api.get.return_value = {"status": {"readyReplicas": 3}}

        self.assertTrue(trigger.evaluate())

        kubecli.dyn_client.resources.get.assert_called_once_with(
            api_version="apps/v1", kind="Deployment"
        )
        mock_api.get.assert_called_once_with(
            name="nginx", namespace="default"
        )

    def test_condition_not_met(self):
        """Resource does not match condition -> returns False."""
        trigger, kubecli = self._make_trigger()
        mock_api = MagicMock()
        kubecli.dyn_client.resources.get.return_value = mock_api
        mock_api.get.return_value = {"status": {"readyReplicas": 0}}

        self.assertFalse(trigger.evaluate())

    def test_string_equality(self):
        """String equality condition works."""
        trigger, kubecli = self._make_trigger(
            condition="status.phase == Running",
            kind="VirtualMachineInstanceMigration",
            apiVersion="kubevirt.io/v1",
        )
        mock_api = MagicMock()
        kubecli.dyn_client.resources.get.return_value = mock_api
        mock_api.get.return_value = {"status": {"phase": "Running"}}

        self.assertTrue(trigger.evaluate())

    def test_resource_not_found(self):
        """Resource does not exist yet -> returns False."""
        trigger, kubecli = self._make_trigger()
        mock_api = MagicMock()
        kubecli.dyn_client.resources.get.return_value = mock_api
        mock_api.get.side_effect = NotFoundError(MagicMock(status=404))

        self.assertFalse(trigger.evaluate())

    def test_api_resource_not_registered(self):
        """CRD not installed on cluster -> returns False."""
        trigger, kubecli = self._make_trigger(
            apiVersion="kubevirt.io/v1",
            kind="VirtualMachineInstanceMigration",
        )
        kubecli.dyn_client.resources.get.side_effect = ResourceNotFoundError(
            "Resource not found"
        )

        self.assertFalse(trigger.evaluate())

    def test_field_path_missing(self):
        """Field path doesn't exist on resource -> returns False."""
        trigger, kubecli = self._make_trigger()
        mock_api = MagicMock()
        kubecli.dyn_client.resources.get.return_value = mock_api
        mock_api.get.return_value = {"status": {}}

        self.assertFalse(trigger.evaluate())

    def test_unexpected_error(self):
        """Unexpected API error -> returns False, no crash."""
        trigger, kubecli = self._make_trigger()
        kubecli.dyn_client.resources.get.side_effect = ConnectionError("refused")

        self.assertFalse(trigger.evaluate())

    def test_namespaced_resource_without_namespace(self):
        """Namespaced resource with no namespace configured -> returns False."""
        kubecli = self._make_kubecli()
        mock_api = MagicMock()
        mock_api.namespaced = True
        kubecli.dyn_client.resources.get.return_value = mock_api

        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": "nginx",
            "condition": "status.readyReplicas >= 1",
        }, kubecli=kubecli)
        self.assertFalse(trigger.evaluate())
        mock_api.get.assert_not_called()

    def test_cluster_scoped_resource(self):
        """No namespace -> calls get() without namespace kwarg."""
        kubecli = self._make_kubecli()
        mock_api = MagicMock()
        mock_api.namespaced = False
        kubecli.dyn_client.resources.get.return_value = mock_api
        mock_api.get.return_value = {"status": {"phase": "Ready"}}

        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "v1",
            "kind": "Node",
            "name": "worker-1",
            "condition": "status.phase == Ready",
        }, kubecli=kubecli)
        trigger.evaluate()

        mock_api.get.assert_called_once_with(name="worker-1")

    def test_crd_same_code_path(self):
        """CRD uses the exact same code path as built-in resources."""
        kubecli = self._make_kubecli()
        mock_api = MagicMock()
        kubecli.dyn_client.resources.get.return_value = mock_api
        mock_api.get.return_value = {"status": {"phase": "Running"}}

        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "kubevirt.io/v1",
            "kind": "VirtualMachineInstanceMigration",
            "name": "test-migration",
            "namespace": "vm-ns",
            "condition": "status.phase == Running",
        }, kubecli=kubecli)
        self.assertTrue(trigger.evaluate())

        kubecli.dyn_client.resources.get.assert_called_once_with(
            api_version="kubevirt.io/v1",
            kind="VirtualMachineInstanceMigration",
        )

    def test_value_error_from_compare(self):
        """ValueError from _compare (non-numeric > operator) -> returns False."""
        trigger, kubecli = self._make_trigger(
            condition="status.phase > 1",
        )
        mock_api = MagicMock()
        kubecli.dyn_client.resources.get.return_value = mock_api
        mock_api.get.return_value = {"status": {"phase": "Running"}}

        self.assertFalse(trigger.evaluate())


class TestK8sTriggerDescribe(unittest.TestCase):
    """Tests for K8sTrigger.describe()."""

    def _mock_kubecli(self):
        kubecli = MagicMock()
        kubecli.dyn_client = MagicMock()
        return kubecli

    def test_describe_with_namespace(self):
        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": "nginx",
            "namespace": "default",
            "condition": "status.readyReplicas >= 1",
        }, kubecli=self._mock_kubecli())
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
        }, kubecli=self._mock_kubecli())
        desc = trigger.describe()
        self.assertIn("Node", desc)
        self.assertIn("worker-1", desc)
        self.assertNotIn("namespace", desc)


class TestK8sTriggerClientInit(unittest.TestCase):
    """Tests for K8sTrigger._get_client() delegation to kubecli."""

    def test_get_client_returns_kubecli_dyn_client(self):
        """_get_client() returns kubecli.dyn_client."""
        kubecli = MagicMock()
        mock_dyn = MagicMock()
        kubecli.dyn_client = mock_dyn

        trigger = K8sTrigger({
            "type": "k8s",
            "apiVersion": "v1",
            "kind": "Pod",
            "name": "test",
            "namespace": "default",
            "condition": "status.phase == Running",
        }, kubecli=kubecli)

        result = trigger._get_client()
        self.assertIs(result, mock_dyn)


if __name__ == "__main__":
    unittest.main()
