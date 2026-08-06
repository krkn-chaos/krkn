import os
import stat
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from krkn.utils.wait_until import wait_until_condition, _load_python_condition


class TestWaitUntilConditionPython(unittest.TestCase):

    def test_condition_met_immediately(self):
        mock_fn = MagicMock(return_value=True)
        with patch(
            "krkn.utils.wait_until._load_python_condition", return_value=mock_fn
        ):
            result = wait_until_condition(
                {"type": "python", "target": "mod.fn", "max_wait_time": 10, "poll_interval": 1},
                "/fake/kubeconfig",
                "/fake/scenario.yaml",
            )
        self.assertTrue(result)
        mock_fn.assert_called_once_with("/fake/kubeconfig", "/fake/scenario.yaml")

    def test_condition_met_after_retries(self):
        mock_fn = MagicMock(side_effect=[False, False, True])
        with patch(
            "krkn.utils.wait_until._load_python_condition", return_value=mock_fn
        ), patch("krkn.utils.wait_until.time.sleep"):
            result = wait_until_condition(
                {"type": "python", "target": "mod.fn", "max_wait_time": 30, "poll_interval": 1},
                "/fake/kubeconfig",
                "/fake/scenario.yaml",
            )
        self.assertTrue(result)
        self.assertEqual(mock_fn.call_count, 3)

    def test_timeout_returns_false(self):
        mock_fn = MagicMock(return_value=False)
        with patch(
            "krkn.utils.wait_until._load_python_condition", return_value=mock_fn
        ), patch("krkn.utils.wait_until.time.sleep"), patch(
            "krkn.utils.wait_until.time.time",
            side_effect=[0, 0, 5, 5, 11, 11],
        ):
            result = wait_until_condition(
                {"type": "python", "target": "mod.fn", "max_wait_time": 10, "poll_interval": 5},
                "/fake/kubeconfig",
                "/fake/scenario.yaml",
            )
        self.assertFalse(result)

    def test_exception_in_condition_does_not_crash(self):
        mock_fn = MagicMock(side_effect=[RuntimeError("boom"), True])
        with patch(
            "krkn.utils.wait_until._load_python_condition", return_value=mock_fn
        ), patch("krkn.utils.wait_until.time.sleep"):
            result = wait_until_condition(
                {"type": "python", "target": "mod.fn", "max_wait_time": 30, "poll_interval": 1},
                "/fake/kubeconfig",
                "/fake/scenario.yaml",
            )
        self.assertTrue(result)
        self.assertEqual(mock_fn.call_count, 2)

    def test_invalid_target_returns_false(self):
        result = wait_until_condition(
            {"type": "python", "target": "nonexistent_module.fn", "max_wait_time": 5, "poll_interval": 1},
            "/fake/kubeconfig",
            "/fake/scenario.yaml",
        )
        self.assertFalse(result)

    def test_missing_required_fields(self):
        result = wait_until_condition(
            {"type": "python"},
            "/fake/kubeconfig",
            "/fake/scenario.yaml",
        )
        self.assertFalse(result)

    def test_unknown_type_returns_false(self):
        result = wait_until_condition(
            {"type": "unknown", "target": "something", "max_wait_time": 5},
            "/fake/kubeconfig",
            "/fake/scenario.yaml",
        )
        self.assertFalse(result)

    def test_non_dict_config_returns_false(self):
        result = wait_until_condition(
            "not_a_dict",
            "/fake/kubeconfig",
            "/fake/scenario.yaml",
        )
        self.assertFalse(result)

    def test_string_max_wait_time_coerced(self):
        mock_fn = MagicMock(return_value=True)
        with patch(
            "krkn.utils.wait_until._load_python_condition", return_value=mock_fn
        ):
            result = wait_until_condition(
                {"type": "python", "target": "mod.fn", "max_wait_time": "10", "poll_interval": "1"},
                "/fake/kubeconfig",
                "/fake/scenario.yaml",
            )
        self.assertTrue(result)

    def test_non_numeric_max_wait_time_returns_false(self):
        result = wait_until_condition(
            {"type": "python", "target": "mod.fn", "max_wait_time": "abc"},
            "/fake/kubeconfig",
            "/fake/scenario.yaml",
        )
        self.assertFalse(result)

    def test_negative_max_wait_time_returns_false(self):
        result = wait_until_condition(
            {"type": "python", "target": "mod.fn", "max_wait_time": -5},
            "/fake/kubeconfig",
            "/fake/scenario.yaml",
        )
        self.assertFalse(result)

    def test_python_condition_timeout_per_poll(self):
        import threading
        event = threading.Event()

        def blocking_fn(kubeconfig, scenario):
            event.wait(timeout=30)
            return True

        with patch(
            "krkn.utils.wait_until._load_python_condition", return_value=blocking_fn
        ):
            result = wait_until_condition(
                {"type": "python", "target": "mod.fn", "max_wait_time": 2, "poll_interval": 0.5},
                "/fake/kubeconfig",
                "/fake/scenario.yaml",
            )
        self.assertFalse(result)
        event.set()


