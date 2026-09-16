# Copyright 2026 The Krkn Authors
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


#!/usr/bin/env python
"""
Scenario configuration parser for weighted scenarios.

This module provides utilities to parse scenario configurations from the chaos_scenarios
config, supporting multiple formats:
1. Explicit format: {scenario_type: str, weight: float, files: []}
2. Weighted format: {scenario_type: {weight: float, files: []}}
3. Old format: {scenario_type: [files]}
"""

import logging
from typing import Tuple, List, Any


def parse_scenario_config(scenario: dict) -> Tuple[str, List[str], float]:
    """
    Parse a scenario configuration entry and extract type, files, and weight.

    Supports three config formats:
    1. Explicit format: {scenario_type: str, weight: N, files: [...]}
    2. Weighted format: {scenario_type: {weight: N, files: [...]}}
    3. Old format: {scenario_type: [...]} (backward compatible)

    Args:
        scenario: Dictionary containing scenario configuration

    Returns:
        Tuple of (scenario_type, scenarios_list, scenario_weight)
        - scenario_type: string identifier for the scenario plugin
        - scenarios_list: list of scenario file paths
        - scenario_weight: validated numeric weight (>0), defaults to 1

    Examples:
        >>> # Weighted format
        >>> parse_scenario_config({
        ...     "pod_disruption_scenarios": {
        ...         "weight": 3,
        ...         "files": ["scenarios/openshift/etcd.yml"]
        ...     }
        ... })
        ('pod_disruption_scenarios', ['scenarios/openshift/etcd.yml'], 3.0)

        >>> # Old format
        >>> parse_scenario_config({
        ...     "hog_scenarios": ["scenarios/kube/cpu-hog.yml"]
        ... })
        ('hog_scenarios', ['scenarios/kube/cpu-hog.yml'], 1.0)

        >>> # Explicit format
        >>> parse_scenario_config({
        ...     "scenario_type": "service_disruption_scenarios",
        ...     "weight": 2,
        ...     "files": ["scenarios/openshift/regex_namespace.yaml"]
        ... })
        ('service_disruption_scenarios', ['scenarios/openshift/regex_namespace.yaml'], 2.0)
    """
    # Support multiple config formats:
    # 1. New explicit format: {scenario_type: str, weight: float, files: []}
    # 2. Extended old format: {scenario_type: {weight: float, files: []}}
    # 3. Old format: {scenario_type: [files]}
    if "scenario_type" in scenario and "files" in scenario:
        # Format 1: New explicit format
        scenario_type = scenario["scenario_type"]
        scenarios_list = scenario["files"]
        scenario_weight = scenario.get("weight", 1)
    else:
        # Formats 2 & 3: Old-style with scenario_type as key
        scenario_type = list(scenario.keys())[0]
        scenario_value = scenario[scenario_type]

        if isinstance(scenario_value, dict):
            # Format 2: Extended old format with weight and files
            scenarios_list = scenario_value.get("files", [])
            scenario_weight = scenario_value.get("weight", 1)
        else:
            # Format 3: Old format - simple list of files
            scenarios_list = scenario_value
            scenario_weight = 1

    # Validate weight: must be numeric and positive
    scenario_weight = _validate_weight(scenario_weight, scenario_type)

    return scenario_type, scenarios_list, scenario_weight


def _validate_weight(weight: Any, scenario_type: str) -> float:
    """
    Validate and normalize a scenario weight value.

    Args:
        weight: Raw weight value from config (could be any type)
        scenario_type: Scenario type name for logging

    Returns:
        Validated float weight (>0), defaults to 1.0 if invalid

    Validation rules:
    - Must be numeric (int, float, or numeric string)
    - Must be > 0 (positive)
    - Invalid values default to 1.0 with a warning
    """
    try:
        weight_float = float(weight)
        if weight_float <= 0:
            logging.warning(
                f"Invalid weight {weight_float} for scenario '{scenario_type}' "
                f"(must be > 0). Using default weight=1"
            )
            return 1.0
        return weight_float
    except (TypeError, ValueError):
        logging.warning(
            f"Invalid weight type '{weight}' for scenario '{scenario_type}' "
            f"(must be numeric). Using default weight=1"
        )
        return 1.0


def extract_scenario_types(chaos_scenarios: List[dict]) -> set:
    """
    Extract unique scenario types from a list of scenario configurations.

    Used for plugin validation logging.

    Args:
        chaos_scenarios: List of scenario configuration dictionaries

    Returns:
        Set of scenario type strings

    Examples:
        >>> scenarios = [
        ...     {"pod_disruption_scenarios": {"weight": 3, "files": ["etcd.yml"]}},
        ...     {"hog_scenarios": ["cpu-hog.yml"]}
        ... ]
        >>> extract_scenario_types(scenarios)
        {'pod_disruption_scenarios', 'hog_scenarios'}
    """
    configured_types = set()
    for scenario in chaos_scenarios:
        if isinstance(scenario, dict):
            # Parse scenario type using same logic as execution loop
            if "scenario_type" in scenario and "files" in scenario:
                # Explicit format: {scenario_type: str, weight: N, files: []}
                configured_types.add(scenario["scenario_type"])
            else:
                # Old/weighted format: {scenario_type: ...}
                configured_types.add(list(scenario.keys())[0])
    return configured_types
