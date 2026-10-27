#!/usr/bin/env python3

"""
Test suite for CommandTrigger class

Usage:
    python -m coverage run -a -m unittest tests/test_triggers/test_command_trigger.py -v

Assisted By: Claude Code
"""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from krkn.scenario_plugins.triggers.command_trigger import (
    COMMAND_TIMEOUT_SECONDS,
    CommandTrigger,
)


class TestCommandTrigger(unittest.TestCase):

    def _make_trigger(self, **overrides):
        """Build a CommandTrigger with sensible defaults."""
        config = {"cmd": "echo hello", "expected_rc": 0}
        config.update(overrides)
        return CommandTrigger(config)

    # ------------------------------------------------------------------
    # evaluate() tests
    # ------------------------------------------------------------------

    @patch("krkn.scenario_plugins.triggers.command_trigger.subprocess.run")
    def test_evaluate_success(self, mock_run):
        """Command exits 0, expected_rc=0 -> returns True."""
        mock_run.return_value = MagicMock(returncode=0)
        trigger = self._make_trigger(cmd="echo ok", expected_rc=0)

        self.assertTrue(trigger.evaluate())
        mock_run.assert_called_once_with(
            "echo ok",
            shell=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )

    @patch("krkn.scenario_plugins.triggers.command_trigger.subprocess.run")
    def test_evaluate_failure(self, mock_run):
        """Command exits 1, expected_rc=0 -> returns False."""
        mock_run.return_value = MagicMock(returncode=1)
        trigger = self._make_trigger(cmd="false", expected_rc=0)

        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.command_trigger.subprocess.run")
    def test_evaluate_custom_expected_rc(self, mock_run):
        """Command exits 42, expected_rc=42 -> returns True."""
        mock_run.return_value = MagicMock(returncode=42)
        trigger = self._make_trigger(cmd="exit 42", expected_rc=42)

        self.assertTrue(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.command_trigger.subprocess.run")
    def test_evaluate_inline_command(self, mock_run):
        """Uses 'inline' field instead of 'cmd'."""
        mock_run.return_value = MagicMock(returncode=0)
        trigger = CommandTrigger({"inline": "date"})

        self.assertTrue(trigger.evaluate())
        mock_run.assert_called_once_with(
            "date",
            shell=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )

    @patch("krkn.scenario_plugins.triggers.command_trigger.subprocess.run")
    def test_cmd_takes_precedence_over_inline(self, mock_run):
        """Both 'cmd' and 'inline' provided; 'cmd' is used."""
        mock_run.return_value = MagicMock(returncode=0)
        trigger = CommandTrigger({"cmd": "use-this", "inline": "not-this"})

        trigger.evaluate()
        args, _ = mock_run.call_args
        self.assertEqual(args[0], "use-this")

    @patch("krkn.scenario_plugins.triggers.command_trigger.subprocess.run")
    def test_evaluate_timeout(self, mock_run):
        """Command hangs, subprocess times out -> returns False."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="sleep 999", timeout=COMMAND_TIMEOUT_SECONDS
        )
        trigger = self._make_trigger(cmd="sleep 999")

        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.command_trigger.subprocess.run")
    def test_evaluate_command_not_found(self, mock_run):
        """Binary does not exist -> returns False."""
        mock_run.side_effect = FileNotFoundError("No such file")
        trigger = self._make_trigger(cmd="/nonexistent/binary")

        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.command_trigger.subprocess.run")
    def test_evaluate_unexpected_exception(self, mock_run):
        """Unexpected exception (e.g. PermissionError) -> returns False, no crash."""
        mock_run.side_effect = PermissionError("Permission denied")
        trigger = self._make_trigger(cmd="/restricted/script.sh")

        self.assertFalse(trigger.evaluate())

    @patch("krkn.scenario_plugins.triggers.command_trigger.subprocess.run")
    def test_evaluate_default_expected_rc(self, mock_run):
        """No expected_rc in config -> defaults to 0."""
        mock_run.return_value = MagicMock(returncode=0)
        trigger = CommandTrigger({"cmd": "true"})

        self.assertTrue(trigger.evaluate())
        self.assertEqual(trigger._expected_rc, 0)

    # ------------------------------------------------------------------
    # describe() tests
    # ------------------------------------------------------------------

    def test_describe(self):
        """Returns a meaningful description string."""
        trigger = self._make_trigger(cmd="check_service.sh", expected_rc=0)
        description = trigger.describe()

        self.assertIn("check_service.sh", description)
        self.assertIn("0", description)
        self.assertIsInstance(description, str)
        self.assertTrue(len(description) > 0)

    # ------------------------------------------------------------------
    # Validation tests
    # ------------------------------------------------------------------

    def test_missing_cmd_and_inline(self):
        """Neither 'cmd' nor 'inline' provided -> raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            CommandTrigger({})

        self.assertIn("cmd", str(ctx.exception).lower())
        self.assertIn("inline", str(ctx.exception).lower())

    def test_expected_rc_string_coerced_to_int(self):
        """expected_rc='0' (string from envsubst) -> coerced to int 0."""
        trigger = CommandTrigger({"cmd": "true", "expected_rc": "0"})
        self.assertEqual(trigger._expected_rc, 0)
        self.assertIsInstance(trigger._expected_rc, int)

    def test_expected_rc_invalid_raises(self):
        """expected_rc='abc' -> raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            CommandTrigger({"cmd": "true", "expected_rc": "abc"})
        self.assertIn("expected_rc", str(ctx.exception))

    def test_expected_rc_above_255_raises(self):
        """expected_rc=999 -> raises ValueError (Unix rc range is 0-255)."""
        with self.assertRaises(ValueError) as ctx:
            CommandTrigger({"cmd": "true", "expected_rc": 999})
        self.assertIn("255", str(ctx.exception))

    def test_expected_rc_negative_raises(self):
        """expected_rc=-1 -> raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            CommandTrigger({"cmd": "true", "expected_rc": -1})
        self.assertIn("expected_rc", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
