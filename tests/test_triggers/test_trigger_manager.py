#!/usr/bin/env python3

"""
Test suite for TriggerManager class

Usage:
    python -m coverage run -a -m unittest tests/test_triggers/test_trigger_manager.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import patch

from krkn.scenario_plugins.triggers.abstract_trigger import AbstractTrigger
from krkn.scenario_plugins.triggers.trigger_manager import (
    DEFAULT_INTERVAL,
    DEFAULT_MODE,
    DEFAULT_ON_TIMEOUT,
    DEFAULT_TIMEOUT,
    TriggerManager,
)


class StubTrigger(AbstractTrigger):
    """Concrete trigger for testing that returns a preconfigured value."""

    def __init__(self, result: bool, name: str = "stub"):
        self._result = result
        self._name = name

    def evaluate(self) -> bool:
        return self._result

    def describe(self) -> str:
        return f"stub trigger '{self._name}' (result={self._result})"

    def set_result(self, result: bool):
        self._result = result


def _make_config(**overrides):
    """Build a minimal valid trigger config dict with overrides."""
    config = {
        "mode": "all_of",
        "timeout": 10,
        "interval": 1,
        "on_timeout": "skip",
        "conditions": [
            {"type": "command", "cmd": "true"},
        ],
    }
    config.update(overrides)
    return config


class TestTriggerManager(unittest.TestCase):

    # ------------------------------------------------------------------
    # wait_for_triggers() — mode tests
    # ------------------------------------------------------------------

    @patch.object(TriggerManager, "_build_trigger")
    def test_all_of_all_pass(self, mock_build):
        """mode=all_of, all triggers pass -> returns True."""
        t1 = StubTrigger(True, "t1")
        t2 = StubTrigger(True, "t2")
        mock_build.side_effect = [t1, t2]

        config = _make_config(
            mode="all_of",
            conditions=[
                {"type": "command", "cmd": "a"},
                {"type": "command", "cmd": "b"},
            ],
        )
        manager = TriggerManager(config)
        self.assertTrue(manager.wait_for_triggers())

    @patch("krkn.scenario_plugins.triggers.trigger_manager.time")
    @patch.object(TriggerManager, "_build_trigger")
    def test_all_of_one_fails(self, mock_build, mock_time):
        """mode=all_of, one trigger stays False -> loops until timeout, returns False."""
        t1 = StubTrigger(True, "t1")
        t2 = StubTrigger(False, "t2")
        mock_build.side_effect = [t1, t2]

        # Simulate: first call returns start time, subsequent calls advance past deadline
        call_count = 0

        def advancing_monotonic():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return 0.0
            return 999.0  # past deadline

        mock_time.monotonic.side_effect = advancing_monotonic
        mock_time.sleep = lambda x: None

        config = _make_config(
            mode="all_of",
            timeout=10,
            conditions=[
                {"type": "command", "cmd": "a"},
                {"type": "command", "cmd": "b"},
            ],
        )
        manager = TriggerManager(config)
        self.assertFalse(manager.wait_for_triggers())

    @patch.object(TriggerManager, "_build_trigger")
    def test_any_of_one_passes(self, mock_build):
        """mode=any_of, one trigger passes -> returns True immediately."""
        t1 = StubTrigger(False, "t1")
        t2 = StubTrigger(True, "t2")
        mock_build.side_effect = [t1, t2]

        config = _make_config(
            mode="any_of",
            conditions=[
                {"type": "command", "cmd": "a"},
                {"type": "command", "cmd": "b"},
            ],
        )
        manager = TriggerManager(config)
        self.assertTrue(manager.wait_for_triggers())

    # ------------------------------------------------------------------
    # wait_for_triggers() — timeout tests
    # ------------------------------------------------------------------

    @patch("krkn.scenario_plugins.triggers.trigger_manager.time")
    @patch.object(TriggerManager, "_build_trigger")
    def test_timeout_returns_false(self, mock_build, mock_time):
        """Triggers never pass, timeout expires -> returns False."""
        t1 = StubTrigger(False, "t1")
        mock_build.side_effect = [t1]

        call_count = 0

        def advancing_monotonic():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return 0.0
            return 999.0

        mock_time.monotonic.side_effect = advancing_monotonic
        mock_time.sleep = lambda x: None

        config = _make_config(
            timeout=10,
            conditions=[{"type": "command", "cmd": "a"}],
        )
        manager = TriggerManager(config)
        self.assertFalse(manager.wait_for_triggers())

    # ------------------------------------------------------------------
    # Default values
    # ------------------------------------------------------------------

    @patch.object(TriggerManager, "_build_trigger")
    def test_default_timeout(self, mock_build):
        """No timeout in config -> defaults to 300."""
        mock_build.return_value = StubTrigger(True)
        config = {
            "conditions": [{"type": "command", "cmd": "true"}],
        }
        manager = TriggerManager(config)
        self.assertEqual(manager._timeout, DEFAULT_TIMEOUT)
        self.assertEqual(manager._timeout, 300)

    @patch.object(TriggerManager, "_build_trigger")
    def test_default_interval(self, mock_build):
        """No interval in config -> defaults to 5."""
        mock_build.return_value = StubTrigger(True)
        config = {
            "conditions": [{"type": "command", "cmd": "true"}],
        }
        manager = TriggerManager(config)
        self.assertEqual(manager._interval, DEFAULT_INTERVAL)
        self.assertEqual(manager._interval, 5)

    @patch.object(TriggerManager, "_build_trigger")
    def test_default_mode(self, mock_build):
        """No mode in config -> defaults to all_of."""
        mock_build.return_value = StubTrigger(True)
        config = {
            "conditions": [{"type": "command", "cmd": "true"}],
        }
        manager = TriggerManager(config)
        self.assertEqual(manager._mode, DEFAULT_MODE)
        self.assertEqual(manager._mode, "all_of")

    @patch.object(TriggerManager, "_build_trigger")
    def test_default_on_timeout(self, mock_build):
        """No on_timeout in config -> defaults to skip."""
        mock_build.return_value = StubTrigger(True)
        config = {
            "conditions": [{"type": "command", "cmd": "true"}],
        }
        manager = TriggerManager(config)
        self.assertEqual(manager._on_timeout, DEFAULT_ON_TIMEOUT)
        self.assertEqual(manager._on_timeout, "skip")

    # ------------------------------------------------------------------
    # Validation tests
    # ------------------------------------------------------------------

    def test_invalid_mode_raises(self):
        """mode='invalid' -> raises ValueError."""
        config = _make_config(mode="invalid")
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("invalid", str(ctx.exception))

    def test_missing_conditions_raises(self):
        """No 'conditions' key -> raises ValueError."""
        config = {"mode": "all_of", "timeout": 10}
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("conditions", str(ctx.exception))

    def test_empty_conditions_raises(self):
        """conditions=[] -> raises ValueError."""
        config = _make_config(conditions=[])
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("conditions", str(ctx.exception))

    def test_conditions_not_a_list_raises(self):
        """conditions='some string' -> raises ValueError."""
        config = _make_config(conditions="kubectl check something")
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("list", str(ctx.exception))

    def test_on_timeout_property(self):
        """on_timeout property returns validated value."""
        mock_build = patch.object(TriggerManager, "_build_trigger").start()
        mock_build.return_value = StubTrigger(True)
        config = _make_config(on_timeout="fail")
        manager = TriggerManager(config)
        self.assertEqual(manager.on_timeout, "fail")
        patch.stopall()

    def test_unknown_trigger_type_raises(self):
        """type='kafka' -> raises ValueError."""
        config = _make_config(
            conditions=[{"type": "kafka", "topic": "events"}],
        )
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("kafka", str(ctx.exception))

    def test_negative_timeout_raises(self):
        """timeout=-1 -> raises ValueError."""
        config = _make_config(timeout=-1)
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("timeout", str(ctx.exception))

    def test_zero_timeout_raises(self):
        """timeout=0 -> raises ValueError."""
        config = _make_config(timeout=0)
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("timeout", str(ctx.exception))

    def test_negative_interval_raises(self):
        """interval=-1 -> raises ValueError."""
        config = _make_config(interval=-1)
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("interval", str(ctx.exception))

    def test_zero_interval_raises(self):
        """interval=0 -> raises ValueError."""
        config = _make_config(interval=0)
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("interval", str(ctx.exception))

    def test_string_timeout_raises(self):
        """timeout='abc' -> raises ValueError."""
        config = _make_config(timeout="abc")
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("numeric", str(ctx.exception))

    def test_string_interval_raises(self):
        """interval='xyz' -> raises ValueError."""
        config = _make_config(interval="xyz")
        with self.assertRaises(ValueError) as ctx:
            TriggerManager(config)
        self.assertIn("numeric", str(ctx.exception))

    # ------------------------------------------------------------------
    # get_status() tests
    # ------------------------------------------------------------------

    @patch.object(TriggerManager, "_build_trigger")
    def test_get_status(self, mock_build):
        """get_status returns dict with trigger states."""
        t1 = StubTrigger(True, "t1")
        t2 = StubTrigger(False, "t2")
        mock_build.side_effect = [t1, t2]

        config = _make_config(
            mode="any_of",
            timeout=60,
            interval=2,
            on_timeout="fail",
            conditions=[
                {"type": "command", "cmd": "a"},
                {"type": "command", "cmd": "b"},
            ],
        )
        manager = TriggerManager(config)

        status = manager.get_status()
        self.assertEqual(status["mode"], "any_of")
        self.assertEqual(status["timeout"], 60)
        self.assertEqual(status["interval"], 2)
        self.assertEqual(status["on_timeout"], "fail")
        self.assertEqual(len(status["triggers"]), 2)

        # Before any evaluation, states should be None
        for trigger_info in status["triggers"]:
            self.assertIn("description", trigger_info)
            self.assertIn("satisfied", trigger_info)
            self.assertIsNone(trigger_info["satisfied"])

    # ------------------------------------------------------------------
    # describe() tests
    # ------------------------------------------------------------------

    @patch.object(TriggerManager, "_build_trigger")
    def test_describe(self, mock_build):
        """describe returns human-readable summary."""
        t1 = StubTrigger(True, "t1")
        t2 = StubTrigger(False, "t2")
        mock_build.side_effect = [t1, t2]

        config = _make_config(
            mode="all_of",
            timeout=30,
            interval=3,
            on_timeout="skip",
            conditions=[
                {"type": "command", "cmd": "a"},
                {"type": "command", "cmd": "b"},
            ],
        )
        manager = TriggerManager(config)
        desc = manager.describe()

        self.assertIsInstance(desc, str)
        self.assertIn("all_of", desc)
        self.assertIn("30", desc)
        self.assertIn("3", desc)
        self.assertIn("skip", desc)
        # Should include each trigger's description
        self.assertIn("t1", desc)
        self.assertIn("t2", desc)


if __name__ == "__main__":
    unittest.main()
