"""Regression tests for unique severity counts in Grype reports."""

import json
import tempfile
import unittest
from pathlib import Path

from summarize_grype_report import summarize_reports


class GrypeReportSummaryTests(unittest.TestCase):
    """Verify IDs are counted once across architectures while details are retained."""

    def test_deduplicates_ids_across_architectures_and_counts_severity(self):
        amd64 = {
            "matches": [
                self.match("CVE-2026-0001", "Critical", "openssl", "fixed"),
                self.match("CVE-2026-0002", "Medium", "urllib3", "fixed"),
            ]
        }
        arm64 = {
            "matches": [
                self.match("CVE-2026-0001", "Critical", "openssl", "fixed"),
                self.match("CVE-2026-0002", "High", "urllib3", "fixed"),
                self.match("GO-2026-1234", "Low", "example.org/mod", "not-fixed"),
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            amd64_path = root / "grype-candidate-amd64.json"
            arm64_path = root / "grype-candidate-arm64.json"
            amd64_path.write_text(json.dumps(amd64), encoding="utf-8")
            arm64_path.write_text(json.dumps(arm64), encoding="utf-8")

            summary = summarize_reports([str(amd64_path), str(arm64_path)])

        self.assertEqual(summary["architectures"], ["amd64", "arm64"])
        self.assertEqual(summary["total_matches"], 5)
        self.assertEqual(summary["unique_vulnerability_ids"], 3)
        self.assertEqual(summary["unique_fixable_vulnerability_ids"], 2)
        self.assertEqual(summary["counts_by_severity"]["Critical"], 1)
        self.assertEqual(summary["counts_by_severity"]["High"], 1)
        self.assertEqual(summary["counts_by_severity"]["Medium"], 0)
        self.assertEqual(summary["counts_by_severity"]["Low"], 1)
        self.assertEqual(len(summary["findings"]), 5)

    @staticmethod
    def match(vulnerability_id, severity, package, fix_state):
        return {
            "artifact": {"name": package, "version": "1.0.0"},
            "vulnerability": {
                "id": vulnerability_id,
                "severity": severity,
                "fix": {"state": fix_state, "versions": ["1.0.1"]},
            },
        }


if __name__ == "__main__":
    unittest.main()