class TestWaitUntilConditionScript(unittest.TestCase):

    def test_script_success(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write("#!/bin/bash\nexit 0\n")
            script_path = f.name
        os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IEXEC)

        try:
            result = wait_until_condition(
                {"type": "script", "target": script_path, "max_wait_time": 10, "poll_interval": 1},
                "/fake/kubeconfig",
                "/fake/scenario.yaml",
            )
            self.assertTrue(result)
        finally:
            os.unlink(script_path)

    def test_script_fails_then_succeeds(self):
        mock_results = [MagicMock(returncode=1), MagicMock(returncode=0)]
        with patch(
            "krkn.utils.wait_until.subprocess.run", side_effect=mock_results
        ), patch("krkn.utils.wait_until.time.sleep"):
            result = wait_until_condition(
                {"type": "script", "target": "/fake/script.sh", "max_wait_time": 30, "poll_interval": 1},
                "/fake/kubeconfig",
                "/fake/scenario.yaml",
            )
        self.assertTrue(result)

    def test_script_failure_logs_output(self):
        mock_result = MagicMock(returncode=1, stdout="some output", stderr="some error")
        mock_success = MagicMock(returncode=0, stdout="", stderr="")
        with patch(
            "krkn.utils.wait_until.subprocess.run",
            side_effect=[mock_result, mock_success],
        ), patch("krkn.utils.wait_until.time.sleep"), patch(
            "logging.debug"
        ) as mock_debug:
            result = wait_until_condition(
                {"type": "script", "target": "/fake/script.sh", "max_wait_time": 30, "poll_interval": 1},
                "/fake/kubeconfig",
                "/fake/scenario.yaml",
            )
        self.assertTrue(result)
        debug_messages = [str(call) for call in mock_debug.call_args_list]
        self.assertTrue(any("stderr" in m for m in debug_messages))
        self.assertTrue(any("stdout" in m for m in debug_messages))

    def test_script_timeout(self):
        mock_result = MagicMock(returncode=1)
        with patch(
            "krkn.utils.wait_until.subprocess.run", return_value=mock_result
        ), patch("krkn.utils.wait_until.time.sleep"), patch(
            "krkn.utils.wait_until.time.time",
            side_effect=[0, 0, 5, 5, 11, 11],
        ):
            result = wait_until_condition(
                {"type": "script", "target": "/fake/script.sh", "max_wait_time": 10, "poll_interval": 5},
                "/fake/kubeconfig",
                "/fake/scenario.yaml",
            )
        self.assertFalse(result)


class TestLoadPythonCondition(unittest.TestCase):

    def test_invalid_format_no_dot(self):
        result = _load_python_condition("nofunctionpath")
        self.assertIsNone(result)

    def test_nonexistent_module(self):
        result = _load_python_condition("nonexistent_xyz.check")
        self.assertIsNone(result)

    def test_valid_builtin(self):
        fn = _load_python_condition("os.path.exists")
        self.assertIsNotNone(fn)
        self.assertTrue(callable(fn))

    def test_non_callable_attribute(self):
        result = _load_python_condition("os.sep")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
