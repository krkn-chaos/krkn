# Copyright 2026 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");

"""Prometheus-backed health checks."""

import datetime
import logging
import os
import queue
from typing import Any

import yaml
from krkn_lib.models.elastic.models import ElasticAlert

try:
    from krkn_lib.models.telemetry import Alerts
except ImportError:  # Older krkn-lib versions do not expose the renamed model yet.
    class Alerts:
        """Compatibility alert record for environments with older krkn-lib."""

        def __init__(self, **kwargs):
            self.name = kwargs.get("name", "")
            self.severity = kwargs.get("severity", "")
            self.message = kwargs.get("message", "")
            self.starts_at = kwargs.get("starts_at", "")
            self.status = kwargs.get("status", False)
            self.phase = kwargs.get("phase", "during")

from krkn.health_checks.abstract_health_check_plugin import AbstractHealthCheckPlugin
from krkn.prometheus.collector import slo_passed


class PrometheusHealthCheckPlugin(AbstractHealthCheckPlugin):
    """Evaluate PromQL health checks at the requested lifecycle phase."""

    def __init__(
        self,
        health_check_type: str = "prometheus_health_check",
        prometheus=None,
        elastic=None,
        run_uuid=None,
        elastic_alerts_index=None,
        chaos_start_time=None,
        chaos_end_time=None,
        **kwargs,
    ):
        super().__init__(health_check_type)
        self.prometheus = prometheus
        self.elastic = elastic
        self.run_uuid = run_uuid
        self.elastic_alerts_index = elastic_alerts_index
        self.chaos_start_time = chaos_start_time
        self.chaos_end_time = chaos_end_time

    def get_health_check_types(self) -> list[str]:
        """Return the configuration type handled by this plugin."""
        return ["prometheus_health_check"]

    def get_config_key(self) -> str:
        """Return the top-level configuration section for Prometheus checks."""
        return "performance_monitoring"

    def increment_iterations(self) -> None:
        """Keep the interface contract; Prometheus checks run once per phase."""
        pass

    def manages_own_threads(self) -> bool:
        """Return false because the factory owns plugin worker threads."""
        # During checks are deliberately evaluated once at teardown, not on an interval.
        return False

    defer_during = True

    def run_health_check(self, config: dict[str, Any], telemetry_queue: queue.Queue) -> None:
        """Do not start interval polling; deferred checks run during teardown."""
        return None

    def run_once(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue = None,
        phase: str = None,
    ) -> dict[str, Any]:
        """Evaluate configured expressions once and return alert results and failures."""
        if not config.get("enable_alerts", False):
            return self._result()

        checks = config.get("config", config.get("queries", []))
        alert_profile = config.get("alert_profile")
        if alert_profile and not checks:
            if not os.path.exists(alert_profile):
                return self._failure(f"Alert profile does not exist: {alert_profile}")
            with open(alert_profile, "r", encoding="utf-8") as profile:
                checks = yaml.safe_load(profile) or []
        if isinstance(checks, dict):
            checks = [checks]
        if not checks:
            return self._result()
        if self.prometheus is None:
            return self._failure("Prometheus client is not configured")

        failures = []
        alerts: list[Alerts] = []
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                    logging.warning("Invalid Prometheus check at index %d", index)
                    continue
            expression = check.get("expr", check.get("query"))
            name = check.get("name", check.get("description", f"prometheus_check_{index}"))
            if not expression:
                logging.warning("Prometheus check '%s' has no expr or query", name)
                continue
            try:
                if phase == "during":
                    response = self.prometheus.process_prom_query_in_range(
                        expression,
                        start_time=self.chaos_start_time,
                        end_time=self.chaos_end_time or datetime.datetime.now(datetime.timezone.utc),
                    )
                else:
                    response = self.prometheus.process_query(expression)
                passed = slo_passed(response)
                passed = True if passed is None else passed
                severity = check.get("severity", "warning")
                message = check.get("description", name)
                alert = self._alert(name, severity, message, phase, passed)
                if not config.get("only_failures", False) or not passed:
                    alerts.append(alert)
                if not passed:
                    if str(severity).lower() in ("critical", "error"):
                        failures.append(self._failure_from_alert(alert))
                    self._push_alert(alert)
            except Exception as exc:
                logging.error(
                    "Prometheus health check '%s' failed: %s",
                    name,
                    exc,
                    exc_info=True,
                )
                message = str(exc)
                severity = check.get("severity", "warning")
                alert = self._alert(name, severity, message, phase, False)
                if str(severity).lower() in ("critical", "error"):
                    failures.append(self._failure_from_alert(alert))
                alerts.append(alert)
                self._push_alert(alert)

        result = {
            "passed": not failures,
            "failures": failures,
            "alerts": alerts,
        }
        self.ret_value = 0 if result["passed"] else 1
        return result

    @staticmethod
    def _result(passed: bool = True) -> dict[str, Any]:
        return {"passed": passed, "failures": [], "alerts": []}

    @staticmethod
    def _failure(message: str) -> dict[str, Any]:
        result = PrometheusHealthCheckPlugin._result(False)
        result["failures"].append({"message": message})
        return result

    @staticmethod
    def _failure_from_alert(alert: Alerts) -> dict[str, str]:
        return {"name": alert.name, "message": alert.message, "severity": alert.severity}

    def _alert(self, name: str, severity: str, message: str, phase: str, status: bool) -> Alerts:
        start_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return Alerts(
            name=name,
            severity=severity,
            message=message,
            starts_at=start_iso,
            status=status,
            phase=phase or "during",
        )

    def _push_alert(self, alert: Alerts) -> None:
        if self.elastic is None or not self.elastic_alerts_index:
            return
        try:
            elastic_alert = ElasticAlert(
                run_uuid=self.run_uuid,
                severity=alert.severity,
                alert=alert.message,
                created_at=alert.starts_at,
                phase=alert.phase,
            )
            # Keep phase readable with older krkn-lib ElasticAlert models too.
            elastic_alert.phase = alert.phase
            if self.elastic.push_alert(elastic_alert, self.elastic_alerts_index) == -1:
                logging.error("Failed to push Prometheus alert '%s' to Elasticsearch", alert.name)
        except Exception as exc:
            logging.error("Failed to push Prometheus alert '%s' to Elasticsearch: %s", alert.name, exc)
