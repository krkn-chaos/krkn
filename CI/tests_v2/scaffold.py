#!/usr/bin/env python3
"""
Generate boilerplate for a new scenario test in CI/tests_v2.

Usage (from repository root):
  python CI/tests_v2/scaffold.py --scenario service_hijacking
  python CI/tests_v2/scaffold.py --scenario node_disruption --scenario-type node_scenarios

Creates (folder-per-scenario layout):
  - CI/tests_v2/scenarios/<scenario>/test_<scenario>.py (BaseScenarioTest subclass + stub test)
  - CI/tests_v2/scenarios/<scenario>/resource.yaml (placeholder workload)
  - CI/tests_v2/scenarios/<scenario>/scenario_base.yaml (placeholder Krkn scenario; edit for your scenario_type)
  - Prints the marker line to add to pytest.ini
"""

import argparse
import re
import sys
from pathlib import Path


def snake_to_camel(snake: str) -> str:
    """Convert snake_case to CamelCase."""
    return "".join(word.capitalize() for word in snake.split("_"))


def scenario_type_default(scenario: str) -> str:
    """Default scenario_type for build_config (e.g. service_hijacking -> service_hijacking_scenarios)."""
    return f"{scenario}_scenarios"


TEST_FILE_TEMPLATE = '''"""
Functional test for {scenario} scenario.
Each test runs in its own ephemeral namespace with workload deployed automatically.
"""

import copy
import pytest
import yaml

from lib.base import BaseScenarioTest, READINESS_TIMEOUT
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_success,
    assert_pod_count_unchanged,
    get_pods_list,
    load_scenario_base,
)


def _load_and_patch_scenario(repo_root, namespace: str, **overrides):
    """Load scenario_base.yaml and patch namespace and overrides. Adjust for your scenario structure."""
    scenario = copy.deepcopy(load_scenario_base(repo_root, "{scenario}"))
    # TODO: patch scenario with namespace and any overrides expected by your scenario_type
    return scenario


@pytest.mark.functional
@pytest.mark.{marker}
class Test{class_name}(BaseScenarioTest):
    """{scenario} scenario."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/{scenario}/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "app={app_label}"

    @pytest.mark.order(1)
    def test_happy_path(
        self, build_config, run_kraken, k8s_core, tmp_path, repo_root
    ):
        """Run {scenario} scenario and assert pods remain healthy."""
        ns = self.ns
        before = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)

        scenario_data = _load_and_patch_scenario(repo_root, ns)
        scenario_path = tmp_path / "{scenario}_scenario.yaml"
        with open(scenario_path, "w") as f:
            yaml.dump(scenario_data, f, default_flow_style=False, sort_keys=False)

        config_path = build_config(
            "{scenario_type}",
            str(scenario_path),
        )
        result = run_kraken(config_path)
        assert_kraken_success(result, context=f"namespace={{ns}}", tmp_path=tmp_path)

        after = get_pods_list(k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after, namespace=ns)
        assert_all_pods_running_and_ready(after, namespace=ns)
'''

RESOURCE_YAML_TEMPLATE = '''# Target workload for {scenario} scenario tests.
# Namespace is patched at deploy time by the test framework.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_label}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {app_label}
  template:
    metadata:
      labels:
        app: {app_label}
    spec:
      containers:
      - name: app
        image: nginx:alpine
        ports:
        - containerPort: 80
'''

SCENARIO_BASE_TEMPLATE = '''# Base scenario for {scenario} (used by build_config with scenario_type: {scenario_type}).
# Edit this file with the structure expected by Krkn. Tests load it and patch namespace/namespace_pattern.
# See scenarios/application_outage/scenario_base.yaml and scenarios/pod_disruption/scenario_base.yaml for examples.
placeholder:
  namespace: default
  # Add fields required by your scenario plugin.
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new scenario test in CI/tests_v2 (folder-per-scenario)")
    parser.add_argument(
        "--scenario",
        required=True,
        help="Scenario name in snake_case (e.g. service_hijacking)",
    )
    parser.add_argument(
        "--scenario-type",
        default=None,
        help="Kraken scenario_type for build_config (default: <scenario>_scenarios)",
    )
    args = parser.parse_args()

    scenario = args.scenario.strip().lower()
    if not re.match(r"^[a-z][a-z0-9_]*$", scenario):
        print("Error: --scenario must be snake_case (e.g. service_hijacking)", file=sys.stderr)
        return 1

    scenario_type = args.scenario_type or scenario_type_default(scenario)
    class_name = snake_to_camel(scenario)
    marker = scenario
    app_label = scenario.replace("_", "-")

    repo_root = Path(__file__).resolve().parent.parent.parent
    scenario_dir_path = repo_root / "CI" / "tests_v2" / "scenarios" / scenario
    test_path = scenario_dir_path / f"test_{scenario}.py"
    resource_path = scenario_dir_path / "resource.yaml"
    scenario_base_path = scenario_dir_path / "scenario_base.yaml"

    if scenario_dir_path.exists() and any(scenario_dir_path.iterdir()):
        print(f"Error: scenario directory already exists and is non-empty: {scenario_dir_path}", file=sys.stderr)
        return 1
    if test_path.exists():
        print(f"Error: {test_path} already exists", file=sys.stderr)
        return 1

    scenario_dir_path.mkdir(parents=True, exist_ok=True)

    test_content = TEST_FILE_TEMPLATE.format(
        scenario=scenario,
        marker=marker,
        class_name=class_name,
        app_label=app_label,
        scenario_type=scenario_type,
    )
    resource_content = RESOURCE_YAML_TEMPLATE.format(scenario=scenario, app_label=app_label)
    scenario_base_content = SCENARIO_BASE_TEMPLATE.format(
        scenario=scenario,
        scenario_type=scenario_type,
    )

    test_path.write_text(test_content, encoding="utf-8")
    resource_path.write_text(resource_content, encoding="utf-8")
    scenario_base_path.write_text(scenario_base_content, encoding="utf-8")

    print(f"Created: {test_path}")
    print(f"Created: {resource_path}")
    print(f"Created: {scenario_base_path}")
    print()
    print("Add this marker to CI/tests_v2/pytest.ini under 'markers':")
    print(f"    {marker}: marks a test as a {scenario} scenario test")
    print()
    print("Then edit scenario_base.yaml with your scenario structure and _load_and_patch_scenario in the test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
