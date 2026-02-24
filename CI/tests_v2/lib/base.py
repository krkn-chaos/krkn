"""
Base class for CI/tests_v2 scenario tests.
Encapsulates the shared lifecycle: ephemeral namespace, optional workload deploy, teardown.
"""

import logging
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


# Timeout constants (seconds). Coordinate with pytest-timeout budget (e.g. 300s).
TIMEOUT_BUDGET = 300
DEPLOY_TIMEOUT = 90
READINESS_TIMEOUT = 90
NS_CLEANUP_TIMEOUT = 60
POLICY_WAIT_TIMEOUT = 30
KRAKEN_PROC_WAIT_TIMEOUT = 60


class BaseScenarioTest:
    """
    Base class for scenario tests. Subclasses set:
    - WORKLOAD_MANIFEST: path (str), or callable(namespace) -> YAML str for inline manifest
    - WORKLOAD_IS_PATH: True if WORKLOAD_MANIFEST is a file path, False if inline YAML
    - LABEL_SELECTOR: label selector for pods to wait on (e.g. "app=my-target")
    """

    WORKLOAD_MANIFEST = None
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = None

    @pytest.fixture(autouse=True)
    def _setup_workload(self, request, repo_root):
        if "no_workload" in request.keywords:
            request.instance.ns = request.getfixturevalue("test_namespace")
            logger.debug("no_workload marker: skipping workload deploy, ns=%s", request.instance.ns)
            yield
            return
        deploy = request.getfixturevalue("deploy_workload")
        test_namespace = request.getfixturevalue("test_namespace")
        manifest = self.WORKLOAD_MANIFEST
        if callable(manifest):
            manifest = manifest(test_namespace)
            is_path = False
            logger.info("Deploying inline workload in ns=%s, label_selector=%s", test_namespace, self.LABEL_SELECTOR)
        else:
            is_path = self.WORKLOAD_IS_PATH
            if is_path and manifest and not Path(manifest).is_absolute():
                manifest = repo_root / manifest
            logger.info("Deploying workload from %s in ns=%s, label_selector=%s", manifest, test_namespace, self.LABEL_SELECTOR)
        ns = deploy(manifest, self.LABEL_SELECTOR, is_path=is_path, timeout=DEPLOY_TIMEOUT)
        request.instance.ns = ns
        yield
