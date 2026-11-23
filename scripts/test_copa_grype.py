"""Regression tests for Grype-to-Copa language-version selection."""

import io
import json
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


HELPERS = runpy.run_path(str(Path(__file__).with_name("copa-grype")))
version_parts = HELPERS["version_parts"]
best_fix = HELPERS["best_fix"]
canonical_python_name = HELPERS["canonical_python_name"]
read_python_names = HELPERS["read_python_names"]
build_manifest = HELPERS["main"]


class VersionOrderingTests(unittest.TestCase):
    """Check release candidate and post-release ordering used by patch selection."""

    def test_python_release_candidate_precedes_final_release(self):
        self.assertLess(version_parts("1.2.3.rc1"), version_parts("1.2.3"))

    def test_final_release_fixes_python_release_candidate(self):
        self.assertEqual(best_fix("1.2.3.rc1", ["1.2.3"], "patch"), "1.2.3")

    def test_post_release_follows_final_release(self):
        self.assertGreater(version_parts("1.2.3.post1"), version_parts("1.2.3"))


class PythonPackageNameTests(unittest.TestCase):
    """Check Grype names map back to the spelling used by pip freeze."""

    def test_pep503_name_normalization(self):
        self.assertEqual(canonical_python_name("zope.interface"), "zope-interface")
        self.assertEqual(canonical_python_name("My_Package"), "my-package")

    def test_freeze_map_preserves_installed_package_spelling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            freeze_path = Path(temp_dir) / "pip-freeze.txt"
            freeze_path.write_text("GitPython==3.1.52\nzope_interface==7.0\n", encoding="utf-8")
            names = read_python_names(freeze_path)

        self.assertEqual(names["gitpython"], "GitPython")
        self.assertEqual(names["zope-interface"], "zope_interface")

    def test_manifest_uses_pip_freeze_spelling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "grype.json"
            freeze_path = Path(temp_dir) / "pip-freeze.txt"
            report_path.write_text(json.dumps({
                "distro": {"name": "fedora", "version": "45"},
                "matches": [{
                    "artifact": {"type": "python-pkg", "name": "gitpython", "version": "3.1.52"},
                    "vulnerability": {
                        "id": "GHSA-example",
                        "fix": {"state": "fixed", "versions": ["3.2.1"]},
                    },
                }],
            }), encoding="utf-8")
            freeze_path.write_text("GitPython==3.1.52\n", encoding="utf-8")
            output = io.StringIO()
            with patch.object(sys, "argv", ["copa-grype", str(report_path), str(freeze_path)]), \
                    patch.dict(os.environ, {"KRKN_COPA_LIBRARY_PATCH_LEVEL": "minor"}), \
                    patch("sys.stdout", output):
                self.assertEqual(build_manifest(), 0)

        self.assertEqual(json.loads(output.getvalue())["langupdates"][0]["name"], "GitPython")


if __name__ == "__main__":
    unittest.main()
