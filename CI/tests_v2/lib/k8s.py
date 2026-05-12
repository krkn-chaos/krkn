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
Kubernetes client fixtures and cluster context checks for CI/tests_v2.
"""

import logging
import subprocess
from pathlib import Path

import pytest
from kubernetes import client, config

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def _kube_config_loaded():
    """Load kubeconfig once per session. Skips if cluster unreachable."""
    try:
        config.load_kube_config()
        logger.info("Kube config loaded successfully")
    except config.ConfigException as e:
        logger.warning("Could not load kube config: %s", e)
        pytest.skip(f"Could not load kube config (is a cluster running?): {e}")


@pytest.fixture(scope="session")
def k8s_core(_kube_config_loaded):
    """Kubernetes CoreV1Api for pods, etc. Uses default kubeconfig."""
    return client.CoreV1Api()


@pytest.fixture(scope="session")
def k8s_networking(_kube_config_loaded):
    """Kubernetes NetworkingV1Api for network policies."""
    return client.NetworkingV1Api()


@pytest.fixture(scope="session")
def k8s_client(_kube_config_loaded):
    """Kubernetes ApiClient for create_from_yaml and other generic API calls."""
    return client.ApiClient()


@pytest.fixture(scope="session")
def k8s_apps(_kube_config_loaded):
    """Kubernetes AppsV1Api for deployment status polling."""
    return client.AppsV1Api()


@pytest.fixture(scope="session", autouse=True)
def _log_cluster_context(request):
    """Log current cluster context at session start; skip if --require-kind and not a dev cluster."""
    try:
        contexts, active = config.list_kube_config_contexts()
    except Exception as e:
        logger.warning("Could not list kube config contexts: %s", e)
        return
    if not active:
        return
    context_name = active.get("name", "?")
    cluster = (active.get("context") or {}).get("cluster", "?")
    logger.info("Running tests against cluster: context=%s cluster=%s", context_name, cluster)
    if not request.config.getoption("--require-kind", False):
        return
    cluster_lower = (cluster or "").lower()
    if "kind" in cluster_lower or "minikube" in cluster_lower:
        return
    pytest.skip(
        f"Cluster '{cluster}' does not look like kind/minikube. "
        "Use default kubeconfig or pass --require-kind only on dev clusters."
    )


@pytest.fixture
def kubectl(repo_root):
    """Run kubectl with given args from repo root. Returns CompletedProcess."""

    def run(args, timeout=120):
        cmd = ["kubectl"] + (args if isinstance(args, list) else list(args))
        return subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    return run
