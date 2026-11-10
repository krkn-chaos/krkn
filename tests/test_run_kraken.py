import unittest
from unittest.mock import patch, mock_open
from types import SimpleNamespace

from run_kraken import main


class TestRunKraken(unittest.TestCase):

    @patch('run_kraken.yaml.safe_load')
    @patch('run_kraken.os.path.isfile')
    @patch('builtins.open', new_callable=mock_open)
    def test_main_without_telemetry_config(self, mock_file, mock_isfile, mock_yaml_load):
        """
        Test that main() doesn't crash when config has no telemetry section
        """
        mock_isfile.side_effect = lambda p: p == "/fake/config.yaml"
        mock_yaml_load.return_value = {
            "kraken": {"rollback_versions_directory": "/tmp/krkn-test-rollback"},
            "tunings": {},
            "performance_monitoring": {},
            "elastic": {},
        }

        options = SimpleNamespace(cfg="/fake/config.yaml")
        result = main(options, None)

        self.assertEqual(result, -1)

    def test_blocking_pre_check_exits_before_starting_during_checkers(self):
        """A blocking pre-check must not start continuous health checkers."""
        config = {
            "kraken": {"kubeconfig_path": "/fake/kubeconfig"},
            "tunings": {"iterations": 1},
            "performance_monitoring": {},
            "elastic": {},
            "cerberus": {},
            "telemetry": {},
        }

        class FakeHealthCheckFactory:
            loaded_plugins = {}
            failed_plugins = []

            def __init__(self):
                self.start_all_called = False

            def run_all_once(self, *args, **kwargs):
                return {
                    "passed": False,
                    "failures": [{"message": "unhealthy"}],
                    "details": {},
                    "exit_on_failure": True,
                }

            def start_all(self, *args, **kwargs):
                self.start_all_called = True
                return []

        factory = FakeHealthCheckFactory()
        options = SimpleNamespace(cfg="/fake/config.yaml")

        with patch("run_kraken.os.path.isfile", return_value=True), \
                patch("builtins.open", mock_open()), \
                patch("run_kraken.yaml.safe_load", return_value=config), \
                patch("run_kraken.RollbackConfig.register"), \
                patch("run_kraken.SafeLogger"), \
                patch("run_kraken.KrknKubernetes"), \
                patch("run_kraken.KrknOpenshift") as mock_ocp, \
                patch("run_kraken.KrknTelemetryKubernetes"), \
                patch("run_kraken.KrknTelemetryOpenshift"), \
                patch("run_kraken.ScenarioPluginFactory"), \
                patch("run_kraken.HealthCheckFactory", return_value=factory), \
                patch("run_kraken.collect_health_check_telemetry", return_value=([], [])):
            mock_ocp.return_value.is_openshift.return_value = False
            result = main(options, None)

        self.assertEqual(result, 4)
        self.assertFalse(factory.start_all_called)

    def test_missing_scenario_plugin_exits_before_health_checks_and_scenarios(self):
        """A missing scenario plugin should stop main() before health checks or scenario execution begins. """
        config = {
            "kraken": {
                "kubeconfig_path": "/test/kubeconfig",
                "chaos_scenarios": [
                    {"unknown_scenarios": ["scenarios/kube/unknown.yaml"]}
                ],
            },
            "tunings": {"iterations": 1},
            "performance_monitoring": {},
            "elastic": {},
            "cerberus": {},
            "telemetry": {},
        }

        class TestScenarioPluginFactory:

            def __init__(self):
                self.loaded_plugins = {}
                self.failed_plugins = []
                self.create_plugin_called = False

            def create_plugin(self, scenario_type):
                self.create_plugin_called = True

        class TestHealthCheckFactory:
            def __init__(self):
                self.loaded_plugins = {}
                self.failed_plugins = []
                self.run_all_once_called = False
                self.start_all_called = False

            def run_all_once(self, *args, **kwargs):
                self.run_all_once_called = True
                return {
                    "passed": True,
                    "failures": [],
                    "details": {},
                    "exit_on_failure": True,
                }

            def start_all(self, *args, **kwargs):
                self.start_all_called = True
                return []


        scenario_factory = TestScenarioPluginFactory()
        health_factory = TestHealthCheckFactory()
        options = SimpleNamespace(cfg="/test/config.yaml")

        with patch("run_kraken.os.path.isfile", return_value=True), \
                patch("builtins.open", mock_open()), \
                patch("run_kraken.yaml.safe_load", return_value=config), \
                patch("run_kraken.RollbackConfig.register"), \
                patch("run_kraken.SafeLogger"), \
                patch("run_kraken.KrknKubernetes"), \
                patch("run_kraken.KrknOpenshift") as mock_ocp, \
                patch("run_kraken.KrknTelemetryKubernetes"), \
                patch("run_kraken.KrknTelemetryOpenshift"), \
                patch("run_kraken.ScenarioPluginFactory",return_value=scenario_factory), \
                patch("run_kraken.HealthCheckFactory",return_value=health_factory), \
                patch("run_kraken.collect_health_check_telemetry",return_value=([], [])):
            mock_ocp.return_value.is_openshift.return_value = False
            result = main(options, None)

        self.assertEqual(result, -1)
        self.assertFalse(health_factory.run_all_once_called)
        self.assertFalse(health_factory.start_all_called)
        self.assertFalse(scenario_factory.create_plugin_called)


if __name__ == "__main__":
    unittest.main()
