#!/usr/bin/env python3

"""
Test suite for TimeActionsScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_time_actions_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch, call

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
    @unittest.mock.patch('yaml.full_load')
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
    @unittest.mock.patch('yaml.full_load')
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


    def test_detect_available_shell_finds_bash(self):
        """Test shell detection finds /bin/bash"""
        kubecli_mock = MagicMock()
        kubecli_mock.exec_cmd_in_pod.return_value = "exists"
        
        shell = self.plugin.detect_available_shell(
            "pod1", "ns1", "container1", kubecli_mock
        )
        
        self.assertEqual(shell, "/bin/bash")
        kubecli_mock.exec_cmd_in_pod.assert_called_once()

    def test_detect_available_shell_fallback_to_sh(self):
        """Test falls back to /bin/sh when bash unavailable"""
        kubecli_mock = MagicMock()
        # First call (bash) fails, second call (sh) succeeds
        kubecli_mock.exec_cmd_in_pod.side_effect = [
            "bash: not found",  # bash fails
            "exists"            # sh succeeds
        ]
        
        shell = self.plugin.detect_available_shell(
            "pod1", "ns1", "container1", kubecli_mock
        )
        
        self.assertEqual(shell, "/bin/sh")
        self.assertEqual(kubecli_mock.exec_cmd_in_pod.call_count, 2)

    def test_detect_available_shell_fallback_to_busybox(self):
        """Test falls back to /busybox/sh when bash and sh unavailable"""
        kubecli_mock = MagicMock()
        # First two calls fail, third call (busybox) succeeds
        kubecli_mock.exec_cmd_in_pod.side_effect = [
            "bash: not found",  # bash fails
            "sh: not found",    # sh fails
            "exists"            # busybox succeeds
        ]
        
        shell = self.plugin.detect_available_shell(
            "pod1", "ns1", "container1", kubecli_mock
        )
        
        self.assertEqual(shell, "/busybox/sh")
        self.assertEqual(kubecli_mock.exec_cmd_in_pod.call_count, 3)

    def test_detect_available_shell_no_shell_available(self):
        """Test returns None when no shells available"""
        kubecli_mock = MagicMock()
        kubecli_mock.exec_cmd_in_pod.side_effect = Exception("No shell found")
        
        shell = self.plugin.detect_available_shell(
            "pod1", "ns1", "container1", kubecli_mock
        )
        
        self.assertIsNone(shell)

    @patch('shlex.quote')
    def test_exec_with_shell_fallback_handles_quotes(self, mock_shlex_quote):
        """Test proper escaping of commands with quotes"""
        kubecli_mock = MagicMock()
        kubecli_mock.exec_cmd_in_pod.return_value = "test output"
        mock_shlex_quote.return_value = "'echo '\"'\"'hello world'\"'\"''"
        
        # Command with quotes should not break
        with patch.object(
            self.plugin, 'detect_available_shell', return_value='/bin/sh'
        ):
            result = self.plugin.exec_with_shell_fallback(
                "pod1", "echo 'hello world'", "ns1", "container1", kubecli_mock
            )
        
        self.assertIsNotNone(result)
        self.assertEqual(result, "test output")
        # Verify shlex.quote was called
        mock_shlex_quote.assert_called_once_with("echo 'hello world'")

    def test_exec_with_shell_fallback_handles_list_command(self):
        """Test that list commands are properly converted to strings"""
        kubecli_mock = MagicMock()
        kubecli_mock.exec_cmd_in_pod.return_value = "success"
        
        with patch.object(
            self.plugin, 'detect_available_shell', return_value='/bin/sh'
        ):
            result = self.plugin.exec_with_shell_fallback(
                "pod1", ["echo", "hello"], "ns1", "container1", kubecli_mock
            )
        
        self.assertEqual(result, "success")

    def test_exec_with_shell_fallback_already_wrapped_command(self):
        """Test that already-wrapped commands are not double-wrapped"""
        kubecli_mock = MagicMock()
        kubecli_mock.exec_cmd_in_pod.return_value = "success"
        
        with patch.object(
            self.plugin, 'detect_available_shell', return_value='/bin/sh'
        ):
            result = self.plugin.exec_with_shell_fallback(
                "pod1", "/bin/bash -c 'date'", "ns1", "container1", kubecli_mock
            )
        
        self.assertEqual(result, "success")
        # Verify the command was used as-is (not wrapped again)
        call_args = kubecli_mock.exec_cmd_in_pod.call_args[0]
        self.assertEqual(call_args[0], "/bin/bash -c 'date'")

    def test_exec_with_shell_fallback_no_shell_available(self):
        """Test fallback returns False when no shell is available"""
        kubecli_mock = MagicMock()
        
        with patch.object(
            self.plugin, 'detect_available_shell', return_value=None
        ):
            result = self.plugin.exec_with_shell_fallback(
                "pod1", "date", "ns1", "container1", kubecli_mock
            )
        
        self.assertFalse(result)

    def test_pod_exec_triggers_fallback_on_shell_error(self):
        """Test pod_exec activates fallback when seeing shell error"""
        kubecli_mock = MagicMock()
        kubecli_mock.exec_cmd_in_pod.return_value = (
            "impossible to determine the shell to run command"
        )
        
        with patch.object(
            self.plugin, 'exec_with_shell_fallback', return_value="success"
        ) as fallback_mock:
            result = self.plugin.pod_exec(
                "pod1", "date", "ns1", "container1", kubecli_mock
            )
        
        fallback_mock.assert_called_once_with(
            "pod1", "date", "ns1", "container1", kubecli_mock
        )
        self.assertEqual(result, "success")

    def test_exec_with_shell_fallback_detects_persistent_shell_error(self):
        """Test fallback detects when shell error persists"""
        kubecli_mock = MagicMock()
        # Shell detection succeeds, but execution still fails with shell error
        kubecli_mock.exec_cmd_in_pod.side_effect = [
            "exists",  # Shell detection succeeds
            "impossible to determine the shell"  # But execution fails
        ]
        
        with patch.object(
            self.plugin, 'detect_available_shell', return_value='/bin/sh'
        ):
            result = self.plugin.exec_with_shell_fallback(
                "pod1", "date", "ns1", "container1", kubecli_mock
            )
        
        self.assertFalse(result)

    def test_exec_with_shell_fallback_retries_on_error(self):
        """Test fallback retries on transient errors"""
        kubecli_mock = MagicMock()
        # First few attempts fail, last one succeeds
        kubecli_mock.exec_cmd_in_pod.side_effect = [
            "exists",  # Shell detection
            "exec failed: connection reset",  # Attempt 1
            "error: timeout",  # Attempt 2
            "success"  # Attempt 3
        ]
        
        with patch.object(
            self.plugin, 'detect_available_shell', return_value='/bin/sh'
        ):
            result = self.plugin.exec_with_shell_fallback(
                "pod1", "date", "ns1", "container1", kubecli_mock
            )
        
        self.assertEqual(result, "success")

    def test_exec_with_shell_fallback_fails_after_max_retries(self):
        """Test fallback returns False after exhausting retries"""
        kubecli_mock = MagicMock()
        # All attempts fail
        kubecli_mock.exec_cmd_in_pod.side_effect = [
            "exists",  # Shell detection
            "error",  # Attempt 1
            "error",  # Attempt 2
            "error",  # Attempt 3
            "error",  # Attempt 4
            "error",  # Attempt 5
        ]
        
        with patch.object(
            self.plugin, 'detect_available_shell', return_value='/bin/sh'
        ):
            result = self.plugin.exec_with_shell_fallback(
                "pod1", "date", "ns1", "container1", kubecli_mock
            )
        
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
