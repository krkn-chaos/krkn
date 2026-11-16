"""Regression tests for Grype-to-Copa language-version selection."""

import runpy
import unittest
from pathlib import Path


HELPERS = runpy.run_path(str(Path(__file__).with_name("copa-grype")))
version_parts = HELPERS["version_parts"]
best_fix = HELPERS["best_fix"]


class VersionOrderingTests(unittest.TestCase):
    """Check release candidate and post-release ordering used by patch selection."""

    def test_python_release_candidate_precedes_final_release(self):
        self.assertLess(version_parts("1.2.3.rc1"), version_parts("1.2.3"))

    def test_final_release_fixes_python_release_candidate(self):
        self.assertEqual(best_fix("1.2.3.rc1", ["1.2.3"], "patch"), "1.2.3")

    def test_post_release_follows_final_release(self):
        self.assertGreater(version_parts("1.2.3.post1"), version_parts("1.2.3"))


if __name__ == "__main__":
    unittest.main()
