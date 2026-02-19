"""Resiliency evaluation orchestrator for Krkn chaos runs.

This module provides the `Resiliency` class which loads the canonical
`alerts.yaml`, executes every SLO expression against Prometheus in the
chaos-test time window, determines pass/fail status and calculates an
overall resiliency score using the generic weighted model implemented
in `krkn.resiliency.score`.
"""

from __future__ import annotations

import base64
import datetime
import logging
import os
from typing import Dict, List, Any, Optional

import yaml
import json
import dataclasses
from krkn_lib.models.telemetry import ChaosRunTelemetry

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
from krkn.prometheus.collector import evaluate_slos
from krkn.resiliency.score import calculate_resiliency_score


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
        env_yaml = os.getenv(self.ENV_VAR_NAME, '').strip()
        if env_yaml:
            try:
                try:
                    decoded_yaml = base64.b64decode(env_yaml, validate=True).decode('utf-8')
                except (base64.binascii.Error, UnicodeDecodeError) as e:
                    logging.debug("Failed to base64 decode %s, trying as plain YAML: %s", 
                                self.ENV_VAR_NAME, str(e))
                    decoded_yaml = env_yaml
                
                raw_yaml_data = yaml.safe_load(decoded_yaml)
                logging.info("Loaded SLO configuration from environment variable %s", self.ENV_VAR_NAME)
                
                if isinstance(raw_yaml_data, dict):
                    self.prometheus_url = raw_yaml_data.get("prometheus_url")
                    raw_yaml_data = raw_yaml_data.get("slos", raw_yaml_data.get("alerts", []))
                
            except yaml.YAMLError as exc:
                logging.error("Failed to parse YAML from %s: %s", self.ENV_VAR_NAME, str(exc))
                raw_yaml_data = []  
                self.prometheus_url = None
            except Exception as exc:
                logging.error("Unexpected error loading SLOs from %s: %s", 
                            self.ENV_VAR_NAME, str(exc))
                raw_yaml_data = [] 
                self.prometheus_url = None
        else:
            if not os.path.exists(alerts_yaml_path):
                raise FileNotFoundError(f"alerts file not found: {alerts_yaml_path}")
            with open(alerts_yaml_path, "r", encoding="utf-8") as fp:
                raw_yaml_data = yaml.safe_load(fp)
            logging.info("Loaded SLO configuration from %s", alerts_yaml_path)
            self.prometheus_url = None

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
        weights: Optional[Dict[str, int]] = None,
        health_check_results: Optional[Dict[str, bool]] = None,
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
        weights: Optional[Dict[str, int]] = None,
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
            weights: Optional override of severity weights for SLO calculation.
        Returns:
            The calculated integer resiliency score (0-100) for this scenario.
        """
        slo_results = evaluate_slos(
            prom_cli=prom_cli,
            slo_list=self._slos,
            start_time=start_time,
            end_time=end_time,
        )
        slo_defs = {slo["name"]: slo["severity"] for slo in self._slos}
        score, breakdown = calculate_resiliency_score(
            slo_definitions=slo_defs,
            prometheus_results=slo_results,
            health_check_results=health_check_results or {},
            weights=weights,
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
        weights: Optional[Dict[str, int]] = None,
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
        slo_defs = {slo["name"]: slo["severity"] for slo in self._slos}
        _overall_score, full_breakdown = calculate_resiliency_score(
            slo_definitions=slo_defs,
            prometheus_results=full_slo_results,
            health_check_results={},
            weights=weights,
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
    run_uuid: Optional[str] = None,
    alerts_yaml_path: str = "config/alerts.yaml",
    logger: Optional[logging.Logger] = None,
) -> Optional[Dict[str, Any]]:
    """Evaluate SLOs, combine health-check results, attach a resiliency report
    to *chaos_telemetry* and return the report. Any failure is logged and *None*
    is returned.
    """

    log = logger or logging.getLogger(__name__)

    try:
        resiliency_obj = Resiliency(alerts_yaml_path)
        resiliency_obj._results = evaluate_slos(
            prom_cli=prometheus, 
            slo_list=resiliency_obj._slos,
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


# -----------------------------------------------------------------------------
# Helper utilities extracted from run_kraken.py
# -----------------------------------------------------------------------------

from typing import Tuple


def add_scenario_reports(
    *,
    resiliency_obj: "Resiliency",
    scenario_telemetries,
    prom_cli: KrknPrometheus,
    scenario_type: str,
    batch_start_dt: datetime.datetime,
    batch_end_dt: datetime.datetime,
    weight: int | float = 1,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Evaluate SLOs for every telemetry item belonging to a scenario window,
    store the result in *resiliency_obj* and enrich the telemetry list with a
    compact resiliency breakdown.

    Args:
        resiliency_obj: Initialized :class:`Resiliency` orchestrator. If *None*,
            the call becomes a no-op (saves caller side checks).
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
    if resiliency_obj is None:
        return

    log = logger or logging.getLogger(__name__)

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
            resiliency_obj.add_scenario_report(
                scenario_name=str(scen_name),
                prom_cli=prom_cli,
                start_time=st_dt,
                end_time=en_dt,
                weight=weight,
                health_check_results=None,
            )

            compact = Resiliency.compact_breakdown(
                resiliency_obj.scenario_reports[-1]
            )
            if isinstance(tel, dict):
                tel["resiliency_report"] = compact
            else:
                setattr(tel, "resiliency_report", compact)
        except Exception as exc:
            log.error("Resiliency per-scenario evaluation failed: %s", exc)


def finalize_and_save(
    *,
    resiliency_obj: "Resiliency",
    prom_cli: KrknPrometheus,
    total_start_time: datetime.datetime,
    total_end_time: datetime.datetime,
    run_mode: str = "standalone",
    summary_path: str = "kraken.report",
    detailed_path: str = "resiliency-report.json",
    logger: Optional[logging.Logger] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Finalize resiliency scoring, persist reports and return them.

    Returns:
        (summary_report, detailed_report)
    """
    if resiliency_obj is None:
        return {}, {}

    log = logger or logging.getLogger(__name__)

    try:
        resiliency_obj.finalize_report(
            prom_cli=prom_cli,
            total_start_time=total_start_time,
            total_end_time=total_end_time,
        )
        summary = resiliency_obj.get_summary()
        detailed = resiliency_obj.get_detailed_report()

        if run_mode == "controller":
            # krknctl expects the detailed report on stdout in a special format
            try:
                detailed_json = json.dumps(detailed)
                print(f"KRKN_RESILIENCY_REPORT_JSON:{detailed_json}")
                log.info("Resiliency report logged to stdout for krknctl.")
            except Exception as exc:
                log.error("Failed to serialize and log detailed resiliency report: %s", exc)
        else:
            # Stand-alone mode – write to files for post-run consumption
            try:
                with open(summary_path, "w", encoding="utf-8") as fp:
                    json.dump(summary, fp, indent=2)
                with open(detailed_path, "w", encoding="utf-8") as fp:
                    json.dump(detailed, fp, indent=2)
                log.info("Resiliency reports written: %s and %s", summary_path, detailed_path)
            except Exception as io_exc:
                log.error("Failed to write resiliency report files: %s", io_exc)

        return summary, detailed

    except Exception as exc:
        log.error("Failed to finalize resiliency scoring: %s", exc)
        return {}, {}