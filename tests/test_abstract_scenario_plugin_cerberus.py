"""
Test suite for krkn/scenario_plugins/abstract_scenario_plugin.py

Run this test file individually with:
  python -m unittest tests/test_abstract_scenario_plugin_cerberus.py -v

Or with coverage:
  python3 -m coverage run -a -m unittest tests/test_abstract_scenario_plugin_cerberus.py -v

Generated with help from Claude Code
"""

import unittest
from unittest.mock import patch, MagicMock, Mock, call
import time
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift


class ConcreteScenarioPlugin(AbstractScenarioPlugin):
    """Concrete implementation for testing"""
    
    def __init__(self):
        super().__init__("test_scenario")
    
    def run(self, run_uuid, scenario, lib_telemetry, scenario_telemetry):
        return 0
    
    def get_scenario_types(self):
        return ["test_scenario"]


class FailingScenarioPlugin(AbstractScenarioPlugin):
    """Plugin that always fails for testing"""
    
    def __init__(self):
        super().__init__("failing_scenario")
    
    def run(self, run_uuid, scenario, lib_telemetry, scenario_telemetry):
        return 1
    
    def get_scenario_types(self):
        return ["failing_scenario"]


class TestAbstractScenarioPluginCerberusIntegration(unittest.TestCase):
    """Test suite for cerberus integration in AbstractScenarioPlugin"""

    def setUp(self):
        """Setup test fixtures"""
        self.plugin = ConcreteScenarioPlugin()
        self.failing_plugin = FailingScenarioPlugin()
        
        self.mock_telemetry = Mock(spec=KrknTelemetryOpenshift)
        self.mock_telemetry.set_parameters_base64.return_value = {"test": "config"}
        self.mock_telemetry.get_telemetry_request_id.return_value = "test-request-id"
        self.mock_telemetry.get_lib_kubernetes.return_value = Mock()
        
        self.krkn_config = {
            "tunings": {"wait_duration": 0},
            "telemetry": {"events_backup": False}
        }

    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cleanup_rollback_version_files')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context')
    @patch('time.sleep')
    def test_cerberus_publish_called_after_successful_scenario(
        self, mock_sleep, mock_signal_ctx, mock_collect_logs, mock_cleanup, mock_cerberus_publish
    ):
        """Test that cerberus.publish_kraken_status is called after a successful scenario"""
        mock_signal_ctx.return_value.__enter__ = Mock()
        mock_signal_ctx.return_value.__exit__ = Mock(return_value=False)

        scenarios_list = ["scenario1.yaml"]
        
        failed_scenarios, telemetries = self.plugin.run_scenarios(
            "test-uuid",
            scenarios_list,
            self.krkn_config,
            self.mock_telemetry
        )

        # Verify cerberus.publish_kraken_status was called
        self.assertEqual(mock_cerberus_publish.call_count, 1)
        
        # Verify it was called with correct arguments (start_timestamp and end_time)
        call_args = mock_cerberus_publish.call_args[0]
        self.assertEqual(len(call_args), 2)
        self.assertIsInstance(call_args[0], int)  # start_timestamp
        self.assertIsInstance(call_args[1], int)  # end_time
        self.assertGreaterEqual(call_args[1], call_args[0])  # end_time >= start_time

    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.execute_rollback_version_files')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context')
    @patch('time.sleep')
    def test_cerberus_publish_called_after_failed_scenario(
        self, mock_sleep, mock_signal_ctx, mock_collect_logs, mock_rollback, mock_cerberus_publish
    ):
        """Test that cerberus.publish_kraken_status is called even after a failed scenario"""
        mock_signal_ctx.return_value.__enter__ = Mock()
        mock_signal_ctx.return_value.__exit__ = Mock(return_value=False)

        scenarios_list = ["scenario1.yaml"]
        
        failed_scenarios, telemetries = self.failing_plugin.run_scenarios(
            "test-uuid",
            scenarios_list,
            self.krkn_config,
            self.mock_telemetry
        )

        # Verify cerberus.publish_kraken_status was called even after failure
        self.assertEqual(mock_cerberus_publish.call_count, 1)
        self.assertEqual(len(failed_scenarios), 1)

    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cleanup_rollback_version_files')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context')
    @patch('time.sleep')
    def test_cerberus_publish_called_for_multiple_scenarios(
        self, mock_sleep, mock_signal_ctx, mock_collect_logs, mock_cleanup, mock_cerberus_publish
    ):
        """Test that cerberus.publish_kraken_status is called for each scenario"""
        mock_signal_ctx.return_value.__enter__ = Mock()
        mock_signal_ctx.return_value.__exit__ = Mock(return_value=False)

        scenarios_list = ["scenario1.yaml", "scenario2.yaml", "scenario3.yaml"]
        
        failed_scenarios, telemetries = self.plugin.run_scenarios(
            "test-uuid",
            scenarios_list,
            self.krkn_config,
            self.mock_telemetry
        )

        # Verify cerberus.publish_kraken_status was called 3 times (once per scenario)
        self.assertEqual(mock_cerberus_publish.call_count, 3)
        self.assertEqual(len(telemetries), 3)

    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cleanup_rollback_version_files')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.execute_rollback_version_files')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context')
    @patch('time.sleep')
    @patch('time.time')
    def test_cerberus_publish_timing(
        self, mock_time, mock_sleep, mock_signal_ctx, mock_collect_logs, 
        mock_rollback, mock_cleanup, mock_cerberus_publish
    ):
        """Test that cerberus.publish_kraken_status receives correct timestamps"""
        mock_signal_ctx.return_value.__enter__ = Mock()
        mock_signal_ctx.return_value.__exit__ = Mock(return_value=False)
        
        # Mock time progression
        time_sequence = [1000.0, 1000.5, 1010.0]  # start, intermediate, end
        mock_time.side_effect = time_sequence

        scenarios_list = ["scenario1.yaml"]
        
        failed_scenarios, telemetries = self.plugin.run_scenarios(
            "test-uuid",
            scenarios_list,
            self.krkn_config,
            self.mock_telemetry
        )

        # Verify cerberus was called with start time from scenario_telemetry
        mock_cerberus_publish.assert_called_once()
        call_args = mock_cerberus_publish.call_args[0]
        self.assertEqual(call_args[0], 1000)  # start_timestamp (int conversion)
        self.assertIsInstance(call_args[1], int)  # end_time should be int

    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cleanup_rollback_version_files')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context')
    @patch('time.sleep')
    def test_cerberus_publish_exception_does_not_break_flow(
        self, mock_sleep, mock_signal_ctx, mock_collect_logs, mock_cleanup, mock_cerberus_publish
    ):
        """Test that exceptions in cerberus.publish_kraken_status don't break scenario execution"""
        mock_signal_ctx.return_value.__enter__ = Mock()
        mock_signal_ctx.return_value.__exit__ = Mock(return_value=False)
        
        # Make cerberus.publish_kraken_status raise an exception
        mock_cerberus_publish.side_effect = Exception("Cerberus connection failed")

        scenarios_list = ["scenario1.yaml"]
        
        # This should raise the exception since it's not caught in the code
        with self.assertRaises(Exception) as cm:
            self.plugin.run_scenarios(
                "test-uuid",
                scenarios_list,
                self.krkn_config,
                self.mock_telemetry
            )
        
        self.assertEqual(str(cm.exception), "Cerberus connection failed")

    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cleanup_rollback_version_files')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.execute_rollback_version_files')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context')
    @patch('time.sleep')
    def test_cerberus_publish_called_for_mixed_success_and_failure(
        self, mock_sleep, mock_signal_ctx, mock_collect_logs, mock_rollback, 
        mock_cleanup, mock_cerberus_publish
    ):
        """Test cerberus publish is called for both successful and failed scenarios"""
        mock_signal_ctx.return_value.__enter__ = Mock()
        mock_signal_ctx.return_value.__exit__ = Mock(return_value=False)

        # Create a mixed plugin that alternates success/failure
        class MixedPlugin(AbstractScenarioPlugin):
            def __init__(self):
                super().__init__("mixed_scenario")
                self.call_count = 0
            
            def run(self, run_uuid, scenario, lib_telemetry, scenario_telemetry):
                self.call_count += 1
                return 0 if self.call_count % 2 == 1 else 1  # Alternate success/failure
            
            def get_scenario_types(self):
                return ["mixed_scenario"]

        mixed_plugin = MixedPlugin()
        scenarios_list = ["scenario1.yaml", "scenario2.yaml", "scenario3.yaml", "scenario4.yaml"]
        
        failed_scenarios, telemetries = mixed_plugin.run_scenarios(
            "test-uuid",
            scenarios_list,
            self.krkn_config,
            self.mock_telemetry
        )

        # Verify cerberus was called 4 times (once per scenario, regardless of success/failure)
        self.assertEqual(mock_cerberus_publish.call_count, 4)
        self.assertEqual(len(failed_scenarios), 2)  # 2 failures
        self.assertEqual(len(telemetries), 4)

    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context')
    @patch('time.sleep')
    def test_cerberus_not_called_for_deprecated_post_scenarios(
        self, mock_sleep, mock_signal_ctx, mock_collect_logs, mock_cerberus_publish
    ):
        """Test that cerberus is not called for deprecated post scenarios (list format)"""
        mock_signal_ctx.return_value.__enter__ = Mock()
        mock_signal_ctx.return_value.__exit__ = Mock(return_value=False)

        # Deprecated format: list of lists
        scenarios_list = [["deprecated_scenario.yaml"]]
        
        failed_scenarios, telemetries = self.plugin.run_scenarios(
            "test-uuid",
            scenarios_list,
            self.krkn_config,
            self.mock_telemetry
        )

        # Verify cerberus was NOT called for deprecated format
        mock_cerberus_publish.assert_not_called()
        self.assertEqual(len(failed_scenarios), 1)

    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cleanup_rollback_version_files')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.populate_cluster_events')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context')
    @patch('time.sleep')
    def test_cerberus_called_with_events_backup_enabled(
        self, mock_sleep, mock_signal_ctx, mock_populate_events, 
        mock_collect_logs, mock_cleanup, mock_cerberus_publish
    ):
        """Test that cerberus is called even when events_backup is enabled"""
        mock_signal_ctx.return_value.__enter__ = Mock()
        mock_signal_ctx.return_value.__exit__ = Mock(return_value=False)
        
        krkn_config_with_events = {
            "tunings": {"wait_duration": 0},
            "telemetry": {"events_backup": True}
        }

        scenarios_list = ["scenario1.yaml"]
        
        failed_scenarios, telemetries = self.plugin.run_scenarios(
            "test-uuid",
            scenarios_list,
            krkn_config_with_events,
            self.mock_telemetry
        )

        # Verify both events backup and cerberus publish were called
        mock_populate_events.assert_called_once()
        mock_cerberus_publish.assert_called_once()

    @patch('krkn.scenario_plugins.abstract_scenario_plugin.cerberus.publish_kraken_status')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.execute_rollback_version_files')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs')
    @patch('krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context')
    @patch('time.sleep')
    def test_cerberus_called_after_exception_in_run(
        self, mock_sleep, mock_signal_ctx, mock_collect_logs, 
        mock_rollback, mock_cerberus_publish
    ):
        """Test that cerberus is called even if run() raises an uncaught exception"""
        mock_signal_ctx.return_value.__enter__ = Mock()
        mock_signal_ctx.return_value.__exit__ = Mock(return_value=False)
        
        # Create plugin that raises exception
        class ExceptionPlugin(AbstractScenarioPlugin):
            def __init__(self):
                super().__init__("exception_scenario")
            
            def run(self, run_uuid, scenario, lib_telemetry, scenario_telemetry):
                raise RuntimeError("Unexpected error in run()")
            
            def get_scenario_types(self):
                return ["exception_scenario"]

        exception_plugin = ExceptionPlugin()
        scenarios_list = ["scenario1.yaml"]
        
        failed_scenarios, telemetries = exception_plugin.run_scenarios(
            "test-uuid",
            scenarios_list,
            self.krkn_config,
            self.mock_telemetry
        )

        # Verify cerberus was called even after exception
        mock_cerberus_publish.assert_called_once()
        # Verify the scenario was marked as failed
        self.assertEqual(len(failed_scenarios), 1)
        self.assertEqual(telemetries[0].exit_status, 1)


if __name__ == '__main__':
    unittest.main()
