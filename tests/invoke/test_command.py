#!/usr/bin/env python3

"""
Test suite for krkn/invoke/command.py

This test file provides comprehensive coverage for command invocation functions:
- invoke: Execute command and exit on failure
- invoke_no_exit: Execute command and return error on failure
- run: Execute command and pass on exception

Usage:
    python3 -m coverage run --source=krkn -m pytest tests/invoke/test_command.py -q
    python3 -m coverage report -m --include=krkn/invoke/command.py
"""

import unittest
from unittest.mock import patch, MagicMock
import subprocess
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from krkn.invoke.command import invoke, invoke_no_exit, run


class TestInvokeCommand(unittest.TestCase):
    """Test suite for invoke function"""

    @patch('krkn.invoke.command.subprocess.check_output')
    def test_invoke_success(self, mock_check_output):
        """Test invoke returns command output on success"""
        mock_check_output.return_value = "command output"
        
        result = invoke("echo hello")
        
        self.assertEqual(result, "command output")
        mock_check_output.assert_called_once_with(
            "echo hello",
            shell=True,
            universal_newlines=True,
            timeout=None
        )

    @patch('krkn.invoke.command.subprocess.check_output')
    def test_invoke_with_timeout(self, mock_check_output):
        """Test invoke passes timeout parameter"""
        mock_check_output.return_value = "output"
        
        result = invoke("echo test", timeout=30)
        
        self.assertEqual(result, "output")
        mock_check_output.assert_called_once_with(
            "echo test",
            shell=True,
            universal_newlines=True,
            timeout=30
        )

    @patch('krkn.invoke.command.sys.exit')
    @patch('krkn.invoke.command.subprocess.check_output')
    def test_invoke_failure_exits(self, mock_check_output, mock_exit):
        """Test invoke calls sys.exit(1) on failure"""
        mock_check_output.side_effect = subprocess.CalledProcessError(1, "cmd")
        
        invoke("failing_command")
        
        mock_exit.assert_called_once_with(1)

    @patch('krkn.invoke.command.sys.exit')
    @patch('krkn.invoke.command.subprocess.check_output')
    def test_invoke_timeout_exception_exits(self, mock_check_output, mock_exit):
        """Test invoke calls sys.exit(1) on timeout"""
        mock_check_output.side_effect = subprocess.TimeoutExpired("cmd", 10)
        
        invoke("slow_command", timeout=10)
        
        mock_exit.assert_called_once_with(1)


class TestInvokeNoExit(unittest.TestCase):
    """Test suite for invoke_no_exit function"""

    @patch('krkn.invoke.command.subprocess.check_output')
    def test_invoke_no_exit_success(self, mock_check_output):
        """Test invoke_no_exit returns command output on success"""
        mock_check_output.return_value = "success output"
        
        result = invoke_no_exit("echo hello")
        
        self.assertEqual(result, "success output")
        mock_check_output.assert_called_once_with(
            "echo hello",
            shell=True,
            universal_newlines=True,
            timeout=15,
            stderr=subprocess.DEVNULL
        )

    @patch('krkn.invoke.command.subprocess.check_output')
    def test_invoke_no_exit_with_custom_timeout(self, mock_check_output):
        """Test invoke_no_exit passes custom timeout parameter"""
        mock_check_output.return_value = "output"
        
        result = invoke_no_exit("echo test", timeout=30)
        
        self.assertEqual(result, "output")
        mock_check_output.assert_called_once_with(
            "echo test",
            shell=True,
            universal_newlines=True,
            timeout=30,
            stderr=subprocess.DEVNULL
        )

    @patch('krkn.invoke.command.subprocess.check_output')
    def test_invoke_no_exit_failure_returns_error(self, mock_check_output):
        """Test invoke_no_exit returns error string on failure"""
        error = subprocess.CalledProcessError(1, "cmd", output="error output")
        mock_check_output.side_effect = error
        
        result = invoke_no_exit("failing_command")
        
        # Should return the string representation of the exception
        self.assertIsInstance(result, str)
        self.assertIn("returned non-zero exit status", result)

    @patch('krkn.invoke.command.subprocess.check_output')
    def test_invoke_no_exit_timeout_returns_error(self, mock_check_output):
        """Test invoke_no_exit returns error string on timeout"""
        error = subprocess.TimeoutExpired("cmd", 15)
        mock_check_output.side_effect = error
        
        result = invoke_no_exit("slow_command")
        
        self.assertIsInstance(result, str)
        self.assertIn("timed out", result.lower())


class TestRun(unittest.TestCase):
    """Test suite for run function"""

    @patch('krkn.invoke.command.subprocess.run')
    def test_run_success(self, mock_run):
        """Test run executes command successfully"""
        mock_run.return_value = MagicMock()
        
        run("echo hello")
        
        mock_run.assert_called_once_with(
            "echo hello",
            shell=True,
            universal_newlines=True,
            timeout=45
        )

    @patch('krkn.invoke.command.subprocess.run')
    def test_run_exception_passes(self, mock_run):
        """Test run passes silently on exception"""
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
        
        # Should not raise exception
        run("failing_command")
        
        mock_run.assert_called_once()

    @patch('krkn.invoke.command.subprocess.run')
    def test_run_timeout_passes(self, mock_run):
        """Test run passes silently on timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 45)
        
        # Should not raise exception
        run("slow_command")
        
        mock_run.assert_called_once()

    @patch('krkn.invoke.command.subprocess.run')
    def test_run_generic_exception_passes(self, mock_run):
        """Test run passes silently on generic exception"""
        mock_run.side_effect = Exception("Generic error")
        
        # Should not raise exception
        run("some_command")
        
        mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
