"""
Base class for CI/tests_v2 scenario tests.
Encapsulates the shared lifecycle: ephemeral namespace, optional workload deploy, teardown.
"""

import copy
import logging
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from lib.utils import load_scenario_base

logger = logging.getLogger(__name__)


def _get_nested(obj, path):
    """Walk path (list of keys/indices) and return the value. Supports list and dict."""
    for key in path:
        obj = obj[key]
    return obj


def _set_nested(obj, path, value):
    """Walk path to the parent and set the last key to value."""
    if not path:
        return
    parent_path, last_key = path[:-1], path[-1]
    parent = obj
    for key in parent_path:
        parent = parent[key]
    parent[last_key] = value


# Timeout constants (seconds). Override via env vars (e.g. KRKN_TEST_READINESS_TIMEOUT).
# Coordinate with pytest-timeout budget (e.g. 300s).
TIMEOUT_BUDGET = int(os.environ.get("KRKN_TEST_TIMEOUT_BUDGET", "300"))
DEPLOY_TIMEOUT = int(os.environ.get("KRKN_TEST_DEPLOY_TIMEOUT", "90"))
READINESS_TIMEOUT = int(os.environ.get("KRKN_TEST_READINESS_TIMEOUT", "90"))
NS_CLEANUP_TIMEOUT = int(os.environ.get("KRKN_TEST_NS_CLEANUP_TIMEOUT", "60"))
POLICY_WAIT_TIMEOUT = int(os.environ.get("KRKN_TEST_POLICY_WAIT_TIMEOUT", "30"))
KRAKEN_PROC_WAIT_TIMEOUT = int(os.environ.get("KRKN_TEST_KRAKEN_PROC_WAIT_TIMEOUT", "60"))


class BaseScenarioTest:
    """
    Base class for scenario tests. Subclasses set:
    - WORKLOAD_MANIFEST: path (str), or callable(namespace) -> YAML str for inline manifest
    - WORKLOAD_IS_PATH: True if WORKLOAD_MANIFEST is a file path, False if inline YAML
    - LABEL_SELECTOR: label selector for pods to wait on (e.g. "app=my-target")
    - SCENARIO_NAME: e.g. "pod_disruption", "application_outage"
    - SCENARIO_TYPE: e.g. "pod_disruption_scenarios", "application_outages_scenarios"
    - NAMESPACE_KEY_PATH: path to namespace field, e.g. [0, "config", "namespace_pattern"] or ["application_outage", "namespace"]
    - NAMESPACE_IS_REGEX: True to wrap namespace in ^...$
    - OVERRIDES_KEY_PATH: path to dict for **overrides (e.g. ["application_outage"]), or [] if none
    """

    WORKLOAD_MANIFEST = None
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = None
    SCENARIO_NAME = ""
    SCENARIO_TYPE = ""
    NAMESPACE_KEY_PATH = []
    NAMESPACE_IS_REGEX = False
    OVERRIDES_KEY_PATH = []

    @pytest.fixture(autouse=True)
    def _inject_common_fixtures(
        self,
        repo_root,
        tmp_path,
        build_config,
        run_kraken,
        run_kraken_background,
        k8s_core,
        k8s_apps,
        k8s_networking,
        k8s_client,
    ):
        """Inject common fixtures onto self so test methods don't need to declare them."""
        self.repo_root = repo_root
        self.tmp_path = tmp_path
        self.build_config = build_config
        self.run_kraken = run_kraken
        self.run_kraken_background = run_kraken_background
        self.k8s_core = k8s_core
        self.k8s_apps = k8s_apps
        self.k8s_networking = k8s_networking
        self.k8s_client = k8s_client
        yield

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

    def load_and_patch_scenario(self, repo_root, namespace, **overrides):
        """Load scenario_base.yaml and patch namespace (and overrides). Returns the scenario structure."""
        scenario = copy.deepcopy(load_scenario_base(repo_root, self.SCENARIO_NAME))
        ns_value = f"^{namespace}$" if self.NAMESPACE_IS_REGEX else namespace
        if self.NAMESPACE_KEY_PATH:
            _set_nested(scenario, self.NAMESPACE_KEY_PATH, ns_value)
        if overrides and self.OVERRIDES_KEY_PATH:
            target = _get_nested(scenario, self.OVERRIDES_KEY_PATH)
            for key, value in overrides.items():
                target[key] = value
        return scenario

    def write_scenario(self, tmp_path, scenario_data, suffix=""):
        """Write scenario data to a YAML file in tmp_path. Returns the path."""
        filename = f"{self.SCENARIO_NAME}_scenario{suffix}.yaml"
        path = tmp_path / filename
        path.write_text(yaml.dump(scenario_data, default_flow_style=False, sort_keys=False))
        return path

    def run_scenario(self, tmp_path, namespace, *, overrides=None, config_filename=None):
        """Load, patch, write scenario; build config; run Kraken. Returns CompletedProcess."""
        scenario = self.load_and_patch_scenario(self.repo_root, namespace, **(overrides or {}))
        scenario_path = self.write_scenario(tmp_path, scenario)
        config_path = self.build_config(
            self.SCENARIO_TYPE,
            str(scenario_path),
            filename=config_filename or "test_config.yaml",
        )
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
            logger.info(
                "[dry-run] Would run Kraken with config=%s, scenario=%s",
                config_path,
                scenario_path,
            )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="[dry-run] skipped", stderr=""
            )
        return self.run_kraken(config_path)
