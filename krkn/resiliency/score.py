from __future__ import annotations

from typing import Dict, List, Tuple

DEFAULT_WEIGHTS = {"critical": 3, "warning": 1}


class SLOResult:
    """Simple container representing evaluation outcome for a single SLO."""

    def __init__(self, name: str, severity: str, passed: bool):
        self.name = name
        self.severity = severity
        self.passed = passed

    def weight(self, weights: Dict[str, int] | None = None) -> int:
        _w = weights or DEFAULT_WEIGHTS
        return _w.get(self.severity, DEFAULT_WEIGHTS["warning"])


def calculate_resiliency_score(
    slo_definitions: Dict[str, str],
    prometheus_results: Dict[str, bool],
    health_check_results: Dict[str, bool],
    weights: Dict[str, int] | None = None,
) -> Tuple[int, Dict[str, int]]:
    """Compute a resiliency score between 0-100 based on SLO pass/fail results.

    Args:
        slo_definitions: Mapping of SLO name -> severity ("critical" | "warning").
        prometheus_results: Mapping of SLO name -> bool indicating whether the SLO
            passed. Any SLO missing in this mapping is treated as failed.
        health_check_results: Mapping of custom health-check name -> bool pass flag.
            These checks are always treated as *critical*.
        weights: Optional override of severity weights.

    Returns:
        Tuple containing (final_score, breakdown) where *breakdown* is a dict with
        the counts of passed/failed SLOs per severity.
    """

    weights = weights or DEFAULT_WEIGHTS

    slo_objects: List[SLOResult] = []
    for slo_name, severity in slo_definitions.items():
        # Exclude SLOs that were not evaluated (query returned no data)
        if slo_name not in prometheus_results:
            continue
        passed = bool(prometheus_results[slo_name])
        slo_objects.append(SLOResult(slo_name, severity, passed))

    # Health-check SLOs (by default keeping them critical)
    for hc_name, hc_passed in health_check_results.items():
        slo_objects.append(SLOResult(hc_name, "critical", bool(hc_passed)))

    total_points = sum(slo.weight(weights) for slo in slo_objects)
    points_lost = sum(slo.weight(weights) for slo in slo_objects if not slo.passed)

    score = 0 if total_points == 0 else int(((total_points - points_lost) / total_points) * 100)

    breakdown = {
        "total_points": total_points,
        "points_lost": points_lost,
        "passed": len([s for s in slo_objects if s.passed]),
        "failed": len([s for s in slo_objects if not s.passed]),
    }
    return score, breakdown
