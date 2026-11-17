#!/usr/bin/env python3
"""Summarize unique Grype vulnerability IDs and retain package-level details."""

import json
import sys
from pathlib import Path

SEVERITIES = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")


def summarize_reports(report_paths):
    """Aggregate Grype JSON files, deduplicating vulnerability IDs across reports."""
    findings = {}
    total_matches = 0
    report_names = []
    architectures = set()

    for report_path in report_paths:
        path = Path(report_path)
        with path.open(encoding="utf-8") as report_file:
            report = json.load(report_file)
        report_names.append(path.name)
        architecture = next((arch for arch in ("amd64", "arm64") if arch in path.name), None)
        if architecture:
            architectures.add(architecture)

        matches = report.get("matches") or []
        total_matches += len(matches)
        for match in matches:
            vulnerability = match.get("vulnerability") or {}
            vulnerability_id = vulnerability.get("id")
            if not vulnerability_id:
                continue

            severity = vulnerability.get("severity") or "Unknown"
            if severity not in SEVERITIES:
                severity = "Unknown"
            artifact = match.get("artifact") or {}
            fix = vulnerability.get("fix") or {}
            fixed_versions = fix.get("versions") or []
            artifact_type = artifact.get("type") or "unknown"
            artifact_id = artifact.get("purl") or artifact.get("id")
            if not artifact_id:
                artifact_id = (
                    f"{artifact_type}:{artifact.get('name') or ''}@{artifact.get('version') or ''}"
                )
            if isinstance(fixed_versions, str):
                fixed_versions = [fixed_versions]

            finding = {
                "id": vulnerability_id,
                "severity": severity,
                "package": artifact.get("name"),
                "artifact_type": artifact_type,
                "artifact_id": artifact_id,
                "installed_version": artifact.get("version"),
                "fix_state": fix.get("state") or "unknown",
                "fixed_versions": fixed_versions,
                "architecture": architecture,
            }
            key = tuple(
                finding[field]
                for field in (
                    "id",
                    "severity",
                    "package",
                    "installed_version",
                    "artifact_type",
                    "artifact_id",
                    "fix_state",
                    "architecture",
                )
            ) + (tuple(fixed_versions),)
            findings[key] = finding

    records = sorted(
        findings.values(),
        key=lambda finding: (
            SEVERITIES.index(finding["severity"]),
            finding["id"],
            finding["package"] or "",
            finding["artifact_type"],
            finding["artifact_id"],
            finding["installed_version"] or "",
            finding["architecture"] or "",
        ),
    )
    severity_by_id = {}
    for finding in records:
        current = severity_by_id.get(finding["id"])
        if current is None or SEVERITIES.index(finding["severity"]) < SEVERITIES.index(current):
            severity_by_id[finding["id"]] = finding["severity"]
    ids_by_severity = {
        severity: sorted(
            vulnerability_id
            for vulnerability_id, finding_severity in severity_by_id.items()
            if finding_severity == severity
        )
        for severity in SEVERITIES
    }
    return {
        "reports": sorted(report_names),
        "architectures": sorted(architectures),
        "total_matches": total_matches,
        "unique_vulnerability_ids": len({finding["id"] for finding in records}),
        "unique_fixable_vulnerability_ids": len(
            {finding["id"] for finding in records if finding["fix_state"] == "fixed"}
        ),
        "counts_by_severity": {
            severity: len(ids_by_severity[severity]) for severity in SEVERITIES
        },
        "ids_by_severity": ids_by_severity,
        "findings": records,
    }


def main(argv=None):
    """Print a JSON summary for one or more Grype reports; return 2 on bad input."""
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(f"usage: {Path(sys.argv[0]).name} GRYPE_REPORT.json [GRYPE_REPORT.json ...]", file=sys.stderr)
        return 2

    try:
        summary = summarize_reports(argv)
    except (OSError, json.JSONDecodeError) as error:
        print(f"cannot summarize Grype reports: {error}", file=sys.stderr)
        return 1
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
