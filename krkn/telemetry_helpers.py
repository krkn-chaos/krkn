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

"""Telemetry collection and transformation helpers."""

import queue
from datetime import datetime
from typing import Any, Tuple, List, Dict

from krkn_lib.models.telemetry.models import HealthCheck, ObjectStateCheck


def collect_health_check_telemetry(
    tq: queue.Queue,
) -> Tuple[List[HealthCheck], List[ObjectStateCheck]]:
    """
    Collect and separate health check telemetry from a queue by type.

    Handles both list and single-item enqueuing from different plugins.
    Separates HealthCheck from ObjectStateCheck records for proper routing.

    :param tq: queue containing telemetry data
    :return: tuple of (health_checks, object_state_checks)
    """
    health_checks = []
    object_state_checks = []

    while True:
        try:
            telemetry_data = tq.get_nowait()
        except queue.Empty:
            break

        # Normalize to list (some plugins enqueue lists, some enqueue single items)
        if isinstance(telemetry_data, list):
            items = telemetry_data
        else:
            items = [telemetry_data]

        # Separate by type
        for item in items:
            if isinstance(item, dict):
                # String items - pass through as-is
                health_checks.append(item)
            elif hasattr(item, 'check_name') and hasattr(item, 'kind'):
                # ObjectStateCheck
                object_state_checks.append(item)
            else:
                # HealthCheck or other
                health_checks.append(item)

    return health_checks, object_state_checks


def group_checks_by_phase(checks: List[Any]) -> Dict[str, List[Any]]:
    """
    Group health check records by phase.

    :param checks: list of health check records (dicts or objects with 'phase' attribute)
    :return: dict with phase as key, list of checks as value
    """
    checks_by_phase = {}
    for check in checks:
        if isinstance(check, dict):
            phase = check.get("phase", "during")
        else:
            phase = getattr(check, "phase", "during")

        if phase not in checks_by_phase:
            checks_by_phase[phase] = []
        checks_by_phase[phase].append(check)

    return checks_by_phase


def build_telemetry_record(
    base_data: Dict[str, Any],
    status: bool,
    start_timestamp: datetime,
    end_timestamp: datetime = None,
    phase: str = "during",
    duration: float = None,
) -> Dict[str, Any]:
    """
    Build a standardized telemetry record with timestamps and duration.

    :param base_data: base fields (url, check_name, vm_name, etc.)
    :param status: boolean status of the check
    :param start_timestamp: check start time (datetime or string)
    :param end_timestamp: check end time (datetime or string); defaults to now
    :param phase: check phase ("pre", "during", "post")
    :param duration: duration in seconds; calculated if not provided
    :return: complete telemetry record dict
    """
    if end_timestamp is None:
        end_timestamp = datetime.now()

    # Convert to ISO format if datetime objects
    if isinstance(start_timestamp, datetime):
        start_iso = start_timestamp.isoformat()
    else:
        start_iso = str(start_timestamp)

    if isinstance(end_timestamp, datetime):
        end_iso = end_timestamp.isoformat()
        if duration is None and isinstance(start_timestamp, datetime):
            duration = (end_timestamp - start_timestamp).total_seconds()
    else:
        end_iso = str(end_timestamp)

    if duration is None:
        duration = 0.0

    record = {
        **base_data,
        "status": status,
        "start_timestamp": start_iso,
        "end_timestamp": end_iso,
        "duration": duration,
        "phase": phase,
    }

    return record
