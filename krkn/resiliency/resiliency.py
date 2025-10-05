"""Resiliency evaluation orchestrator for Krkn chaos runs.

This module provides the `Resiliency` class which loads the canonical
`alerts.yaml`, executes every SLO expression against Prometheus in the
chaos-test time window, determines pass/fail status and calculates an
overall resiliency score using the generic weighted model implemented
in `krkn.resiliency.score`.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import Dict, List, Any

import yaml

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
from krkn.prometheus.collector import evaluate_slos
from .score import calculate_resiliency_score


class Resiliency:  
    """Central orchestrator for resiliency scoring."""

    def __init__(self, alerts_yaml_path: str):
        if not os.path.exists(alerts_yaml_path):
            raise FileNotFoundError(f"alerts file not found: {alerts_yaml_path}")
        self.alerts_yaml_path = alerts_yaml_path
        self._slos: List[Dict[str, Any]] = self._load_alerts(alerts_yaml_path)
        self._results: Dict[str, bool] = {}
        self._score: int | None = None
        self._breakdown: Dict[str, int] | None = None

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def evaluate_slos(
        self,
        prom_cli: KrknPrometheus,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        granularity: int = 30,
    ) -> None:
        """Evaluate all SLO expressions against Prometheus and cache results."""

        # Use shared evaluation helper from `krkn.prometheus.collector`
        self._results = evaluate_slos(
            prom_cli=prom_cli,
            slo_list=self._slos,
            start_time=start_time,
            end_time=end_time,
            granularity=granularity,
        )

    def calculate_score(
        self,
        *,
        weights: Dict[str, int] | None = None,
        health_check_results: Dict[str, bool] | None = None,
    ) -> int:
        """Calculate the resiliency score using collected SLO results."""
        slo_defs = {slo["name"]: slo["severity"] for slo in self._slos}
        score, breakdown = calculate_resiliency_score(
            slo_definitions=slo_defs,
            prometheus_results=self._results,
            health_check_results=health_check_results or {},
            weights=weights,
        )
        self._score = score
        self._breakdown = breakdown
        self._health_check_results = health_check_results or {}
        return score

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary ready for telemetry output."""
        if self._score is None:
            raise RuntimeError("calculate_score() must be called before to_dict()")
        return {
            "score": self._score,
            "breakdown": self._breakdown,
            "slo_results": self._results,
            "health_check_results": getattr(self, "_health_check_results", {}),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _load_alerts(path: str) -> List[Dict[str, Any]]:
        """Load alerts.yaml and normalise it into an internal list structure."""
        with open(path, "r", encoding="utf-8") as fp:
            raw_alerts = yaml.safe_load(fp)

        if not isinstance(raw_alerts, list):
            raise ValueError("alerts.yaml must contain a top-level list of SLO definitions")

        slos: List[Dict[str, Any]] = []
        for idx, alert in enumerate(raw_alerts):
            if not ("expr" in alert and "severity" in alert):
                logging.warning("Skipping invalid alert entry at index %d: %s", idx, alert)
                continue
            # Generate a stable name for the SLO. Prefer description, else expr hash.
            name = (
                alert.get("description")
                or f"slo_{idx}"
            )
            slos.append({
                "name": name,
                "expr": alert["expr"],
                "severity": alert["severity"].lower(),
            })
        return slos