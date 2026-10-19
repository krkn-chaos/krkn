#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: update-go-vulnerabilities.sh [OPTIONS] [MODULE_DIR]

Scan one Go module with govulncheck, update dependencies to the highest fixed
versions reported for each vulnerable module, tidy go.mod/go.sum, refresh vendor
when present, and scan again. The default mode applies updates.

Options:
  --dry-run              Report proposed go get updates without changing files.
  --pattern PATTERN      Go package pattern to scan (default: ./...).
  --tags TAGS            Comma-separated Go build tags (default: none).
  --exclude-module MOD   Do not update this module; can be repeated. Its fixed
                         findings remain reported and make the final scan fail.
  --max-passes N         Maximum scan/update cycles (default: 5).
  -h, --help             Show this help.

Requires: go, govulncheck, python3.
Run this against a disposable/clean checkout first. It modifies go.mod,
go.sum, and vendor/ when present. It handles one Go module root at a time.
EOF
}

DRY_RUN=0
PATTERN='./...'
BUILD_TAGS=''
MAX_PASSES=5
EXCLUDED_MODULES=()
MODULE_DIR='.'
POSITIONAL_SET=0

while (($#)); do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --pattern)
      if (($# < 2)); then
        echo "error: --pattern requires a value" >&2
        exit 2
      fi
      PATTERN=$2
      shift 2
      ;;
    --tags)
      if (($# < 2)); then
        echo "error: --tags requires a value" >&2
        exit 2
      fi
      BUILD_TAGS=$2
      shift 2
      ;;
    --max-passes)
      if (($# < 2)); then
        echo "error: --max-passes requires a value" >&2
        exit 2
      fi
      MAX_PASSES=$2
      shift 2
      ;;
    --exclude-module)
      if (($# < 2)) || [[ -z "$2" ]]; then
        echo "error: --exclude-module requires a module path" >&2
        exit 2
      fi
      EXCLUDED_MODULES+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if ((POSITIONAL_SET)); then
        echo "error: only one MODULE_DIR is supported per invocation" >&2
        usage >&2
        exit 2
      fi
      MODULE_DIR=$1
      POSITIONAL_SET=1
      shift
      ;;
  esac
done

if ! [[ "$MAX_PASSES" =~ ^[1-9][0-9]*$ ]]; then
  echo "error: --max-passes must be a positive integer" >&2
  exit 2
fi

for command_name in go govulncheck python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "error: required command not found: $command_name" >&2
    if [[ "$command_name" == govulncheck ]]; then
      echo "install it with: go install golang.org/x/vuln/cmd/govulncheck@latest" >&2
    fi
    exit 127
  fi
done

if ! MODULE_DIR=$(cd "$MODULE_DIR" 2>/dev/null && pwd); then
  echo "error: module directory does not exist" >&2
  exit 2
fi
if [[ ! -f "$MODULE_DIR/go.mod" ]]; then
  echo "error: no go.mod found at $MODULE_DIR (pass the module root, not a parent directory)" >&2
  exit 2
fi

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/go-vuln-remediation.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT

scan_and_plan() {
  local report_path=$1
  local stderr_path=$2
  local updates_path=$3
  local unresolved_path=$4

  local scan_args=(-json)
  if [[ -n "$BUILD_TAGS" ]]; then
    scan_args+=(-tags "$BUILD_TAGS")
  fi
  scan_args+=("$PATTERN")

  if ! (cd "$MODULE_DIR" && govulncheck "${scan_args[@]}") >"$report_path" 2>"$stderr_path"; then
    cat "$stderr_path" >&2
    echo "error: govulncheck failed while scanning $MODULE_DIR" >&2
    return 1
  fi

  local python_args=("$report_path" "$updates_path" "$unresolved_path")
  if ((${#EXCLUDED_MODULES[@]})); then
    python_args+=("${EXCLUDED_MODULES[@]}")
  fi
  python3 - "${python_args[@]}" <<'PY'
import json
import re
import sys

report_path, updates_path, unresolved_path, *excluded_modules = sys.argv[1:]
excluded_modules = set(excluded_modules)
messages = []
with open(report_path, encoding="utf-8") as report:
    raw_report = report.read()

decoder = json.JSONDecoder()
position = 0
while position < len(raw_report):
    while position < len(raw_report) and raw_report[position].isspace():
        position += 1
    if position == len(raw_report):
        break
    try:
        message, position = decoder.raw_decode(raw_report, position)
    except json.JSONDecodeError as error:
        line_number = raw_report.count("\n", 0, error.pos) + 1
        raise SystemExit(
            f"invalid govulncheck JSON at line {line_number}: {error.msg}"
        )
    if isinstance(message, list):
        if not all(isinstance(item, dict) for item in message):
            raise SystemExit("govulncheck JSON array contains a non-object entry")
        messages.extend(message)
    elif isinstance(message, dict):
        messages.append(message)
    else:
        raise SystemExit("govulncheck JSON stream contains a non-object entry")

if not any(message.get("config") for message in messages):
    raise SystemExit("govulncheck returned no JSON configuration; scan output is incomplete")

updates = {}
update_ids = {}
unresolved = set()
excluded = set()
finding_count = 0

version_re = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)

def version_parts(value):
    match = version_re.fullmatch(value)
    if not match:
        raise ValueError(f"unsupported Go module version: {value}")
    major, minor, patch, prerelease = match.groups()
    identifiers = prerelease.split(".") if prerelease else None
    return (int(major), int(minor), int(patch), identifiers)

def compare_versions(left, right):
    left_core, right_core = version_parts(left), version_parts(right)
    if left_core[:3] != right_core[:3]:
        return (left_core[:3] > right_core[:3]) - (left_core[:3] < right_core[:3])
    left_pre, right_pre = left_core[3], right_core[3]
    if left_pre is None or right_pre is None:
        if left_pre is None and right_pre is None:
            return 0
        return 1 if left_pre is None else -1
    for left_id, right_id in zip(left_pre, right_pre):
        if left_id == right_id:
            continue
        left_numeric, right_numeric = left_id.isdigit(), right_id.isdigit()
        if left_numeric and right_numeric:
            return (int(left_id) > int(right_id)) - (int(left_id) < int(right_id))
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return (left_id > right_id) - (left_id < right_id)
    return (len(left_pre) > len(right_pre)) - (len(left_pre) < len(right_pre))

for message in messages:
    finding = message.get("finding")
    if not finding:
        continue
    finding_count += 1
    osv_id = finding.get("osv", "unknown vulnerability")
    trace = finding.get("trace") or []
    frame = next((item for item in trace if item.get("module")), None)
    module = frame.get("module", "") if frame else ""
    fixed = finding.get("fixed_version", "")

    if module in ("stdlib", "toolchain") or fixed.startswith("go1."):
        unresolved.add(f"{osv_id}: Go standard library/toolchain fix {fixed or 'not reported'}; update the Go toolchain")
        continue
    if not module or not frame.get("version"):
        unresolved.add(f"{osv_id}: could not identify a versioned Go module in the finding trace")
        continue
    if not fixed:
        unresolved.add(f"{osv_id}: {module}@{frame['version']} has no fixed version in the vulnerability data")
        continue
    try:
        version_parts(fixed)
    except ValueError as error:
        unresolved.add(f"{osv_id}: {module} fix cannot be applied automatically ({error})")
        continue
    if module in excluded_modules:
        excluded.add(f"{osv_id}: {module}@{frame['version']} has fix {fixed}, excluded by --exclude-module")
        continue
    current = updates.get(module)
    if current is None or compare_versions(fixed, current) > 0:
        updates[module] = fixed
    update_ids.setdefault(module, set()).add(osv_id)

with open(updates_path, "w", encoding="utf-8") as output:
    for module, version in sorted(updates.items()):
        output.write(f"{module}\t{version}\n")
with open(unresolved_path, "w", encoding="utf-8") as output:
    for item in sorted(unresolved | excluded):
        output.write(item + "\n")

print(f"govulncheck findings: {finding_count}")
print(f"modules with fixed versions: {len(updates)}")
for module, version in sorted(updates.items()):
    ids = ", ".join(sorted(update_ids[module]))
    print(f"  {module}@{version} (findings: {ids})")
if excluded:
    print("fixed findings excluded by policy:")
    for item in sorted(excluded):
        print(f"  {item}")
if unresolved:
    print("findings requiring separate action:")
    for item in sorted(unresolved):
        print(f"  {item}")
PY
}

printf 'Go toolchain: '
go version
printf 'Scanning module: %s\n' "$MODULE_DIR"
printf 'Package pattern: %s\n' "$PATTERN"
if [[ -n "$BUILD_TAGS" ]]; then
  printf 'Build tags: %s\n' "$BUILD_TAGS"
fi
if ((${#EXCLUDED_MODULES[@]})); then
  printf 'Excluded modules from automatic updates: %s\n' "${EXCLUDED_MODULES[*]}"
fi

pass=1
while ((pass <= MAX_PASSES)); do
  report_path="$TMP_DIR/govulncheck-$pass.jsonl"
  stderr_path="$TMP_DIR/govulncheck-$pass.stderr"
  updates_path="$TMP_DIR/updates-$pass.tsv"
  unresolved_path="$TMP_DIR/unresolved-$pass.txt"

  printf '\nScan/update pass %d of %d\n' "$pass" "$MAX_PASSES"
  scan_and_plan "$report_path" "$stderr_path" "$updates_path" "$unresolved_path"

  updates=()
  while IFS=$'\t' read -r module version; do
    [[ -n "$module" && -n "$version" ]] && updates+=("$module@$version")
  done < "$updates_path"

  if ((${#updates[@]} == 0)); then
    if [[ -s "$unresolved_path" ]]; then
      echo "error: unresolved govulncheck findings remain; see the messages above" >&2
      exit 1
    fi
    echo "No reachable Go module vulnerabilities remain."
    exit 0
  fi

  if ((DRY_RUN)); then
    printf 'Dry run; would run these go get commands sequentially:\n'
    for update in "${updates[@]}"; do
      printf '  go get %q\n' "$update"
    done
    exit 0
  fi

  printf 'Applying fixed module versions sequentially:\n'
  (
    cd "$MODULE_DIR"
    for update in "${updates[@]}"; do
      printf '  go get %s\n' "$update"
      if ! go get "$update"; then
        echo "error: go get failed for $update" >&2
        exit 1
      fi
    done
    go mod tidy
    if [[ -d vendor ]]; then
      go mod vendor
    fi
  )

  pass=$((pass + 1))
done

echo "error: vulnerabilities still require updates after $MAX_PASSES scan/update passes" >&2
exit 1
