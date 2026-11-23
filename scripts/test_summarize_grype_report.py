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

    def test_preserves_same_name_version_for_different_artifact_types(self):
        report = {
            "matches": [
                self.match(
                    "CVE-2026-0003",
                    "High",
                    "openssl",
                    "fixed",
                    artifact_type="rpm",
                    purl="pkg:rpm/fedora/openssl@1.0.0",
                ),
                self.match(
                    "CVE-2026-0003",
                    "High",
                    "openssl",
                    "fixed",
                    artifact_type="python",
                    purl="pkg:pypi/openssl@1.0.0",
                ),
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "grype-report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")

            summary = summarize_reports([str(report_path)])

        self.assertEqual(summary["total_matches"], 2)
        self.assertEqual(summary["unique_vulnerability_ids"], 1)
        self.assertEqual(summary["unique_fixable_vulnerability_ids"], 1)
        self.assertEqual(len(summary["findings"]), 2)
        self.assertEqual(
            {finding["artifact_type"] for finding in summary["findings"]},
            {"rpm", "python"},
        )
        self.assertEqual(
            {finding["artifact_id"] for finding in summary["findings"]},
            {"pkg:rpm/fedora/openssl@1.0.0", "pkg:pypi/openssl@1.0.0"},
        )

    @staticmethod
    def match(vulnerability_id, severity, package, fix_state, artifact_type=None, purl=None):
        artifact = {"name": package, "version": "1.0.0"}
        if artifact_type:
            artifact["type"] = artifact_type
        if purl:
            artifact["purl"] = purl
        return {
            "artifact": artifact,
            "vulnerability": {
                "id": vulnerability_id,
                "severity": severity,
                "fix": {"state": fix_state, "versions": ["1.0.1"]},
            },
        }


if __name__ == "__main__":
    unittest.main()
