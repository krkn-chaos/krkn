#!/usr/bin/env python3
"""
Tests for krkn/utils/junit.py — validate_junit_options and write_junit_file.

Usage:
    python -m coverage run -a -m unittest tests/test_junit_utils.py -v
"""

import os
import shutil
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stub external dependencies so no krkn_lib install is needed
# ---------------------------------------------------------------------------

def _inject(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return sys.modules[name]


_inject("krkn_lib")
_inject("krkn_lib.utils")
_inject("krkn_lib.utils.functions",
        get_junit_test_case=MagicMock(return_value="<xml/>"),
        get_yaml_item_value=MagicMock())
_inject("krkn_lib.k8s", KrknKubernetes=MagicMock())
_inject("krkn_lib.ocp", KrknOpenshift=MagicMock())
_inject("krkn_lib.models.telemetry", ScenarioTelemetry=MagicMock(), ChaosRunTelemetry=MagicMock())
_inject("krkn_lib.telemetry.ocp", KrknTelemetryOpenshift=MagicMock())
_inject("krkn_lib.telemetry.k8s", KrknTelemetryKubernetes=MagicMock())
_inject("tzlocal")
_inject("tzlocal.unix", get_localzone=MagicMock(return_value="UTC"))

from krkn.utils.junit import validate_junit_options, write_junit_file  # noqa: E402


# ===========================================================================
# validate_junit_options
# ===========================================================================

class TestValidateJunitOptions(unittest.TestCase):

    def test_neither_set_returns_no_error_and_no_path(self):
        junit_error, path = validate_junit_options(None, None)
        self.assertFalse(junit_error)
        self.assertIsNone(path)

    def test_path_only_returns_error(self):
        junit_error, path = validate_junit_options(None, "/some/path")
        self.assertTrue(junit_error)
        self.assertIsNone(path)

    def test_testcase_only_no_path_returns_error_without_crash(self):
        # If junit_testcase_path is None, normpath(None) must not be called.
        junit_error, path = validate_junit_options("my test", None)
        self.assertTrue(junit_error)
        self.assertIsNone(path)

    def test_valid_dir_returns_no_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            junit_error, path = validate_junit_options("my test", tmpdir)
        self.assertFalse(junit_error)
        self.assertIsNotNone(path)

    def test_path_is_normalized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            unnormalized = tmpdir + "/."
            _, path = validate_junit_options("my test", unnormalized)
        self.assertEqual(path, os.path.normpath(unnormalized))

    def test_nonexistent_path_returns_error(self):
        junit_error, _ = validate_junit_options("my test", "/nonexistent/path/xyz")
        self.assertTrue(junit_error)

    def test_file_instead_of_dir_returns_error(self):
        with tempfile.NamedTemporaryFile() as tmp:
            junit_error, _ = validate_junit_options("my test", tmp.name)
        self.assertTrue(junit_error)

    def test_nonwritable_dir_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chmod(tmpdir, stat.S_IRUSR | stat.S_IXUSR)
            try:
                junit_error, _ = validate_junit_options("my test", tmpdir)
                self.assertTrue(junit_error)
            finally:
                os.chmod(tmpdir, stat.S_IRWXU)


# ===========================================================================
# write_junit_file
# ===========================================================================

class TestWriteJunitFile(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _get_written_file(self):
        files = [
            f for f in os.listdir(self.tmpdir)
            if f.startswith("junit_krkn_") and f.endswith(".xml")
        ]
        self.assertEqual(len(files), 1, f"Expected exactly one junit XML file, got: {files}")
        return os.path.join(self.tmpdir, files[0])

    @patch("krkn.utils.junit.get_junit_test_case", return_value="<xml>success</xml>")
    def test_writes_file_on_success(self, _mock):
        write_junit_file(
            junit_normalized_path=self.tmpdir,
            success=True,
            elapsed_seconds=10.5,
            test_case_description="chaos run",
            test_stdout="some output",
        )
        with open(self._get_written_file()) as f:
            self.assertEqual(f.read(), "<xml>success</xml>")

    @patch("krkn.utils.junit.get_junit_test_case", return_value="<xml>failure</xml>")
    def test_writes_file_on_failure(self, _mock):
        write_junit_file(
            junit_normalized_path=self.tmpdir,
            success=False,
            elapsed_seconds=5.0,
            test_case_description="chaos run",
            test_stdout="error output",
        )
        with open(self._get_written_file()) as f:
            self.assertEqual(f.read(), "<xml>failure</xml>")

    @patch("krkn.utils.junit.get_junit_test_case", return_value="<xml/>")
    def test_passes_correct_args_to_get_junit_test_case(self, mock_get):
        write_junit_file(
            junit_normalized_path=self.tmpdir,
            success=True,
            elapsed_seconds=42.9,
            test_case_description="my scenario",
            test_stdout="stdout here",
            test_version="v1.2.3",
        )
        mock_get.assert_called_once_with(
            success=True,
            time=42,
            test_suite_name="chaos-krkn",
            test_case_description="my scenario",
            test_stdout="stdout here",
            test_version="v1.2.3",
        )

    @patch("krkn.utils.junit.get_junit_test_case", return_value="<xml/>")
    def test_elapsed_seconds_truncated_to_int(self, mock_get):
        write_junit_file(
            junit_normalized_path=self.tmpdir,
            success=True,
            elapsed_seconds=99.99,
            test_case_description="t",
            test_stdout="",
        )
        self.assertEqual(mock_get.call_args[1]["time"], 99)

    @patch("krkn.utils.junit.get_junit_test_case", return_value="<xml/>")
    def test_file_name_matches_expected_pattern(self, _mock):
        write_junit_file(
            junit_normalized_path=self.tmpdir,
            success=True,
            elapsed_seconds=1.0,
            test_case_description="t",
            test_stdout="",
        )
        files = os.listdir(self.tmpdir)
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0], r"^junit_krkn_\d+\.xml$")

    @patch("krkn.utils.junit.get_junit_test_case", return_value="<xml/>")
    def test_version_defaults_to_none(self, mock_get):
        write_junit_file(
            junit_normalized_path=self.tmpdir,
            success=True,
            elapsed_seconds=1.0,
            test_case_description="t",
            test_stdout="",
        )
        self.assertIsNone(mock_get.call_args[1]["test_version"])


if __name__ == "__main__":
    unittest.main()
