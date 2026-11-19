#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 scan|fix REQUIREMENTS_FILE REPORT_JSON" >&2
}

if [[ $# -ne 3 ]]; then usage; exit 2; fi
mode=$1
requirements=$2
report=$3
service=${PIP_AUDIT_SERVICE:-osv}

[[ -s "$requirements" ]] || { echo "error: requirements file is missing or empty: $requirements" >&2; exit 1; }
command -v pip-audit >/dev/null 2>&1 || { echo 'error: pip-audit is required' >&2; exit 127; }
command -v jq >/dev/null 2>&1 || { echo 'error: jq is required' >&2; exit 127; }
mkdir -p "$(dirname "$report")"

args=(--vulnerability-service "$service" --strict --format=json --output "$report")
case "$mode" in
  scan)
    # Freeze files are complete, exact-version snapshots from the built image.
    args+=(--no-deps --disable-pip)
    ;;
  fix)
    # Resolve the source requirements and let pip-audit update fixable direct or transitive deps.
    args+=(--fix)
    ;;
  *) echo "error: unsupported mode '$mode'" >&2; usage; exit 2 ;;
esac

set +e
pip-audit "${args[@]}" --requirement "$requirements"
rc=$?
set -e

if ((rc > 1)); then
  echo "error: pip-audit failed with exit code $rc" >&2
  exit "$rc"
fi
if ! jq -e '
  type == "object" and
  (.dependencies | type == "array") and
  all(.dependencies[]; (.name | type == "string") and (.version | type == "string") and (.vulns | type == "array"))
' "$report" >/dev/null; then
  echo "error: pip-audit did not produce a complete JSON report: $report" >&2
  exit 1
fi

findings=$(jq '[.dependencies[]?.vulns[]?.id] | unique | length' "$report")
if ((rc == 1 && findings == 0)); then
  echo 'error: pip-audit returned findings status without a valid vulnerability finding' >&2
  exit 1
fi
if [[ "$mode" == fix ]]; then
  fixed_packages=$(jq '[.fixes[]?.name] | unique | length' "$report")
  echo "pip-audit found $findings vulnerability IDs and updated $fixed_packages packages"
elif ((findings > 0)); then
  echo "pip-audit reported $findings unique vulnerability IDs; residual findings are informational"
fi
