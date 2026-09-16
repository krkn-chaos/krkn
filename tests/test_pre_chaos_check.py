import unittest
from unittest.mock import MagicMock, patch

from krkn.alert_health_check.pre_chaos_check import run_pre_chaos_check


class TestPreChaosCheck(unittest.TestCase):
    def _base_kwargs(self, **overrides):
        kwargs = dict(
            chaos_scenarios=[{"id": "scenario1"}],
            check_critical_alerts=False,
            enable_alerts=False,
            enable_metrics=False,
            exit_on_pre_check_failure=False,
            prometheus=MagicMock(),
            elastic_search=MagicMock(),
            run_uuid="uuid-1",
            elastic_alerts_index="alerts-idx",
            elastic_metrics_index="metrics-idx",
            alert_profile="alerts.yaml",
            metrics_profile="metrics.yaml",
        )
        kwargs.update(overrides)
        return kwargs

    @patch("krkn.alert_health_check.pre_chaos_check.prometheus_plugin")
    def test_critical_alerts_failure_sets_failed(self, mock_plugin):
        def fake_critical_alerts(prom, summary, *args, **kwargs):
            summary.post_chaos_alerts.append("ALERT")

        mock_plugin.critical_alerts.side_effect = fake_critical_alerts
        result = run_pre_chaos_check(**self._base_kwargs(check_critical_alerts=True))
        self.assertTrue(result.ran)
        self.assertTrue(result.failed)
        self.assertFalse(result.should_exit)

    @patch("krkn.alert_health_check.pre_chaos_check.prometheus_plugin")
    def test_alerts_profile_failure_sets_failed(self, mock_plugin):
        mock_plugin.alerts.return_value = ["some-alert"]
        result = run_pre_chaos_check(**self._base_kwargs(enable_alerts=True))
        self.assertTrue(result.ran)
        self.assertTrue(result.failed)
        self.assertFalse(result.should_exit)

    @patch("krkn.alert_health_check.pre_chaos_check.prometheus_plugin")
    def test_metrics_capture_called_when_enabled(self, mock_plugin):
        result = run_pre_chaos_check(**self._base_kwargs(enable_metrics=True))
        mock_plugin.metrics.assert_called_once()
        self.assertTrue(result.ran)
        self.assertFalse(result.failed)
        self.assertFalse(result.should_exit)

    @patch("krkn.alert_health_check.pre_chaos_check.prometheus_plugin")
    def test_exit_on_pre_check_failure_true_signals_exit(self, mock_plugin):
        def fake_critical_alerts(prom, summary, *args, **kwargs):
            summary.post_chaos_alerts.append("ALERT")

        mock_plugin.critical_alerts.side_effect = fake_critical_alerts
        result = run_pre_chaos_check(
            **self._base_kwargs(
                check_critical_alerts=True, exit_on_pre_check_failure=True
            )
        )
        self.assertTrue(result.failed)
        self.assertTrue(result.should_exit)

    @patch("krkn.alert_health_check.pre_chaos_check.prometheus_plugin")
    def test_exit_on_pre_check_failure_false_does_not_exit(self, mock_plugin):
        def fake_critical_alerts(prom, summary, *args, **kwargs):
            summary.post_chaos_alerts.append("ALERT")

        mock_plugin.critical_alerts.side_effect = fake_critical_alerts
        result = run_pre_chaos_check(
            **self._base_kwargs(
                check_critical_alerts=True, exit_on_pre_check_failure=False
            )
        )
        self.assertTrue(result.failed)
        self.assertFalse(result.should_exit)

    @patch("krkn.alert_health_check.pre_chaos_check.prometheus_plugin")
    def test_empty_chaos_scenarios_skips(self, mock_plugin):
        result = run_pre_chaos_check(
            **self._base_kwargs(chaos_scenarios=[], check_critical_alerts=True)
        )
        self.assertFalse(result.ran)
        self.assertFalse(result.failed)
        self.assertFalse(result.should_exit)
        mock_plugin.critical_alerts.assert_not_called()

    @patch("krkn.alert_health_check.pre_chaos_check.prometheus_plugin")
    def test_no_flags_enabled_skips(self, mock_plugin):
        result = run_pre_chaos_check(**self._base_kwargs())
        self.assertFalse(result.ran)
        mock_plugin.critical_alerts.assert_not_called()
        mock_plugin.alerts.assert_not_called()
        mock_plugin.metrics.assert_not_called()


if __name__ == "__main__":
    unittest.main()
