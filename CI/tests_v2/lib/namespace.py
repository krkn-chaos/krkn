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

# Privileged pod-security labels applied to ephemeral test namespaces so the same
# workloads are admitted on both Kubernetes and OpenShift. Shared by the test_namespace
# fixture and the make_namespace factory.
POD_SECURITY_PRIVILEGED_LABELS = {
    "pod-security.kubernetes.io/audit": "privileged",
    "pod-security.kubernetes.io/enforce": "privileged",
    "pod-security.kubernetes.io/enforce-version": "v1.24",
    "pod-security.kubernetes.io/warn": "privileged",
    "security.openshift.io/scc.podSecurityLabelSync": "false",
}


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


def create_labeled_namespace(k8s_core, name: str, extra_labels: dict = None) -> str:
    """Create a namespace with privileged pod-security labels plus any extra_labels.

    Reusable across scenarios that need ad-hoc namespaces (e.g. multi-namespace
    selection or label-selector targeting). Returns the namespace name.
    """
    labels = dict(POD_SECURITY_PRIVILEGED_LABELS)
    if extra_labels:
        labels.update(extra_labels)
    body = client.V1Namespace(metadata=client.V1ObjectMeta(name=name, labels=labels))
    k8s_core.create_namespace(body=body)
    logger.info("Created test namespace: %s", name)
    return name


def delete_namespace_quietly(k8s_core, name: str) -> None:
    """Background-delete a namespace, logging (never raising) on failure. Safe in finalizers."""
    try:
        k8s_core.delete_namespace(
            name=name,
            body=client.V1DeleteOptions(propagation_policy="Background"),
        )
    except Exception as e:  # noqa: BLE001 - cleanup must never raise
        logger.warning("Failed to delete namespace %s: %s", name, e)


def _keep_namespace_on_fail(request) -> bool:
    """True when --keep-ns-on-fail is set and the test's call phase failed."""
    keep_on_fail = request.config.getoption("--keep-ns-on-fail", False)
    rep_call = getattr(request.node, "rep_call", None)
    failed = rep_call is not None and rep_call.failed
    return bool(keep_on_fail and failed)


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
            labels=dict(POD_SECURITY_PRIVILEGED_LABELS),
        )
    )
    k8s_core.create_namespace(body=ns)
    logger.info("Created test namespace: %s", name)

    yield name

    if _keep_namespace_on_fail(request):
        logger.info("[keep-ns-on-fail] Keeping namespace %s for debugging", name)
        return

    delete_namespace_quietly(k8s_core, name)


@pytest.fixture(scope="function")
def make_namespace(request, k8s_core):
    """
    Factory fixture to create ad-hoc privileged test namespaces during a test.

    Returns a callable make(name, extra_labels=None) -> name. Each created namespace
    is registered for teardown deletion, honouring --keep-ns-on-fail the same way the
    test_namespace fixture does. Useful for scenarios that need several namespaces
    (multi-namespace selection) or a uniquely labelled namespace (label-selector targeting).
    """

    def _make(name: str, extra_labels: dict = None) -> str:
        create_labeled_namespace(k8s_core, name, extra_labels=extra_labels)

        def _finalize(ns_name=name):
            if _keep_namespace_on_fail(request):
                logger.info("[keep-ns-on-fail] Keeping namespace %s for debugging", ns_name)
                return
            delete_namespace_quietly(k8s_core, ns_name)

        request.addfinalizer(_finalize)
        return name

    return _make


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
