"""
Workload deploy and pod/deployment readiness fixtures for CI/tests_v2.
"""

import logging
import time
from pathlib import Path

import pytest
import yaml
from kubernetes import utils as k8s_utils

from lib.base import READINESS_TIMEOUT
from lib.utils import patch_namespace_in_docs

logger = logging.getLogger(__name__)


def wait_for_deployment_replicas(k8s_apps, namespace: str, name: str, timeout: int = 120) -> None:
    """
    Poll until the deployment has ready_replicas >= spec.replicas.
    Raises TimeoutError with diagnostic details on failure.
    """
    deadline = time.monotonic() + timeout
    last_dep = None
    attempts = 0
    while time.monotonic() < deadline:
        try:
            dep = k8s_apps.read_namespaced_deployment(name=name, namespace=namespace)
        except Exception as e:
            logger.debug("Deployment %s/%s poll attempt %s failed: %s", namespace, name, attempts, e)
            time.sleep(2)
            attempts += 1
            continue
        last_dep = dep
        ready = dep.status.ready_replicas or 0
        desired = dep.spec.replicas or 1
        if ready >= desired:
            logger.debug("Deployment %s/%s ready (%s/%s)", namespace, name, ready, desired)
            return
        logger.debug("Deployment %s/%s not ready yet: %s/%s", namespace, name, ready, desired)
        time.sleep(2)
        attempts += 1
    diag = ""
    if last_dep is not None and last_dep.status:
        diag = f" ready_replicas={last_dep.status.ready_replicas}, desired={last_dep.spec.replicas}"
    raise TimeoutError(
        f"Deployment {namespace}/{name} did not become ready within {timeout}s.{diag}"
    )


@pytest.fixture
def wait_for_pods_running(k8s_core):
    """
    Poll until all matching pods are Running and all containers ready.
    Uses exponential backoff: 1s, 2s, 4s, ... capped at 10s.
    Raises TimeoutError with diagnostic details on failure.
    """

    def _wait(namespace: str, label_selector: str, timeout: int = READINESS_TIMEOUT):
        deadline = time.monotonic() + timeout
        interval = 1.0
        max_interval = 10.0
        last_list = None
        while time.monotonic() < deadline:
            try:
                pod_list = k8s_core.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector,
                )
            except Exception:
                time.sleep(min(interval, max_interval))
                interval = min(interval * 2, max_interval)
                continue
            last_list = pod_list
            items = pod_list.items or []
            if not items:
                time.sleep(min(interval, max_interval))
                interval = min(interval * 2, max_interval)
                continue
            all_running = all(
                (p.status and p.status.phase == "Running") for p in items
            )
            if not all_running:
                time.sleep(min(interval, max_interval))
                interval = min(interval * 2, max_interval)
                continue
            all_ready = True
            for p in items:
                if not p.status or not p.status.container_statuses:
                    all_ready = False
                    break
                for cs in p.status.container_statuses:
                    if not getattr(cs, "ready", False):
                        all_ready = False
                        break
            if all_ready:
                return
            time.sleep(min(interval, max_interval))
            interval = min(interval * 2, max_interval)

        diag = ""
        if last_list and last_list.items:
            p = last_list.items[0]
            diag = f" e.g. pod {p.metadata.name}: phase={getattr(p.status, 'phase', None)}"
        raise TimeoutError(
            f"Pods in {namespace} with label {label_selector} did not become ready within {timeout}s.{diag}"
        )

    return _wait


@pytest.fixture(scope="function")
def deploy_workload(test_namespace, k8s_client, wait_for_pods_running, repo_root, tmp_path):
    """
    Helper that applies a manifest into the test namespace and waits for pods.
    Yields a callable: deploy(manifest_path_or_content, label_selector, *, is_path=True)
    which applies the manifest, waits for readiness, and returns the namespace name.
    """

    def _deploy(manifest_path_or_content, label_selector, *, is_path=True, timeout=READINESS_TIMEOUT):
        try:
            if is_path:
                path = Path(manifest_path_or_content)
                if not path.is_absolute():
                    path = repo_root / path
                with open(path) as f:
                    docs = list(yaml.safe_load_all(f))
            else:
                docs = list(yaml.safe_load_all(manifest_path_or_content))
            docs = patch_namespace_in_docs(docs, test_namespace)
            k8s_utils.create_from_yaml(
                k8s_client,
                yaml_objects=docs,
                namespace=test_namespace,
            )
        except k8s_utils.FailToCreateError as e:
            msgs = [str(exc) for exc in e.api_exceptions]
            raise RuntimeError(f"Failed to create resources: {'; '.join(msgs)}") from e
        logger.info("Workload applied in namespace=%s, waiting for pods with selector=%s", test_namespace, label_selector)
        wait_for_pods_running(test_namespace, label_selector, timeout=timeout)
        logger.info("Pods ready in namespace=%s", test_namespace)
        return test_namespace

    return _deploy
