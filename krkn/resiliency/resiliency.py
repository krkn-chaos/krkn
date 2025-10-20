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
import json
from krkn_lib.models.telemetry import ChaosRunTelemetry

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
from krkn.prometheus.collector import evaluate_slos
from .score import calculate_resiliency_score


class Resiliency:  
    """Central orchestrator for resiliency scoring."""




    ENV_VAR_NAME = "KRKN_ALERTS_YAML_CONTENT"

    def __init__(self, alerts_yaml_path: str = "config/alerts.yaml"):
        """Load SLO definitions from the default alerts file, unless the
        *KRKN_ALERTS_YAML_CONTENT* environment variable is set – in which case its
        raw YAML string is parsed instead. The custom YAML may optionally follow
        this schema:

        prometheus_url: http://prometheus:9090  # optional, currently unused
        slos:
          - expr: <PromQL>
            severity: critical|warning
            description: <text>

        For backward-compatibility the legacy list-only format is still accepted.
        """
        raw_yaml_data: Any
        env_yaml = os.getenv(self.ENV_VAR_NAME)
        if env_yaml:
            try:
                raw_yaml_data = yaml.safe_load(env_yaml)
            except yaml.YAMLError as exc:
                raise ValueError(
                    f"Invalid YAML in environment variable {self.ENV_VAR_NAME}: {exc}"
                ) from exc
            logging.info("Loaded SLO configuration from environment variable %s", self.ENV_VAR_NAME)
            # Store optional Prometheus URL if provided
            if isinstance(raw_yaml_data, dict):
                self.prometheus_url = raw_yaml_data.get("prometheus_url")  # may be None
                raw_yaml_data = raw_yaml_data.get("slos", raw_yaml_data.get("alerts", []))
        else:
            if not os.path.exists(alerts_yaml_path):
                raise FileNotFoundError(f"alerts file not found: {alerts_yaml_path}")
            with open(alerts_yaml_path, "r", encoding="utf-8") as fp:
                raw_yaml_data = yaml.safe_load(fp)
            logging.info("Loaded SLO configuration from %s", alerts_yaml_path)
            self.prometheus_url = None

        self._slos = self._normalise_alerts(raw_yaml_data)
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
    @staticmethod
    def _normalise_alerts(raw_alerts: Any) -> List[Dict[str, Any]]:
        """Convert raw YAML alerts data into internal SLO list structure."""
        if not isinstance(raw_alerts, list):
            raise ValueError("SLO configuration must be a list under key 'slos' or top-level list")

        slos: List[Dict[str, Any]] = []
        for idx, alert in enumerate(raw_alerts):
            if not (isinstance(alert, dict) and "expr" in alert and "severity" in alert):
                logging.warning("Skipping invalid alert entry at index %d: %s", idx, alert)
                continue
            name = alert.get("description") or f"slo_{idx}"
            slos.append(
                {
                    "name": name,
                    "expr": alert["expr"],
                    "severity": str(alert["severity"]).lower(),
                }
            )
        return slos

# -----------------------------------------------------------------------------
# High-level helper for run_kraken.py
# -----------------------------------------------------------------------------

def compute_resiliency(*,
    prometheus: KrknPrometheus,
    chaos_telemetry: "ChaosRunTelemetry",
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    run_uuid: str | None = None,
    alerts_yaml_path: str = "config/alerts.yaml",
    logger: logging.Logger | None = None,
) -> Dict[str, Any] | None:
    """Evaluate SLOs, combine health-check results, attach a resiliency report
    to *chaos_telemetry* and return the report. Any failure is logged and *None*
    is returned.
    """

    log = logger or logging.getLogger(__name__)

    try:
        resiliency_obj = Resiliency(alerts_yaml_path)
        resiliency_obj.evaluate_slos(
            prom_cli=prometheus,
            start_time=start_time,
            end_time=end_time,
        )

        health_results: Dict[str, bool] = {}
        hc_list = getattr(chaos_telemetry, "health_checks", None)
        if hc_list:
            for idx, hc in enumerate(hc_list):
                # Extract URL/name
                try:
                    name = getattr(hc, "url", None)
                    if name is None and isinstance(hc, dict):
                        name = hc.get("url", f"hc_{idx}")
                except Exception:
                    name = f"hc_{idx}"
                # Extract status
                try:
                    status = getattr(hc, "status", None)
                    if status is None and isinstance(hc, dict):
                        status = hc.get("status", True)
                except Exception:
                    status = False
                health_results[str(name)] = bool(status)

        resiliency_obj.calculate_score(health_check_results=health_results)
        resiliency_report = resiliency_obj.to_dict()
        chaos_telemetry.resiliency_report = resiliency_report
        chaos_telemetry.resiliency_score = resiliency_report.get("score")

        
        if not hasattr(ChaosRunTelemetry, "_with_resiliency_patch"):
            _orig_to_json = ChaosRunTelemetry.to_json

            def _to_json_with_resiliency(self):
                raw_json = _orig_to_json(self)
                try:
                    data = json.loads(raw_json)
                except Exception:
                    return raw_json
                if hasattr(self, "resiliency_report"):
                    data["resiliency_report"] = self.resiliency_report
                if hasattr(self, "resiliency_score"):
                    data["resiliency_score"] = self.resiliency_score
                return json.dumps(data)

            ChaosRunTelemetry.to_json = _to_json_with_resiliency  
            ChaosRunTelemetry._with_resiliency_patch = True

        log.info(
            "Resiliency score for run %s: %s%%",
            run_uuid or "<unknown>",
            resiliency_report.get("score"),
        )
        return resiliency_report

    except Exception as exc:
        log.error("Failed to compute resiliency score: %s", exc)
        return None