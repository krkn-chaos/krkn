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
Shared fixtures for pytest functional tests (CI/tests_v2).
Tests must be run from the repository root so run_kraken.py and config paths resolve.
"""

import logging
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--keep-ns-on-fail",
        action="store_true",
        default=False,
        help="Don't delete test namespaces on failure (for debugging)",
    )
    parser.addoption(
        "--require-kind",
        action="store_true",
        default=False,
        help="Skip tests unless current context is a known dev cluster (kind, minikube)",
    )


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def _repo_root() -> Path:
    """Repository root (directory containing run_kraken.py and CI/)."""
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def repo_root():
    return _repo_root()


@pytest.fixture(scope="session", autouse=True)
def _configure_logging():
    """Set log format with timestamps for test runs."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )


# Re-export fixtures from lib modules so pytest discovers them
from lib.deploy import deploy_workload, wait_for_pods_running  # noqa: E402, F401
from lib.kraken import build_config, run_kraken, run_kraken_background  # noqa: E402, F401
from lib.k8s import (  # noqa: E402, F401
    _kube_config_loaded,
    _log_cluster_context,
    k8s_apps,
    k8s_client,
    k8s_core,
    k8s_networking,
    kubectl,
)
from lib.namespace import _cleanup_stale_namespaces, test_namespace  # noqa: E402, F401
from lib.preflight import _preflight_checks  # noqa: E402, F401
