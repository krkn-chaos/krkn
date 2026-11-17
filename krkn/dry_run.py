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
"""`--dry-run`: preview the targets of the configured scenarios.

Only `AbstractScenarioPlugin.preview_targets()` is ever called on a plugin,
never `run()`/`run_scenarios()`, so no chaos, rollback, telemetry upload or
health check is started. Plugins without a preview are reported as
unsupported instead of being simulated.
"""
import logging
import os
from collections import defaultdict

from krkn.scenario_config_parser import parse_scenario_config
from krkn.scenario_plugins.scenario_plugin_factory import (
    ScenarioPluginFactory,
    ScenarioPluginNotFound,
)


def run_dry_run(chaos_scenarios: list, kubecli, plugin_factory: ScenarioPluginFactory) -> int:
    """
    Logs the targets every configured scenario would hit.

    :return: 0 when every scenario was previewed and a real run would find
        enough targets, 1 otherwise (unsupported scenario, invalid config,
        Kubernetes API failure, not enough matching targets)
    """
    logging.info("DRY RUN: chaos execution disabled, no cluster resources will be modified")
    problems = 0
    total = 0

    for scenario in chaos_scenarios or []:
        try:
            scenario_type, scenarios_list, _ = parse_scenario_config(scenario)
        except Exception as e:
            logging.error("ERROR: invalid chaos_scenarios entry %r: %s", scenario, e)
            problems += 1
            continue
        if not isinstance(scenarios_list, list):
            logging.error("[%s] ERROR: expected a list of scenario files, got %r", scenario_type, scenarios_list)
            problems += 1
            continue
        if not scenarios_list:
            # The real run skips empty lists without creating the plugin.
            continue
        try:
            plugin = plugin_factory.create_plugin(scenario_type)
        except ScenarioPluginNotFound:
            logging.error("[%s] ERROR: no plugin found for this scenario type", scenario_type)
            problems += 1
            continue

        for scenario_file in scenarios_list:
            logging.info("")
            logging.info("Scenario: %s (%s)", scenario_file, scenario_type)
            if not isinstance(scenario_file, str) or not os.path.exists(scenario_file):
                logging.error("  ERROR: scenario file not found: %s", scenario_file)
                problems += 1
                continue
            try:
                previews = plugin.preview_targets(scenario_file, kubecli)
            except NotImplementedError:
                logging.warning(
                    "  UNSUPPORTED: dry-run is not implemented for %s, its targets were NOT previewed",
                    scenario_type,
                )
                problems += 1
                continue
            except ValueError as e:
                logging.error("  ERROR: invalid scenario configuration: %s", e)
                problems += 1
                continue
            except Exception as e:
                logging.error("  ERROR: target discovery failed: %s", e)
                problems += 1
                continue

            for preview in previews:
                total += _log_preview(preview)
                problems += len(preview["issues"])

    logging.info("")
    logging.info("Total matched workloads: %d", total)
    logging.info("No chaos actions were executed.")
    rc = 1 if problems else 0
    if problems:
        logging.error("DRY RUN found %d problem(s), see above", problems)
    logging.info("DRY RUN exit code: %d", rc)
    return rc


def _log_preview(preview: dict) -> int:
    if preview["id"]:
        logging.info("  Entry: %s", preview["id"])
    logging.info("  Matching criteria:")
    for key, value in preview["criteria"].items():
        logging.info("    %s: %s", key, value)

    targets = preview["targets"]
    if not targets:
        logging.warning("  No workloads matched")
    else:
        logging.info(
            "  Matched targets (%d would be picked at random):", preview["count"]
        )
        by_namespace = defaultdict(list)
        for name, namespace in targets:
            by_namespace[namespace].append(name)
        for namespace in sorted(by_namespace):
            logging.info("    Namespace: %s", namespace)
            for name in sorted(by_namespace[namespace]):
                logging.info("      - %s", name)
    for issue in preview["issues"]:
        logging.error("  PROBLEM: %s", issue)
    return len(targets)
