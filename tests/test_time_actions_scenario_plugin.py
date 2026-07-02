#!/usr/bin/env python3

"""
Test suite for TimeActionsScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_time_actions_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.time_actions.time_actions_scenario_plugin import TimeActionsScenarioPlugin


class TestTimeActionsScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for TimeActionsScenarioPlugin
        """
        self.plugin = TimeActionsScenarioPlugin()

    def tearDown(self):
        """Clean up after each test to prevent state leakage"""
        self.plugin = None

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["time_scenarios"])
        self.assertEqual(len(result), 1)

    @patch("krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.logging")
    @patch("builtins.open", side_effect=RuntimeError("disk quota exceeded"))
    def test_exception_variable_bound_in_except_handler(self, mock_open, mock_logging):
        """run() must bind exception variable so logging shows actual error, not NameError"""
        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario="fake_scenario.yaml",
            lib_telemetry=MagicMock(),
            scenario_telemetry=MagicMock(),
        )

        self.assertEqual(result, 1)
        logged_msg = mock_logging.error.call_args[0][0]
        self.assertIn("disk quota exceeded", logged_msg)
        self.assertNotIn("NameError", logged_msg)
    @unittest.mock.patch('builtins.open', create=True)
    @unittest.mock.patch('yaml.safe_load')
    @unittest.mock.patch('logging.error')
    def test_run_exception_handling_with_variable(self, mock_logging_error, mock_yaml, mock_open):
        """
        Test that run() properly captures exception variable and logs it
        This tests the fix for the undefined variable 'e' bug
        """
        # Setup mock to raise exception
        mock_yaml.side_effect = RuntimeError("Test exception message")
        
        mock_lib_telemetry = MagicMock()
        mock_scenario_telemetry = MagicMock()
        
        # Execute the run method
        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario="test_scenario.yaml",
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry
        )
        
        # Assert failure is returned
        self.assertEqual(result, 1)
        
        # Assert logging.error was called with the exception message
        mock_logging_error.assert_called_once()
        error_call_args = str(mock_logging_error.call_args)
        self.assertIn("Test exception message", error_call_args)
        self.assertIn("TimeActionsScenarioPlugin", error_call_args)

    @unittest.mock.patch('builtins.open', create=True)
    @unittest.mock.patch('yaml.safe_load')
    def test_run_with_skew_time_exception(self, mock_yaml, mock_open):
        """
        Test that run() handles exceptions from skew_time method
        """
        # Setup mock scenario config
        mock_yaml.return_value = {
            "time_scenarios": [
                {
                    "action": "skew_time",
                    "object_type": "node",
                    "object_name": ["test-node"]
                }
            ]
        }
        
        mock_lib_telemetry = MagicMock()
        mock_kubecli = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_kubecli
        
        # Make skew_time raise an exception
        with unittest.mock.patch.object(self.plugin, 'skew_time', side_effect=Exception("Skew failed")):
            mock_scenario_telemetry = MagicMock()
                
            # Execute the run method
            result = self.plugin.run(
                run_uuid="test-uuid",
                scenario="test_scenario.yaml",
                    lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry
            )
            
            # Assert failure is returned
            self.assertEqual(result, 1)

    @patch('krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.KrknKubernetes')
    def test_exec_with_shell_fallback_detects_persistent_shell_error(self, mock_kubecli_class):
        """Test that exec_with_shell_fallback returns False when both direct and shell execution fail persistently"""
        mock_kubecli = MagicMock()
        mock_kubecli_class.return_value = mock_kubecli
        mock_kubecli.exec_cmd_in_pod.side_effect = Exception("Command failed")
        
        result = self.plugin.exec_with_shell_fallback(
            "test", "test-pod", "default", "test-container", mock_kubecli
        )
        
        self.assertFalse(result)

    @patch('krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.KrknKubernetes')
    def test_exec_with_shell_fallback_fails_after_max_retries(self, mock_kubecli_class):
        """Test that exec_with_shell_fallback returns False after exhausting all retries"""
        mock_kubecli = MagicMock()
        mock_kubecli_class.return_value = mock_kubecli
        mock_kubecli.exec_cmd_in_pod.side_effect = Exception("Command failed")
        
        result = self.plugin.exec_with_shell_fallback(
            "test", "test-pod", "default", "test-container", mock_kubecli, max_retries=2
        )
        
        self.assertFalse(result)

    @patch('krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.KrknKubernetes')
    def test_exec_with_shell_fallback_retries_on_error(self, mock_kubecli_class):
        """Test that exec_with_shell_fallback succeeds after retrying"""
        mock_kubecli = MagicMock()
        mock_kubecli_class.return_value = mock_kubecli
        # First two calls fail, third succeeds
        mock_kubecli.exec_cmd_in_pod.side_effect = [
            Exception("First failure"),
            Exception("Second failure"), 
            "success"
        ]
        
        result = self.plugin.exec_with_shell_fallback(
            "test", "test-pod", "default", "test-container", mock_kubecli, max_retries=3
        )
        
        self.assertEqual(result, "success")

    @patch('krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.time.sleep')
    def test_pod_exec_handles_exceptions(self, mock_sleep):
        """Test that pod_exec catches transient exceptions and retries"""
        mock_kubecli = MagicMock()
        mock_kubecli.exec_cmd_in_pod.side_effect = [Exception("Network error"), "impossible to determine the shell", "success"]
        
        result = self.plugin.pod_exec("pod", "cmd", "ns", "container", mock_kubecli)
        
        self.assertEqual(result, "success")
        self.assertEqual(mock_kubecli.exec_cmd_in_pod.call_count, 3)

    @patch('krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.datetime')
    @patch('krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.time.sleep')
    def test_check_date_time_pod_retry_on_exception(self, mock_sleep, mock_dt):
        """Test that check_date_time for pods retries on transient failures then succeeds"""
        import datetime as real_dt

        mock_dt.MINYEAR = real_dt.MINYEAR
        mock_dt.datetime.side_effect = lambda *a, **k: real_dt.datetime(*a, **k)

        t_first = real_dt.datetime(2026, 1, 1, 0, 0, 0)
        t_parsed = real_dt.datetime(2026, 1, 1, 0, 5, 0)
        t_after = real_dt.datetime(2026, 1, 1, 0, 10, 0)

        # Trace of utcnow() calls:
        #   1. line 401: first_date_time = utcnow()  →  t_first
        #   2. iter 0: pod_exec→False, pod_datetime stays MINYEAR, line 419 utcnow()  →  anything (comparison fails)
        #   3. iter 1: pod_exec→False, same, line 419 utcnow()
        #   4. iter 2: pod_exec→"str", string_to_date→t_parsed, line 419 utcnow()  →  t_after  (t_first < t_parsed < t_after → success!)
        utcnow_returns = iter([t_first, t_after, t_after, t_after])
        mock_dt.datetime.utcnow = MagicMock(side_effect=lambda: next(utcnow_returns, t_after))

        mock_kubecli = MagicMock()

        with patch.object(self.plugin, 'pod_exec') as mock_pod_exec, \
             patch.object(self.plugin, 'string_to_date') as mock_s2d:

            mock_pod_exec.side_effect = [False, False, "Thu Jan  1 00:05:00 UTC 2026"]
            mock_s2d.return_value = t_parsed

            names = [["test-pod", "default", "test-container"]]
            not_reset = self.plugin.check_date_time("pod", names, mock_kubecli)

            self.assertEqual(not_reset, [])
            self.assertEqual(mock_pod_exec.call_count, 3)
            self.assertEqual(mock_sleep.call_count, 2)

    @patch('krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.datetime')
    @patch('krkn.scenario_plugins.time_actions.time_actions_scenario_plugin.time.sleep')
    def test_check_date_time_node_retry_on_exception(self, mock_sleep, mock_dt):
        """Test that check_date_time for nodes retries on transient exec errors then succeeds"""
        import datetime as real_dt

        mock_dt.MINYEAR = real_dt.MINYEAR
        mock_dt.datetime.side_effect = lambda *a, **k: real_dt.datetime(*a, **k)

        t_first = real_dt.datetime(2026, 1, 1, 0, 0, 0)
        t_parsed = real_dt.datetime(2026, 1, 1, 0, 5, 0)
        t_after = real_dt.datetime(2026, 1, 1, 0, 10, 0)

        # Trace of utcnow() calls:
        #   1. line 349: first_date_time = utcnow()  →  t_first
        #   2. iter 0 (counter==0): exec_command_on_node raises, line 375 utcnow()  →  anything
        #   3. iter 1 (counter==1): exec_cmd_in_pod succeeds, string_to_date→t_parsed, line 375 utcnow() → t_after
        utcnow_returns = iter([t_first, t_after, t_after])
        mock_dt.datetime.utcnow = MagicMock(side_effect=lambda: next(utcnow_returns, t_after))

        mock_kubecli = MagicMock()
        mock_kubecli.exec_command_on_node.side_effect = Exception("TLS handshake error")
        mock_kubecli.exec_cmd_in_pod.return_value = "Thu Jan  1 00:05:00 UTC 2026"

        with patch.object(self.plugin, 'string_to_date') as mock_s2d:
            mock_s2d.return_value = t_parsed

            names = ["test-node"]
            not_reset = self.plugin.check_date_time("node", names, mock_kubecli)

            self.assertEqual(not_reset, [])
            self.assertEqual(mock_kubecli.exec_command_on_node.call_count, 1)
            self.assertEqual(mock_kubecli.exec_cmd_in_pod.call_count, 1)
            self.assertEqual(mock_sleep.call_count, 1)


if __name__ == "__main__":
    unittest.main()

