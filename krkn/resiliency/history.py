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

"""Historical resiliency-score queries.

Provides helpers to parse a CLI time-window (duration string or explicit
start/end timestamps), query Prometheus over that window, and populate the
overall_resiliency_report field of a ChaosRunTelemetry object.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Optional

from krkn_lib.models.k8s import ResiliencyReport
from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus

from krkn.resiliency.resiliency import Resiliency


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_duration(duration_str: str) -> datetime.timedelta:
    """Parse a human-friendly duration string into a timedelta.

    Supported units: s (seconds), m (minutes), h (hours), d (days), w (weeks).
    Examples: '30s', '5m', '24h', '7d', '2w'
    """
    units = {
        's': 'seconds',
        'm': 'minutes',
        'h': 'hours',
        'd': 'days',
        'w': 'weeks',
    }
    s = duration_str.strip().lower()
    if len(s) < 2:
        raise ValueError(
            f"Invalid duration '{duration_str}': expected a number followed by a unit (s, m, h, d, w)"
        )
    unit = s[-1]
    if unit not in units:
        raise ValueError(
            f"Unknown duration unit '{unit}' in '{duration_str}'. Supported units: s, m, h, d, w"
        )
    try:
        value = float(s[:-1])
    except ValueError:
        raise ValueError(f"Invalid numeric value '{s[:-1]}' in '{duration_str}'")
    if value <= 0:
        raise ValueError(f"Duration must be positive, got '{duration_str}'")
    return datetime.timedelta(**{units[unit]: value})


def parse_datetime(dt_str: str) -> datetime.datetime:
    """Parse a datetime string into a UTC-aware datetime object.

    The input is always interpreted as UTC regardless of the host timezone.

    Supported formats:
      YYYY-MM-DDTHH:MM:SS   (ISO 8601)
      YYYY-MM-DD HH:MM:SS
      YYYY-MM-DD            (midnight assumed)
    """
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            naive = datetime.datetime.strptime(dt_str.strip(), fmt)
            return naive.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    raise ValueError(
        f"Cannot parse datetime '{dt_str}'. "
        "Use ISO 8601 format: YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD (times are UTC)"
    )


# ---------------------------------------------------------------------------
# Window representation
# ---------------------------------------------------------------------------

@dataclass
class HistoryWindow:
    """A resolved start/end time window for a historical resiliency query."""
    start: datetime.datetime
    end: datetime.datetime
    label: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_history_window(
    past_resiliency_score: Optional[str],
    hist_start_str: Optional[str],
    hist_end_str: Optional[str],
    resiliency_score_flag: bool = False,
) -> Optional[HistoryWindow]:
    """Parse and validate historical resiliency CLI options.

    Returns a :class:`HistoryWindow` when any window option was provided, or
    ``None`` when none were supplied (normal chaos run).

    Args:
        past_resiliency_score: Trailing duration string (e.g. '1h', '24h').
        hist_start_str: Explicit window start datetime string.
        hist_end_str: Explicit window end datetime string.
        resiliency_score_flag: Must be ``True`` when using ``--start-time``/
            ``--end-time``; set by the ``--resiliency-score`` flag or the
            ``resiliency-score`` command.

    Raises:
        ValueError: with a human-readable message when options are invalid.
    """
    if past_resiliency_score is not None and (hist_start_str or hist_end_str):
        raise ValueError(
            "--past-resiliency-score and --start-time/--end-time are mutually exclusive"
        )

    if (hist_start_str or hist_end_str) and not resiliency_score_flag:
        raise ValueError(
            "--start-time/--end-time require the --resiliency-score flag "
            "or the resiliency-score command"
        )

    if past_resiliency_score is not None:
        duration = parse_duration(past_resiliency_score)
        end = datetime.datetime.now(datetime.timezone.utc)
        start = end - duration
        return HistoryWindow(start=start, end=end, label=past_resiliency_score)

    if hist_start_str or hist_end_str:
        if not hist_start_str or not hist_end_str:
            raise ValueError("--start-time and --end-time must both be provided together")
        start = parse_datetime(hist_start_str)
        end = parse_datetime(hist_end_str)
        if end <= start:
            raise ValueError("--end-time must be after --start-time")
        return HistoryWindow(start=start, end=end, label=f"{start} → {end}")

    return None


def apply_historical_resiliency(
    window: HistoryWindow,
    resiliency_obj: Resiliency,
    prometheus: KrknPrometheus,
    telemetry: ChaosRunTelemetry,
) -> None:
    """Query Prometheus over *window* and populate ``telemetry.overall_resiliency_report``.

    Raises:
        RuntimeError: when Prometheus or the resiliency object is unavailable.
    """
    if resiliency_obj is None or prometheus is None:
        raise RuntimeError(
            "Prometheus is required for historical resiliency scoring but is not available. "
            "Ensure prometheus_url is set in config and Prometheus is reachable."
        )

    logging.info(
        "Querying historical resiliency score for window %s → %s", window.start, window.end
    )
    resiliency_obj.add_scenario_report(
        scenario_name="historical",
        prom_cli=prometheus,
        start_time=window.start,
        end_time=window.end,
    )
    hist_report = resiliency_obj.scenario_reports[-1]
    hist_score = hist_report["score"]
    hist_breakdown = hist_report.get("breakdown", {})
    passed = hist_breakdown.get("passed", 0)
    total = passed + hist_breakdown.get("failed", 0)
    history_summary = {
        "scenarios": {"historical": hist_score},
        "resiliency_score": hist_score,
        "passed_slos": passed,
        "total_slos": total,
    }
    telemetry.overall_resiliency_report = ResiliencyReport(
        json_object=history_summary,
        resiliency_score=hist_score,
        passed_slos=passed,
        total_slos=total,
    )
    logging.info("Historical resiliency score (%s): %d", window.label, hist_score)
