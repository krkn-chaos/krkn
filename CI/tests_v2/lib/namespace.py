#!/usr/bin/env python
#
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

"""
Namespace lifecycle fixtures for CI/tests_v2: create, delete, stale cleanup.
"""

import logging
import os
import time
import uuid
from datetime import datetime

import pytest
from kubernetes import client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

STALE_NS_AGE_MINUTES = 30


def _namespace_age_minutes(metadata) -> float:
    """Return age of namespace in minutes from its creation_timestamp."""
    if not metadata or not metadata.creation_timestamp:
        return 0.0
    created = metadata.creation_timestamp
    if hasattr(created, "timestamp"):
        created_ts = created.timestamp()
    else:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created_ts = dt.timestamp()
        except Exception:
            return 0.0
    return (time.time() - created_ts) / 60.0


def _wait_for_namespace_gone(k8s_core, name: str, timeout: int = 60):
    """Poll until the namespace no longer exists."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            k8s_core.read_namespace(name=name)
        except ApiException as e:
            if e.status == 404:
                return
            raise
        time.sleep(1)
    raise TimeoutError(f"Namespace {name} did not disappear within {timeout}s")


@pytest.fixture(scope="function")
def test_namespace(request, k8s_core):
    """
    Create an ephemeral namespace for the test. Deleted after the test unless
    --keep-ns-on-fail is set and the test failed.
    """
    name = f"krkn-test-{uuid.uuid4().hex[:8]}"
    ns = client.V1Namespace(
        metadata=client.V1ObjectMeta(
            name=name,
            labels={
                "pod-security.kubernetes.io/audit": "privileged",
                "pod-security.kubernetes.io/enforce": "privileged",
                "pod-security.kubernetes.io/enforce-version": "v1.24",
                "pod-security.kubernetes.io/warn": "privileged",
                "security.openshift.io/scc.podSecurityLabelSync": "false",
            },
        )
    )
    k8s_core.create_namespace(body=ns)
    logger.info("Created test namespace: %s", name)

    yield name

    keep_on_fail = request.config.getoption("--keep-ns-on-fail", False)
    rep_call = getattr(request.node, "rep_call", None)
    failed = rep_call is not None and rep_call.failed
    if keep_on_fail and failed:
        logger.info("[keep-ns-on-fail] Keeping namespace %s for debugging", name)
        return

    try:
        k8s_core.delete_namespace(
            name=name,
            body=client.V1DeleteOptions(propagation_policy="Background"),
        )
        logger.debug("Scheduled background deletion for namespace: %s", name)
    except Exception as e:
        logger.warning("Failed to delete namespace %s: %s", name, e)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_stale_namespaces(k8s_core):
    """Delete krkn-test-* namespaces older than STALE_NS_AGE_MINUTES at session start."""
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return
    try:
        namespaces = k8s_core.list_namespace()
    except Exception as e:
        logger.warning("Could not list namespaces for stale cleanup: %s", e)
        return
    for ns in namespaces.items or []:
        name = ns.metadata.name if ns.metadata else ""
        if not name.startswith("krkn-test-"):
            continue
        if _namespace_age_minutes(ns.metadata) <= STALE_NS_AGE_MINUTES:
            continue
        try:
            logger.warning("Deleting stale namespace: %s", name)
            k8s_core.delete_namespace(
                name=name,
                body=client.V1DeleteOptions(propagation_policy="Background"),
            )
        except Exception as e:
            logger.warning("Failed to delete stale namespace %s: %s", name, e)
