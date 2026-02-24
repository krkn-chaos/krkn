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
from typing import Dict, List, Any, Optional, Tuple

import yaml
import json
import dataclasses
from krkn_lib.models.telemetry import ChaosRunTelemetry

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
from krkn.prometheus.collector import evaluate_slos
from krkn.resiliency.score import calculate_resiliency_score


class Resiliency:  
    """Central orchestrator for resiliency scoring."""

    def __init__(self, alerts_yaml_path: str):
       
        if not os.path.exists(alerts_yaml_path):
            raise FileNotFoundError(f"alerts file not found: {alerts_yaml_path}")
        with open(alerts_yaml_path, "r", encoding="utf-8") as fp:
            raw_yaml_data = yaml.safe_load(fp)
        logging.info("Loaded SLO configuration from %s", alerts_yaml_path)

        self._slos = self._normalise_alerts(raw_yaml_data)
        self._results: Dict[str, bool] = {}
        self._score: Optional[int] = None
        self._breakdown: Optional[Dict[str, int]] = None
        self._health_check_results: Dict[str, bool] = {}
        self.scenario_reports: List[Dict[str, Any]] = []
        self.summary: Optional[Dict[str, Any]] = None
        self.detailed_report: Optional[Dict[str, Any]] = None

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def calculate_score(
        self,
        *,
        health_check_results: Optional[Dict[str, bool]] = None,
    ) -> int:
        """Calculate the resiliency score using collected SLO results."""
        slo_defs = {slo["name"]: {"severity": slo["severity"], "weight": slo.get("weight")} for slo in self._slos}
        score, breakdown = calculate_resiliency_score(
            slo_definitions=slo_defs,
            prometheus_results=self._results,
            health_check_results=health_check_results or {},
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
    # Scenario-based resiliency evaluation
    # ------------------------------------------------------------------
    def add_scenario_report(
        self,
        *,
        scenario_name: str,
        prom_cli: KrknPrometheus,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        weight: float | int = 1,
        health_check_results: Optional[Dict[str, bool]] = None,
    ) -> int:
        """
        Evaluate SLOs for a single scenario window and store the result.

        Args:
            scenario_name: Human-friendly scenario identifier.
            prom_cli: Initialized KrknPrometheus instance.
            start_time: Window start.
            end_time: Window end.
            weight: Weight to use for the final weighted average calculation.
            health_check_results: Optional mapping of custom health-check name ➡ bool.
        Returns:
            The calculated integer resiliency score (0-100) for this scenario.
        """
        slo_results = evaluate_slos(
            prom_cli=prom_cli,
            slo_list=self._slos,
            start_time=start_time,
            end_time=end_time,
        )
        slo_defs = {slo["name"]: {"severity": slo["severity"], "weight": slo.get("weight")} for slo in self._slos}
        score, breakdown = calculate_resiliency_score(
            slo_definitions=slo_defs,
            prometheus_results=slo_results,
            health_check_results=health_check_results or {},
        )
        self.scenario_reports.append(
            {
                "name": scenario_name,
                "window": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                },
                "score": score,
                "weight": weight,
                "breakdown": breakdown,
                "slo_results": slo_results,
                "health_check_results": health_check_results or {},
            }
        )
        return score

    def finalize_report(
        self,
        *,
        prom_cli: KrknPrometheus,
        total_start_time: datetime.datetime,
        total_end_time: datetime.datetime,
    ) -> None:
        if not self.scenario_reports:
            raise RuntimeError("No scenario reports added – nothing to finalize")

        # ---------------- Weighted average (primary resiliency_score) ----------
        total_weight = sum(rep["weight"] for rep in self.scenario_reports)
        resiliency_score = int(
            sum(rep["score"] * rep["weight"] for rep in self.scenario_reports) / total_weight
        )

        # ---------------- Overall SLO evaluation across full test window -----------------------------
        full_slo_results = evaluate_slos(
            prom_cli=prom_cli,
            slo_list=self._slos,
            start_time=total_start_time,
            end_time=total_end_time,
        )
        slo_defs = {slo["name"]: {"severity": slo["severity"], "weight": slo.get("weight")} for slo in self._slos}
        _overall_score, full_breakdown = calculate_resiliency_score(
            slo_definitions=slo_defs,
            prometheus_results=full_slo_results,
            health_check_results={},
        )

        self.summary = {
            "scenarios": {rep["name"]: rep["score"] for rep in self.scenario_reports},
            "resiliency_score": resiliency_score,
            "passed_slos": full_breakdown.get("passed", 0),
            "total_slos": full_breakdown.get("passed", 0) + full_breakdown.get("failed", 0),
        }

        # Detailed report currently limited to per-scenario information; system stability section removed
        self.detailed_report = {
            "scenarios": self.scenario_reports,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Return the concise resiliency_summary structure."""
        if not hasattr(self, "summary"):
            raise RuntimeError("finalize_report() must be called first")
        return self.summary

    def get_detailed_report(self) -> Dict[str, Any]:
        """Return the full resiliency-report structure."""
        if not hasattr(self, "detailed_report"):
            raise RuntimeError("finalize_report() must be called first")
        return self.detailed_report

    @staticmethod
    def compact_breakdown(report: Dict[str, Any]) -> Dict[str, int]:
        """Return a compact summary dict for a single scenario report."""
        try:
            passed = report["breakdown"]["passed"]
            failed = report["breakdown"]["failed"]
            score_val = report["score"]
        except Exception:
            passed = report.get("breakdown", {}).get("passed", 0)
            failed = report.get("breakdown", {}).get("failed", 0)
            score_val = report.get("score", 0)
        return {
            "resiliency_score": score_val,
            "passed_slos": passed,
            "total_slos": passed + failed,
        }

    def attach_compact_to_telemetry(self, chaos_telemetry: ChaosRunTelemetry) -> None:
        """Embed per-scenario compact resiliency reports into a ChaosRunTelemetry instance."""
        score_map = {
            rep["name"]: self.compact_breakdown(rep) for rep in self.scenario_reports
        }
        new_scenarios = []
        for item in getattr(chaos_telemetry, "scenarios", []):
            if isinstance(item, dict):
                name = item.get("scenario")
                if name in score_map:
                    item["resiliency_report"] = score_map[name]
                new_scenarios.append(item)
            else:
                name = getattr(item, "scenario", None)
                try:
                    item_dict = dataclasses.asdict(item)
                except Exception:
                    item_dict = {
                        k: getattr(item, k)
                        for k in dir(item)
                        if not k.startswith("__") and not callable(getattr(item, k))
                    }
                if name in score_map:
                    item_dict["resiliency_report"] = score_map[name]
                new_scenarios.append(item_dict)
        chaos_telemetry.scenarios = new_scenarios

    def add_scenario_reports(
        self,
        *,
        scenario_telemetries,
        prom_cli: KrknPrometheus,
        scenario_type: str,
        batch_start_dt: datetime.datetime,
        batch_end_dt: datetime.datetime,
        weight: int | float = 1,
    ) -> None:
        """Evaluate SLOs for every telemetry item belonging to a scenario window,
        store the result and enrich the telemetry list with a compact resiliency breakdown.

        Args:
            scenario_telemetries: Iterable with telemetry objects/dicts for the
                current scenario batch window.
            prom_cli: Pre-configured :class:`KrknPrometheus` instance.
            scenario_type: Fallback scenario identifier in case individual
                telemetry items do not provide one.
            batch_start_dt: Fallback start timestamp for the batch window.
            batch_end_dt: Fallback end timestamp for the batch window.
            weight: Weight to assign to every scenario when calculating the final
                weighted average.
            logger: Optional custom logger.
        """

        for tel in scenario_telemetries:
            try:
                # -------- Extract timestamps & scenario name --------------------
                if isinstance(tel, dict):
                    st_ts = tel.get("start_timestamp")
                    en_ts = tel.get("end_timestamp")
                    scen_name = tel.get("scenario", scenario_type)
                else:
                    st_ts = getattr(tel, "start_timestamp", None)
                    en_ts = getattr(tel, "end_timestamp", None)
                    scen_name = getattr(tel, "scenario", scenario_type)

                if st_ts and en_ts:
                    st_dt = datetime.datetime.fromtimestamp(int(st_ts))
                    en_dt = datetime.datetime.fromtimestamp(int(en_ts))
                else:
                    st_dt = batch_start_dt
                    en_dt = batch_end_dt

                # -------- Calculate resiliency score for the scenario -----------
                self.add_scenario_report(
                    scenario_name=str(scen_name),
                    prom_cli=prom_cli,
                    start_time=st_dt,
                    end_time=en_dt,
                    weight=weight,
                    health_check_results=None,
                )

                compact = self.compact_breakdown(self.scenario_reports[-1])
                if isinstance(tel, dict):
                    tel["resiliency_report"] = compact
                else:
                    setattr(tel, "resiliency_report", compact)
            except Exception as exc:
                logging.error("Resiliency per-scenario evaluation failed: %s", exc)

    def finalize_and_save(
        self,
        *,
        prom_cli: KrknPrometheus,
        total_start_time: datetime.datetime,
        total_end_time: datetime.datetime,
        run_mode: str = "standalone",
        detailed_path: str = "resiliency-report.json",
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Finalize resiliency scoring, persist reports and return them.

        Args:
            prom_cli: Pre-configured KrknPrometheus instance.
            total_start_time: Start time for the full test window.
            total_end_time: End time for the full test window.
            run_mode: "controller" or "standalone" mode.

        Returns:
            (detailed_report)
        """

        try:
            self.finalize_report(
                prom_cli=prom_cli,
                total_start_time=total_start_time,
                total_end_time=total_end_time,
            )
            detailed = self.get_detailed_report()

            if run_mode == "controller":
                # krknctl expects the detailed report on stdout in a special format
                try:
                    detailed_json = json.dumps(detailed)
                    print(f"KRKN_RESILIENCY_REPORT_JSON:{detailed_json}")
                    logging.info("Resiliency report logged to stdout for krknctl.")
                except Exception as exc:
                    logging.error("Failed to serialize and log detailed resiliency report: %s", exc)
            else:
                # Stand-alone mode – write to files for post-run consumption
                try:
                    with open(detailed_path, "w", encoding="utf-8") as fp:
                        json.dump(detailed, fp, indent=2)
                    logging.info("Resiliency report written: %s", detailed_path)
                except Exception as io_exc:
                    logging.error("Failed to write resiliency report files: %s", io_exc)

        except Exception as exc:
            logging.error("Failed to finalize resiliency scoring: %s", exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
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
                    "weight": alert.get("weight")
                }
            )
        return slos
