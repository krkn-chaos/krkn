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
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class RecoveryTimeStats:
    metric: str
    count: int = 0
    min_seconds: float = 0.0
    max_seconds: float = 0.0
    avg_seconds: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class RecoveryTimeSummary:
    not_ready_time: RecoveryTimeStats = field(
        default_factory=lambda: RecoveryTimeStats(metric="not_ready_time")
    )
    ready_time: RecoveryTimeStats = field(
        default_factory=lambda: RecoveryTimeStats(metric="ready_time")
    )
    stopped_time: RecoveryTimeStats = field(
        default_factory=lambda: RecoveryTimeStats(metric="stopped_time")
    )
    running_time: RecoveryTimeStats = field(
        default_factory=lambda: RecoveryTimeStats(metric="running_time")
    )

    def to_dict(self):
        return {
            "not_ready_time": self.not_ready_time.to_dict(),
            "ready_time": self.ready_time.to_dict(),
            "stopped_time": self.stopped_time.to_dict(),
            "running_time": self.running_time.to_dict(),
        }


def _stats_for(metric: str, values: List[float]) -> RecoveryTimeStats:
    non_zero = [v for v in values if v > 0.0]
    if not non_zero:
        return RecoveryTimeStats(metric=metric)
    return RecoveryTimeStats(
        metric=metric,
        count=len(non_zero),
        min_seconds=round(min(non_zero), 3),
        max_seconds=round(max(non_zero), 3),
        avg_seconds=round(sum(non_zero) / len(non_zero), 3),
    )


def build_recovery_time_summary(affected_nodes: list) -> Optional[RecoveryTimeSummary]:
    if not affected_nodes:
        return None

    not_ready, ready, stopped, running = [], [], [], []

    for node in affected_nodes:
        not_ready.append(float(getattr(node, "not_ready_time", 0.0) or 0.0))
        ready.append(float(getattr(node, "ready_time", 0.0) or 0.0))
        stopped.append(float(getattr(node, "stopped_time", 0.0) or 0.0))
        running.append(float(getattr(node, "running_time", 0.0) or 0.0))

    return RecoveryTimeSummary(
        not_ready_time=_stats_for("not_ready_time", not_ready),
        ready_time=_stats_for("ready_time", ready),
        stopped_time=_stats_for("stopped_time", stopped),
        running_time=_stats_for("running_time", running),
    )


def log_recovery_time_summary(action: str, summary: RecoveryTimeSummary) -> None:
    logging.info(
        "[recovery_time_summary] action=%s | "
        "not_ready: count=%d min=%.3fs max=%.3fs avg=%.3fs | "
        "ready: count=%d min=%.3fs max=%.3fs avg=%.3fs | "
        "stopped: count=%d min=%.3fs max=%.3fs avg=%.3fs | "
        "running: count=%d min=%.3fs max=%.3fs avg=%.3fs",
        action,
        summary.not_ready_time.count,
        summary.not_ready_time.min_seconds,
        summary.not_ready_time.max_seconds,
        summary.not_ready_time.avg_seconds,
        summary.ready_time.count,
        summary.ready_time.min_seconds,
        summary.ready_time.max_seconds,
        summary.ready_time.avg_seconds,
        summary.stopped_time.count,
        summary.stopped_time.min_seconds,
        summary.stopped_time.max_seconds,
        summary.stopped_time.avg_seconds,
        summary.running_time.count,
        summary.running_time.min_seconds,
        summary.running_time.max_seconds,
        summary.running_time.avg_seconds,
    )