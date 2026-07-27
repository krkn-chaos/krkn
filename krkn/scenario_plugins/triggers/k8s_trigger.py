# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import re

from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import (
    NotFoundError,
    ResourceNotFoundError,
)

from krkn.scenario_plugins.triggers.abstract_trigger import AbstractTrigger

OPERATORS = ("==", "!=", ">=", "<=", ">", "<")
OPERATOR_RE = re.compile(r"\s*(==|!=|>=|<=|>|<)\s*")


def _resolve_path(obj, path: str):
    """Walk a dot-separated path on a dict/ResourceInstance.

    Returns the value at the path, or raises KeyError / IndexError
    if any segment is missing.
    """
    current = obj
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current[segment]
        elif isinstance(current, (list, tuple)):
            current = current[int(segment)]
        else:
            current = getattr(current, segment)
    return current


def _coerce(value: str):
    """Coerce a string value to int, float, bool, None, or leave as str."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() == "none" or value.lower() == "null":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _compare(actual, operator: str, expected):
    """Compare actual value against expected using the given operator."""
    try:
        actual_num = float(actual)
        expected_num = float(expected)
        is_numeric = True
    except (TypeError, ValueError):
        is_numeric = False

    if operator == "==":
        if is_numeric:
            return actual_num == expected_num
        return str(actual) == str(expected)
    if operator == "!=":
        if is_numeric:
            return actual_num != expected_num
        return str(actual) != str(expected)

    if not is_numeric:
        raise ValueError(
            f"cannot compare non-numeric values with '{operator}': "
            f"actual={actual!r}, expected={expected!r}"
        )
    if operator == ">=":
        return actual_num >= expected_num
    if operator == "<=":
        return actual_num <= expected_num
    if operator == ">":
        return actual_num > expected_num
    if operator == "<":
        return actual_num < expected_num
    raise ValueError(f"unsupported operator: '{operator}'")


def _parse_condition(condition: str) -> tuple:
    """Parse 'field.path == value' into (path, operator, expected_value)."""
    match = OPERATOR_RE.search(condition)
    if not match:
        raise ValueError(
            f"condition must contain an operator "
            f"({', '.join(OPERATORS)}): got {condition!r}"
        )
    operator = match.group(1)
    path = condition[: match.start()].strip()
    raw_value = condition[match.end() :].strip()
    if not path:
        raise ValueError(f"condition is missing a field path: {condition!r}")
    if not raw_value:
        raise ValueError(f"condition is missing an expected value: {condition!r}")
    return path, operator, _coerce(raw_value)


class K8sTrigger(AbstractTrigger):
    """Trigger that waits for a Kubernetes resource to match a condition.

    Kind-agnostic: works with built-in resources and CRDs through the
    same code path using the Kubernetes dynamic client.
    """

    def __init__(self, trigger_config: dict):
        self._api_version = trigger_config.get("apiVersion")
        if not self._api_version:
            raise ValueError("k8s trigger requires 'apiVersion'")

        self._kind = trigger_config.get("kind")
        if not self._kind:
            raise ValueError("k8s trigger requires 'kind'")

        self._name = trigger_config.get("name")
        if not self._name:
            raise ValueError("k8s trigger requires 'name'")

        raw_condition = trigger_config.get("condition")
        if not raw_condition:
            raise ValueError("k8s trigger requires 'condition'")

        self._namespace = trigger_config.get("namespace")
        self._context = trigger_config.get("context")
        self._path, self._operator, self._expected = _parse_condition(
            raw_condition
        )
        self._raw_condition = raw_condition

        self._client = None
        self._last_result: bool | None = None

    def _get_client(self) -> DynamicClient:
        if self._client is None:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config(context=self._context)
            self._client = DynamicClient(client.ApiClient())
        return self._client

    def evaluate(self) -> bool:
        try:
            dyn = self._get_client()
            resource_api = dyn.resources.get(
                api_version=self._api_version, kind=self._kind
            )

            if resource_api.namespaced and not self._namespace:
                raise ValueError(
                    f"{self._api_version}/{self._kind} is namespaced "
                    f"but no namespace was specified"
                )

            if self._namespace:
                resource = resource_api.get(
                    name=self._name, namespace=self._namespace
                )
            else:
                resource = resource_api.get(name=self._name)

            actual = _resolve_path(resource, self._path)
            met = _compare(actual, self._operator, self._expected)

            logging.debug(
                "k8s trigger: %s/%s %s.%s=%r (condition: %s) -> %s",
                self._kind,
                self._name,
                self._path,
                self._operator,
                actual,
                self._raw_condition,
                met,
            )
        except NotFoundError:
            logging.debug(
                "k8s trigger: resource %s/%s not found yet",
                self._kind,
                self._name,
            )
            met = False
        except ResourceNotFoundError:
            logging.error(
                "k8s trigger: API resource %s %s not registered on cluster",
                self._api_version,
                self._kind,
            )
            met = False
        except (KeyError, IndexError, AttributeError) as e:
            logging.debug(
                "k8s trigger: field path '%s' not present on %s/%s: %s",
                self._path,
                self._kind,
                self._name,
                e,
            )
            met = False
        except Exception as e:
            logging.error("k8s trigger unexpected error: %s", e)
            met = False

        if met != self._last_result:
            if met:
                logging.info(
                    "trigger condition satisfied: %s/%s %s",
                    self._kind,
                    self._name,
                    self._raw_condition,
                )
            else:
                logging.info(
                    "trigger condition not satisfied: %s/%s %s",
                    self._kind,
                    self._name,
                    self._raw_condition,
                )
        self._last_result = met
        return met

    def describe(self) -> str:
        ns_part = f" namespace={self._namespace}" if self._namespace else ""
        ctx_part = f" context={self._context}" if self._context else ""
        return (
            f"k8s trigger: {self._api_version}/{self._kind} "
            f"'{self._name}'{ns_part}{ctx_part} "
            f"(condition: {self._raw_condition})"
        )
