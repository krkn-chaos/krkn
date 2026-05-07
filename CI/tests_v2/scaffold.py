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
Generate boilerplate for a new scenario test in CI/tests_v2.

Usage (from repository root):
  python CI/tests_v2/scaffold.py --scenario service_hijacking
  python CI/tests_v2/scaffold.py --scenario node_disruption --scenario-type node_scenarios

Creates (folder-per-scenario layout):
  - CI/tests_v2/scenarios/<scenario>/test_<scenario>.py (BaseScenarioTest subclass + stub test)
  - CI/tests_v2/scenarios/<scenario>/resource.yaml (placeholder workload)
  - CI/tests_v2/scenarios/<scenario>/scenario_base.yaml (placeholder Krkn scenario; edit for your scenario_type)
  - Adds the scenario marker to pytest.ini (if not already present)
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

import pytest

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_failure,
    assert_kraken_success,
    assert_pod_count_unchanged,
    get_pods_list,
)


@pytest.mark.functional
@pytest.mark.{marker}
class Test{class_name}(BaseScenarioTest):
    """{scenario} scenario."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/{scenario}/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "app={app_label}"
    SCENARIO_NAME = "{scenario}"
    SCENARIO_TYPE = "{scenario_type}"
    NAMESPACE_KEY_PATH = {namespace_key_path}
    NAMESPACE_IS_REGEX = {namespace_is_regex}
    OVERRIDES_KEY_PATH = {overrides_key_path}

    @pytest.mark.order(1)
    def test_happy_path(self):
        """Run {scenario} scenario and assert pods remain healthy."""
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)

        result = self.run_scenario(self.tmp_path, ns)
        assert_kraken_success(result, context=f"namespace={{ns}}", tmp_path=self.tmp_path)

        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
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

SCENARIO_BASE_DICT_TEMPLATE = '''# Base scenario for {scenario} (used by build_config with scenario_type: {scenario_type}).
# Edit this file with the structure expected by Krkn. Top-level key must match SCENARIO_NAME.
# See scenarios/application_outage/scenario_base.yaml and scenarios/pod_disruption/scenario_base.yaml for examples.
{scenario}:
  namespace: default
  # Add fields required by your scenario plugin.
'''

SCENARIO_BASE_LIST_TEMPLATE = '''# Base scenario for {scenario} (list format). Tests patch config.namespace_pattern with ^<ns>$.
# Edit with the structure expected by your scenario plugin. See scenarios/pod_disruption/scenario_base.yaml.
- id: {scenario}-default
  config:
    namespace_pattern: "^default$"
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
    parser.add_argument(
        "--list-based",
        action="store_true",
        help="Use list-based scenario (NAMESPACE_KEY_PATH [0, 'config', 'namespace_pattern'], OVERRIDES_KEY_PATH [0, 'config'])",
    )
    parser.add_argument(
        "--regex-namespace",
        action="store_true",
        help="Set NAMESPACE_IS_REGEX = True (namespace wrapped in ^...$)",
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

    if args.list_based:
        namespace_key_path = [0, "config", "namespace_pattern"]
        namespace_is_regex = True
        overrides_key_path = [0, "config"]
        scenario_base_template = SCENARIO_BASE_LIST_TEMPLATE
    else:
        namespace_key_path = [scenario, "namespace"]
        namespace_is_regex = args.regex_namespace
        overrides_key_path = [scenario]
        scenario_base_template = SCENARIO_BASE_DICT_TEMPLATE

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
        namespace_key_path=repr(namespace_key_path),
        namespace_is_regex=namespace_is_regex,
        overrides_key_path=repr(overrides_key_path),
    )
    resource_content = RESOURCE_YAML_TEMPLATE.format(scenario=scenario, app_label=app_label)
    scenario_base_content = scenario_base_template.format(
        scenario=scenario,
        scenario_type=scenario_type,
    )

    test_path.write_text(test_content, encoding="utf-8")
    resource_path.write_text(resource_content, encoding="utf-8")
    scenario_base_path.write_text(scenario_base_content, encoding="utf-8")

    # Auto-add marker to pytest.ini if not already present
    pytest_ini_path = repo_root / "CI" / "tests_v2" / "pytest.ini"
    marker_line = f"    {marker}: marks a test as a {scenario} scenario test"
    if pytest_ini_path.exists():
        content = pytest_ini_path.read_text(encoding="utf-8")
        if f"    {marker}:" not in content and f"{marker}: marks" not in content:
            lines = content.splitlines(keepends=True)
            insert_at = None
            for i, line in enumerate(lines):
                if re.match(r"^    \w+:\s*.+", line):
                    insert_at = i + 1
            if insert_at is not None:
                lines.insert(insert_at, marker_line + "\n")
                pytest_ini_path.write_text("".join(lines), encoding="utf-8")
                print("Added marker to pytest.ini")
            else:
                print("Could not find markers block in pytest.ini; add manually:")
                print(marker_line)
        else:
            print("Marker already in pytest.ini")
    else:
        print("pytest.ini not found; add this marker under 'markers':")
        print(marker_line)

    print(f"Created: {test_path}")
    print(f"Created: {resource_path}")
    print(f"Created: {scenario_base_path}")
    print()
    print("Then edit scenario_base.yaml with your scenario structure (top-level key should match SCENARIO_NAME).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
