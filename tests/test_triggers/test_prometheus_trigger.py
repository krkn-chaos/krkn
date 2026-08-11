#!/usr/bin/env python3

"""
Test suite for PrometheusTrigger class

Usage:
    python -m coverage run -a -m unittest tests/test_triggers/test_prometheus_trigger.py -v
"""

import sys
import unittest
from types import ModuleType
from unittest.mock import MagicMock, patch

from krkn.scenario_plugins.triggers.prometheus_trigger import (
    PROM_REQUEST_TIMEOUT_SECONDS,
    PrometheusTrigger,
)
from krkn.scenario_plugins.triggers.trigger_manager import TriggerManager


class TestPrometheusTrigger(unittest.TestCase):

    def _make_config(self, **overrides):
        config = {
            "query": "up > 0",
            "prometheus_url": "http://prometheus:9090",
        }
        config.update(overrides)
        return config

    def _mock_client(self, result=None, side_effect=None):
        client = MagicMock()
        if side_effect is not None:
            client.process_query.side_effect = side_effect
        else:
            client.process_query.return_value = result
        return client

    def _make_trigger(self, client=None, **overrides):
        """Build a trigger; inject client so tests skip real KrknPrometheus import."""
        trigger = PrometheusTrigger(self._make_config(**overrides))
        if client is not None:
            trigger._prom_client = client
        return trigger

    def _patch_krkn_prometheus(self, mock_cls):
        """Install a fake krkn_lib.prometheus.krkn_prometheus module for lazy import."""
        mod = ModuleType("krkn_lib.prometheus.krkn_prometheus")
        mod.KrknPrometheus = mock_cls
        return patch.dict(
            sys.modules,
            {
                "krkn_lib.prometheus.krkn_prometheus": mod,
            },
        )

    # ------------------------------------------------------------------
    # evaluate() tests
    # ------------------------------------------------------------------

    def test_evaluate_non_empty_result(self):
        """Non-empty PromQL result -> evaluate() returns True."""
        client = self._mock_client(
            result=[{"metric": {"__name__": "up"}, "value": [1.0, "1"]}]
        )
        trigger = self._make_trigger(client=client)

        self.assertTrue(trigger.evaluate())
        client.process_query.assert_called_once_with("up > 0")

    def test_evaluate_empty_result(self):
        """Empty list -> evaluate() returns False."""
        trigger = self._make_trigger(client=self._mock_client(result=[]))
        self.assertFalse(trigger.evaluate())

    def test_evaluate_connection_error(self):
        """HTTP/connection errors -> warning logged, returns False, no crash."""
        trigger = self._make_trigger(
            client=self._mock_client(side_effect=ConnectionError("refused"))
        )

        with self.assertLogs(level="WARNING") as cm:
            self.assertFalse(trigger.evaluate())

        self.assertTrue(
            any("prometheus trigger query failed" in msg for msg in cm.output)
        )

    def test_evaluate_request_timeout(self):
        """requests.Timeout -> warning with timeout, returns False."""
        import requests

        trigger = self._make_trigger(
            client=self._mock_client(
                side_effect=requests.exceptions.Timeout("hung")
            )
        )

        with self.assertLogs(level="WARNING") as cm:
            self.assertFalse(trigger.evaluate())

        self.assertTrue(
            any(
                f"timed out after {PROM_REQUEST_TIMEOUT_SECONDS}s" in msg
                for msg in cm.output
            )
        )

    def test_evaluate_generic_exception(self):
        """Unexpected exception -> False, no crash."""
        trigger = self._make_trigger(
            client=self._mock_client(side_effect=RuntimeError("boom"))
        )

        with self.assertLogs(level="WARNING"):
            self.assertFalse(trigger.evaluate())

    def test_client_built_lazily_once(self):
        """KrknPrometheus is created on first evaluate and reused."""
        mock_cls = MagicMock(
            return_value=self._mock_client(result=[{"value": [0, "1"]}])
        )
        trigger = self._make_trigger(prometheus_bearer_token="tok")
        self.assertIsNone(trigger._prom_client)

        with self._patch_krkn_prometheus(mock_cls):
            trigger.evaluate()
            trigger.evaluate()

        mock_cls.assert_called_once_with("http://prometheus:9090", "tok")
        self.assertEqual(mock_cls.return_value.process_query.call_count, 2)
        self.assertEqual(
            trigger._prom_client.prom_cli._timeout,
            PROM_REQUEST_TIMEOUT_SECONDS,
        )

    def test_state_change_logging(self):
        """INFO logs only on state transitions, not every poll."""
        client = MagicMock()
        trigger = self._make_trigger(client=client)

        client.process_query.return_value = []
        with self.assertLogs(level="INFO") as log_ctx:
            trigger.evaluate()
        self.assertTrue(
            any(
                "trigger condition not satisfied" in line
                for line in log_ctx.output
            )
        )

        with patch("logging.info") as mock_info:
            trigger.evaluate()
            mock_info.assert_not_called()

        client.process_query.return_value = [{"value": [0, "1"]}]
        with self.assertLogs(level="INFO") as log_ctx:
            trigger.evaluate()
        self.assertTrue(
            any(
                "trigger condition satisfied" in line
                for line in log_ctx.output
            )
        )

    # ------------------------------------------------------------------
    # timeout via TriggerManager
    # ------------------------------------------------------------------

    @patch("krkn.scenario_plugins.triggers.trigger_manager.time")
    def test_timeout_reached_without_match(self, mock_time):
        """Empty results until deadline -> wait_for_triggers returns False."""
        mock_cls = MagicMock(return_value=self._mock_client(result=[]))
        call_count = 0

        def advancing_monotonic():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return 0.0
            return 999.0

        mock_time.monotonic.side_effect = advancing_monotonic
        mock_time.sleep = lambda x: None

        with self._patch_krkn_prometheus(mock_cls):
            manager = TriggerManager(
                {
                    "timeout": 10,
                    "interval": 1,
                    "conditions": [
                        {
                            "type": "prometheus",
                            "query": "vector(0) > 1",
                            "prometheus_url": "http://prometheus:9090",
                        },
                    ],
                },
            )
            self.assertFalse(manager.wait_for_triggers())

    def test_manager_builds_prometheus_trigger(self):
        mock_cls = MagicMock(
            return_value=self._mock_client(result=[{"value": [0, "1"]}])
        )
        with self._patch_krkn_prometheus(mock_cls):
            manager = TriggerManager(
                {
                    "conditions": [
                        {
                            "type": "prometheus",
                            "query": "up == 1",
                            "prometheus_url": "http://prometheus:9090",
                        },
                    ],
                },
            )
            self.assertTrue(manager.wait_for_triggers())
        mock_cls.return_value.process_query.assert_called_with("up == 1")

    # ------------------------------------------------------------------
    # describe() / validation
    # ------------------------------------------------------------------

    def test_describe(self):
        trigger = self._make_trigger(query="avg(rate(cpu[5m])) > 0.8")
        description = trigger.describe()
        self.assertIn("prometheus", description)
        self.assertIn("avg(rate(cpu[5m])) > 0.8", description)

    def test_missing_query_raises(self):
        with self.assertRaises(ValueError) as ctx:
            PrometheusTrigger({"prometheus_url": "http://prometheus:9090"})
        self.assertIn("query", str(ctx.exception))

    def test_empty_query_raises(self):
        with self.assertRaises(ValueError):
            PrometheusTrigger(
                {"query": "", "prometheus_url": "http://prometheus:9090"}
            )

    def test_missing_prometheus_url_raises(self):
        with self.assertRaises(ValueError) as ctx:
            PrometheusTrigger({"query": "up"})
        self.assertIn("prometheus_url", str(ctx.exception))

    def test_last_result_initialised_to_none(self):
        trigger = self._make_trigger()
        self.assertIsNone(trigger._last_result)


if __name__ == "__main__":
    unittest.main()
