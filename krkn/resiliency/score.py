from __future__ import annotations

from typing import Dict, List, Tuple

DEFAULT_WEIGHTS = {"critical": 3, "warning": 1}


class SLOResult:
    """Simple container representing evaluation outcome for a single SLO."""

    def __init__(self, name: str, severity: str, passed: bool, weight: int | None = None):
        self.name = name
        self.severity = severity
        self.passed = passed
        self._custom_weight = weight

    def weight(self, severity_weights: Dict[str, int]) -> int:
        """Return the weight for this SLO. Uses custom weight if set, otherwise uses severity-based weight."""
        if self._custom_weight is not None:
            return self._custom_weight
        return severity_weights.get(self.severity, severity_weights.get("warning", 1))


def calculate_resiliency_score(
    slo_definitions: Dict[str, str] | Dict[str, Dict[str, int | str | None]],
    prometheus_results: Dict[str, bool],
    health_check_results: Dict[str, bool],
) -> Tuple[int, Dict[str, int]]:
    """Compute a resiliency score between 0-100 based on SLO pass/fail results.

    Args:
        slo_definitions: Mapping of SLO name -> severity ("critical" | "warning") OR
            SLO name -> {"severity": str, "weight": int | None}.
        prometheus_results: Mapping of SLO name -> bool indicating whether the SLO
            passed. Any SLO missing in this mapping is treated as failed.
        health_check_results: Mapping of custom health-check name -> bool pass flag.
            These checks are always treated as *critical*.

    Returns:
        Tuple containing (final_score, breakdown) where *breakdown* is a dict with
        the counts of passed/failed SLOs per severity.
    """

    slo_objects: List[SLOResult] = []
    for slo_name, slo_def in slo_definitions.items():
        # Exclude SLOs that were not evaluated (query returned no data)
        if slo_name not in prometheus_results:
            continue
        passed = bool(prometheus_results[slo_name])

        # Support both old format (str) and new format (dict)
        if isinstance(slo_def, str):
            severity = slo_def
            slo_weight = None
        else:
            severity = slo_def.get("severity", "warning")
            slo_weight = slo_def.get("weight")

        slo_objects.append(SLOResult(slo_name, severity, passed, weight=slo_weight))

    # Health-check SLOs (by default keeping them critical)
    for hc_name, hc_passed in health_check_results.items():
        slo_objects.append(SLOResult(hc_name, "critical", bool(hc_passed)))

    total_points = sum(slo.weight(DEFAULT_WEIGHTS) for slo in slo_objects)
    points_lost = sum(slo.weight(DEFAULT_WEIGHTS) for slo in slo_objects if not slo.passed)

    score = 0 if total_points == 0 else int(((total_points - points_lost) / total_points) * 100)

    breakdown = {
        "total_points": total_points,
        "points_lost": points_lost,
        "passed": len([s for s in slo_objects if s.passed]),
        "failed": len([s for s in slo_objects if not s.passed]),
    }
    return score, breakdown
