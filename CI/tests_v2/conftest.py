"""
Shared fixtures for pytest functional tests (CI/tests_v2).
Tests must be run from the repository root so run_kraken.py and config paths resolve.
"""

import html as html_lib
import logging
import os
import re
from pathlib import Path

import pytest

# Matches Krkn's log format "%(asctime)s [%(levelname)s] %(message)s" so each line can be
# rendered as a Timestamp/Level/Message row in the HTML report; non-matching lines (banner,
# tracebacks) fall back to a single Message cell.
_KRAKEN_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[,.]\d+)?)\s+\[(\w+)\]\s+(.*)$"
)
# Cap rows per run so a chatty scenario can't bloat the HTML report.
_KRAKEN_LOG_MAX_LINES = 1000


def pytest_addoption(parser):
    parser.addoption(
        "--keep-ns-on-fail",
        action="store_true",
        default=False,
        help="Don't delete test namespaces on failure (for debugging)",
    )
    parser.addoption(
        "--require-kind",
        action="store_true",
        default=False,
        help="Skip tests unless current context is a known dev cluster (kind, minikube)",
    )


def _kraken_log_html(outputs, evidence):
    """Render stashed Krkn stdout/stderr (and the evidence verdict) as an HTML block for the report."""
    parts = ["<div><strong>Krkn Execution Log</strong></div>"]
    for idx, out in enumerate(outputs, 1):
        combined = ((out.get("stdout") or "") + "\n" + (out.get("stderr") or "")).strip("\n")
        lines = combined.splitlines() if combined else []
        if len(outputs) > 1:
            parts.append(f"<div><em>Run {idx} (rc={out.get('returncode')})</em></div>")
        if len(lines) > _KRAKEN_LOG_MAX_LINES:
            parts.append(
                f"<div><em>(showing last {_KRAKEN_LOG_MAX_LINES} of {len(lines)} lines)</em></div>"
            )
            lines = lines[-_KRAKEN_LOG_MAX_LINES:]
        parts.append(
            '<table style="border-collapse:collapse;font-family:monospace;font-size:12px">'
            "<tr><th style='text-align:left;padding:2px 8px'>Timestamp</th>"
            "<th style='text-align:left;padding:2px 8px'>Level</th>"
            "<th style='text-align:left;padding:2px 8px'>Message</th></tr>"
        )
        for line in lines:
            m = _KRAKEN_LOG_LINE_RE.match(line)
            ts, lvl, msg = (m.group(1), m.group(2), m.group(3)) if m else ("", "", line)
            parts.append(
                "<tr>"
                f"<td style='padding:2px 8px;white-space:nowrap'>{html_lib.escape(ts)}</td>"
                f"<td style='padding:2px 8px'>{html_lib.escape(lvl)}</td>"
                f"<td style='padding:2px 8px'>{html_lib.escape(msg)}</td>"
                "</tr>"
            )
        parts.append("</table>")
    if evidence is not None:
        mark = "✓ Matched" if evidence["verified"] else "✗ No match for"
        parts.append(
            f"<div><strong>Execution Evidence:</strong> {mark} "
            f"<code>{html_lib.escape(evidence['pattern'])}</code></div>"
        )
    return "".join(parts)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    pytest_html = item.config.pluginmanager.getplugin("html")
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)

    if rep.when != "call":
        return

    from lib.utils import EXECUTION_EVIDENCE  # local import: lib is on path at runtime

    evidence = EXECUTION_EVIDENCE.get(item.nodeid)
    if evidence is not None:
        # user_properties survive pytest-xdist worker -> controller transport so the
        # terminal-summary hook (running on the controller) can build the table.
        rep.user_properties.append(
            ("kraken_evidence", "verified" if evidence["verified"] else "missing")
        )

    outputs = getattr(item, "_kraken_outputs", None)
    if pytest_html is not None and outputs:
        extras = getattr(rep, "extras", [])
        extras.append(pytest_html.extras.html(_kraken_log_html(outputs, evidence)))
        rep.extras = extras


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print and (in GitHub Actions) write the execution-evidence summary table."""
    reports = terminalreporter.stats.get("passed", []) + terminalreporter.stats.get("failed", [])
    rows = []
    for rep in reports:
        if getattr(rep, "when", None) != "call":
            continue
        evidence = None
        for name, value in getattr(rep, "user_properties", []):
            if name == "kraken_evidence":
                evidence = value
        if evidence == "verified":
            ev = "✓ Verified"
        elif evidence == "missing":
            ev = "✗ No evidence"
        else:
            ev = "—"
        result = "PASSED" if rep.passed else "FAILED"
        rows.append((rep.nodeid, result, ev))
    if not rows:
        return
    rows.sort()
    terminalreporter.write_sep("=", "Execution Evidence Summary")
    for nodeid, result, ev in rows:
        terminalreporter.write_line(f"{result:<6}  {ev:<14}  {nodeid}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a") as f:
                f.write("\n### Execution Evidence Summary\n\n")
                f.write("| Test | Result | Execution Evidence |\n")
                f.write("|------|--------|--------------------|\n")
                for nodeid, result, ev in rows:
                    f.write(f"| `{nodeid}` | {result} | {ev} |\n")
        except Exception as e:
            logging.getLogger(__name__).warning(
                "Could not write GITHUB_STEP_SUMMARY: %s", e
            )


def _repo_root() -> Path:
    """Repository root (directory containing run_kraken.py and CI/)."""
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def repo_root():
    return _repo_root()


@pytest.fixture(scope="session", autouse=True)
def _configure_logging():
    """Set log format with timestamps for test runs."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )


# Re-export fixtures from lib modules so pytest discovers them
from lib.deploy import deploy_workload, wait_for_pods_running  # noqa: E402, F401
from lib.kraken import build_config, run_kraken, run_kraken_background  # noqa: E402, F401
from lib.k8s import (  # noqa: E402, F401
    _kube_config_loaded,
    _log_cluster_context,
    k8s_apps,
    k8s_client,
    k8s_core,
    k8s_networking,
    kubectl,
)
from lib.namespace import _cleanup_stale_namespaces, make_namespace, test_namespace  # noqa: E402, F401
from lib.preflight import _preflight_checks  # noqa: E402, F401
