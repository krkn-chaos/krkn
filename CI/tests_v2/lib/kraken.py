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
Kraken execution and config building fixtures for CI/tests_v2.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _kraken_cmd(config_path: str, repo_root: Path):
    """Use the same Python as the test process so venv/.venv and coverage match."""
    python = sys.executable
    if os.environ.get("KRKN_TEST_COVERAGE", "0") == "1":
        return [
            python, "-m", "coverage", "run", "-a",
            "run_kraken.py", "-c", str(config_path),
        ]
    return [python, "run_kraken.py", "-c", str(config_path)]


@pytest.fixture
def run_kraken(repo_root):
    """Run Kraken with the given config path. Returns CompletedProcess. Default timeout 300s."""

    def run(config_path, timeout=300, extra_args=None):
        cmd = _kraken_cmd(config_path, repo_root)
        if extra_args:
            cmd.extend(extra_args)
        return subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    return run


@pytest.fixture
def run_kraken_background(repo_root):
    """Start Kraken in background. Returns Popen. Call proc.terminate() or proc.wait() to stop."""

    def start(config_path):
        cmd = _kraken_cmd(config_path, repo_root)
        return subprocess.Popen(
            cmd,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    return start


@pytest.fixture
def build_config(repo_root, tmp_path):
    """
    Build a Kraken config from tests_v2's common_test_config.yaml with scenario_type and scenario_file
    substituted. Disables Prometheus/Elastic checks for local runs.
    Returns the path to the written config file.
    """
    common_path = repo_root / "CI" / "tests_v2" / "config" / "common_test_config.yaml"

    def _build(scenario_type: str, scenario_file: str, filename: str = "test_config.yaml"):
        content = common_path.read_text()
        content = content.replace("$scenario_type", scenario_type)
        content = content.replace("$scenario_file", scenario_file)
        content = content.replace("$post_config", "")

        config = yaml.safe_load(content)
        if "kraken" in config:
            # Disable status server so parallel test workers don't all bind to port 8081
            config["kraken"]["publish_kraken_status"] = False
        if "performance_monitoring" in config:
            config["performance_monitoring"]["check_critical_alerts"] = False
            config["performance_monitoring"]["enable_alerts"] = False
            config["performance_monitoring"]["enable_metrics"] = False
        if "elastic" in config:
            config["elastic"]["enable_elastic"] = False
        if "tunings" in config:
            config["tunings"]["wait_duration"] = 1

        out_path = tmp_path / filename
        with open(out_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        return str(out_path)

    return _build
