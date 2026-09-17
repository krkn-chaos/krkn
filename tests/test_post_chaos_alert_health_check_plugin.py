import queue
import threading
import unittest
from unittest.mock import MagicMock, patch

from krkn.health_checks import HealthCheckFactory
from krkn.health_checks.post_chaos_alert_health_check_plugin import (
    PostChaosAlertHealthCheckPlugin,
)


class TestPostChaosAlertHealthCheckPlugin(unittest.TestCase):
    def test_plugin_discoverable_by_factory(self):
        factory = HealthCheckFactory()
        self.assertIn("post_chaos_alert_check", factory.loaded_plugins)

    def test_blocks_until_stop_then_evaluates_once(self):
        plugin = PostChaosAlertHealthCheckPlugin(
            prometheus=MagicMock(), elastic_search=MagicMock(), run_uuid="uuid-1"
        )
        tq = queue.Queue()
        config = {"check_critical_alerts": True, "elastic_alerts_index": "alerts-idx"}

        with patch(
            "krkn.health_checks.post_chaos_alert_health_check_plugin.prometheus_plugin"
        ) as mock_plugin:
            worker = threading.Thread(
                target=plugin.run_health_check, args=(config, tq)
            )
            worker.start()

            # Not evaluated yet; still blocked on stop_event.
            worker.join(timeout=0.2)
            self.assertTrue(worker.is_alive())
            mock_plugin.critical_alerts.assert_not_called()

            plugin.stop()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            mock_plugin.critical_alerts.assert_called_once()

    def test_failure_sets_return_value(self):
        plugin = PostChaosAlertHealthCheckPlugin(
            prometheus=MagicMock(), elastic_search=MagicMock(), run_uuid="uuid-1"
        )
        tq = queue.Queue()
        config = {"check_critical_alerts": True, "elastic_alerts_index": "alerts-idx"}

        def fake_critical_alerts(prom, summary, *args, **kwargs):
            summary.post_chaos_alerts.append("ALERT")

        with patch(
            "krkn.health_checks.post_chaos_alert_health_check_plugin.prometheus_plugin"
        ) as mock_plugin:
            mock_plugin.critical_alerts.side_effect = fake_critical_alerts
            plugin.stop()
            plugin.run_health_check(config, tq)

        self.assertEqual(plugin.get_return_value(), 2)

    def test_no_checks_enabled_skips(self):
        plugin = PostChaosAlertHealthCheckPlugin(
            prometheus=MagicMock(), elastic_search=MagicMock(), run_uuid="uuid-1"
        )
        tq = queue.Queue()

        with patch(
            "krkn.health_checks.post_chaos_alert_health_check_plugin.prometheus_plugin"
        ) as mock_plugin:
            plugin.stop()
            plugin.run_health_check({}, tq)
            mock_plugin.critical_alerts.assert_not_called()
            mock_plugin.alerts.assert_not_called()
            mock_plugin.metrics.assert_not_called()

        self.assertEqual(plugin.get_return_value(), 0)


if __name__ == "__main__":
    unittest.main()
