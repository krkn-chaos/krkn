#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: update-go-vulnerabilities.sh [OPTIONS] MODULE_DIR

Use govulncheck module findings to propose fixed Go module versions, apply them
with go get, tidy the module, and rescan. Vulnerabilities without an applicable
update are reported but do not fail the command; scanner and module-loading
errors do fail it.

Options:
  --exclude-module MOD    Do not update this module; can be repeated
  --max-passes N          Maximum update passes (default: 5)
  --report-dir DIR        Save govulncheck JSON streams and update evidence
  -h, --help              Show this help

Requires go, govulncheck, python3. Runs in govulncheck module scan mode.
EOF
}

MAX_PASSES=5
REPORT_DIR=''
EXCLUDED_MODULES=()
MODULE_DIR=''

while (($#)); do
  case "$1" in
    --exclude-module)
      (($# >= 2)) && [[ -n "$2" ]] || { echo 'error: --exclude-module requires a value' >&2; exit 2; }
      EXCLUDED_MODULES+=("$2"); shift 2 ;;
    --max-passes)
      (($# >= 2)) || { echo 'error: --max-passes requires a value' >&2; exit 2; }
      MAX_PASSES=$2; shift 2 ;;
    --report-dir)
      (($# >= 2)) || { echo 'error: --report-dir requires a value' >&2; exit 2; }
      REPORT_DIR=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --*) echo "error: unknown option: $1" >&2; usage >&2; exit 2 ;;
    *)
      [[ -z "$MODULE_DIR" ]] || { echo 'error: only one MODULE_DIR is supported' >&2; exit 2; }
      MODULE_DIR=$1; shift ;;
  esac
done

[[ -n "$MODULE_DIR" ]] || { usage >&2; exit 2; }
[[ "$MAX_PASSES" =~ ^[1-9][0-9]*$ ]] || { echo 'error: --max-passes must be a positive integer' >&2; exit 2; }

for command_name in go govulncheck python3; do
  command -v "$command_name" >/dev/null 2>&1 || { echo "error: required command not found: $command_name" >&2; exit 127; }
done

MODULE_DIR=$(cd "$MODULE_DIR" && pwd)
[[ -f "$MODULE_DIR/go.mod" ]] || { echo "error: no go.mod found at $MODULE_DIR" >&2; exit 2; }
if [[ -z "$REPORT_DIR" ]]; then
  REPORT_DIR="$MODULE_DIR/govulncheck-reports"
fi
mkdir -p "$REPORT_DIR"

printf 'Go toolchain: '; go version
printf 'Scanning module: %s\nScan level: module\n' "$MODULE_DIR"
if ((${#EXCLUDED_MODULES[@]})); then
  printf 'Excluded modules from automatic updates: %s\n' "${EXCLUDED_MODULES[*]}"
fi

parse_report() {
  local report=$1 updates_file=$2 unresolved_file=$3
  local python_args=("$report" "$updates_file" "$unresolved_file")
  local excluded
  for excluded in "${EXCLUDED_MODULES[@]-}"; do
    [[ -z "$excluded" ]] || python_args+=("$excluded")
  done
  python3 - "${python_args[@]}" <<'PY'
import json
import re
import sys

report_path, updates_path, unresolved_path, *excluded_args = sys.argv[1:]
excluded = set(excluded_args)
raw = open(report_path, encoding="utf-8").read()
decoder = json.JSONDecoder()
messages = []
offset = 0
while offset < len(raw):
    while offset < len(raw) and raw[offset].isspace():
        offset += 1
    if offset == len(raw):
        break
    try:
        item, offset = decoder.raw_decode(raw, offset)
    except json.JSONDecodeError as error:
        line = raw.count("\n", 0, error.pos) + 1
        raise SystemExit(f"invalid govulncheck JSON at line {line}: {error.msg}")
    if isinstance(item, list):
        messages.extend(item)
    elif isinstance(item, dict):
        messages.append(item)
    else:
        raise SystemExit("govulncheck JSON stream contains a non-object value")

if not any(isinstance(message, dict) and message.get("config") for message in messages):
    raise SystemExit("govulncheck returned no configuration message; scan output is incomplete")

version_re = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")

def version_key(value):
    match = version_re.fullmatch(value)
    if not match:
        raise ValueError(f"unsupported Go module version: {value}")
    major, minor, patch, pre = match.groups()
    identifiers = pre.split(".") if pre else []
    return (int(major), int(minor), int(patch), identifiers)

def compare(left, right):
    l, r = version_key(left), version_key(right)
    if l[:3] != r[:3]:
        return (l[:3] > r[:3]) - (l[:3] < r[:3])
    if not l[3] or not r[3]:
        return (bool(l[3]) < bool(r[3])) - (bool(l[3]) > bool(r[3]))
    for a, b in zip(l[3], r[3]):
        if a == b:
            continue
        an, bn = a.isdigit(), b.isdigit()
        if an and bn:
            return (int(a) > int(b)) - (int(a) < int(b))
        if an != bn:
            return -1 if an else 1
        return (a > b) - (a < b)
    return (len(l[3]) > len(r[3])) - (len(l[3]) < len(r[3]))

updates = {}
update_ids = {}
unresolved = set()
excluded_findings = set()
finding_count = 0
for message in messages:
    finding = message.get("finding") if isinstance(message, dict) else None
    if not finding:
        continue
    finding_count += 1
    osv = finding.get("osv", "unknown vulnerability")
    trace = finding.get("trace") or []
    frame = next((f for f in trace if f.get("module") and f.get("module") != "stdlib"), None)
    module = frame.get("module", "") if frame else ""
    version = frame.get("version", "") if frame else ""
    fixed = finding.get("fixed_version", "")
    if not module or not version:
        unresolved.add(f"{osv}: Go standard library/toolchain finding or module version unavailable; fixed version {fixed or 'not reported'}")
        continue
    if not fixed:
        unresolved.add(f"{osv}: {module}@{version} has no fixed version in vulnerability data")
        continue
    try:
        version_key(fixed)
    except ValueError as error:
        unresolved.add(f"{osv}: {module} fix cannot be applied automatically ({error})")
        continue
    if module in excluded:
        excluded_findings.add(f"{osv}: {module}@{version} has fix {fixed}, excluded by compatibility policy")
        continue
    current = updates.get(module)
    if current is None or compare(fixed, current) > 0:
        updates[module] = fixed
    update_ids.setdefault(module, set()).add(osv)

with open(updates_path, "w", encoding="utf-8") as out:
    for module, version in sorted(updates.items()):
        out.write(f"{module}\t{version}\n")
with open(unresolved_path, "w", encoding="utf-8") as out:
    for item in sorted(unresolved | excluded_findings):
        out.write(item + "\n")

print(f"govulncheck findings: {finding_count}")
print(f"modules with fixed versions: {len(updates)}")
for module, version in sorted(updates.items()):
    print(f"  {module}@{version} (findings: {', '.join(sorted(update_ids[module]))})")
if excluded_findings:
    print("fixed findings excluded by compatibility policy:")
    for item in sorted(excluded_findings):
        print(f"  {item}")
if unresolved:
    print("findings requiring separate action:")
    for item in sorted(unresolved):
        print(f"  {item}")
PY
}

backup_manifests() {
  local backup=$1
  mkdir -p "$backup"
  cp "$MODULE_DIR/go.mod" "$backup/go.mod"
  [[ ! -f "$MODULE_DIR/go.sum" ]] || cp "$MODULE_DIR/go.sum" "$backup/go.sum"
}

restore_manifests() {
  local backup=$1
  cp "$backup/go.mod" "$MODULE_DIR/go.mod"
  if [[ -f "$backup/go.sum" ]]; then cp "$backup/go.sum" "$MODULE_DIR/go.sum"; else rm -f "$MODULE_DIR/go.sum"; fi
}

applied_file="$REPORT_DIR/applied-updates.tsv"
: > "$applied_file"
final_scan_done=0
pass=1
while ((pass <= MAX_PASSES)); do
  report="$REPORT_DIR/govulncheck-pass-${pass}.jsonl"
  stderr="$REPORT_DIR/govulncheck-pass-${pass}.stderr"
  updates_file="$REPORT_DIR/updates-pass-${pass}.tsv"
  unresolved_file="$REPORT_DIR/unresolved-pass-${pass}.txt"
  echo "Scan/update pass $pass of $MAX_PASSES"
  scan_args=(-scan=module -json)
  if ! (cd "$MODULE_DIR" && govulncheck "${scan_args[@]}") >"$report" 2>"$stderr"; then
    cat "$stderr" >&2
    echo "error: govulncheck failed while scanning $MODULE_DIR" >&2
    exit 1
  fi
  cat "$stderr" >&2
  if ((pass == 1)); then cp "$report" "$REPORT_DIR/govulncheck-before.jsonl"; fi
  parse_report "$report" "$updates_file" "$unresolved_file"

  updates=()
  while IFS=$'\t' read -r module version; do
    [[ -n "$module" && -n "$version" ]] && updates+=("$module@$version")
  done < "$updates_file"
  if ((${#updates[@]} == 0)); then
    cp "$report" "$REPORT_DIR/govulncheck-final.jsonl"
    cp "$unresolved_file" "$REPORT_DIR/unresolved-final.txt"
    final_scan_done=1
    break
  fi

  pass_applied=()
  pass_backup="$REPORT_DIR/.pass-backup"
  rm -rf "$pass_backup"
  backup_manifests "$pass_backup"
  for update in "${updates[@]}"; do
    module=${update%@*}
    backup="$REPORT_DIR/.manifest-backup"
    rm -rf "$backup"
    backup_manifests "$backup"
    echo "go get $update"
    if (
      cd "$MODULE_DIR"
      if python3 - "$module" <<'PY'
import json, subprocess, sys
target = sys.argv[1]
data = json.loads(subprocess.check_output(["go", "mod", "edit", "-json"], text=True))
sys.exit(0 if any(r.get("Old", {}).get("Path") == target
                  and r.get("New", {}).get("Path") == target
                  and r.get("New", {}).get("Version")
                  for r in data.get("Replace", [])) else 1)
PY
      then
        echo "Removing self-replacement for $module so go get can select the fixed version"
        go mod edit "-dropreplace=$module"
      fi
      go get "$update"
    ); then
      pass_applied+=("$update")
    else
      restore_manifests "$backup"
      echo "warning: go get rejected $update; restored go.mod and go.sum" >&2
    fi
    rm -rf "$backup"
  done
  if ((${#pass_applied[@]})); then
    if (cd "$MODULE_DIR" && go mod tidy); then
      printf '%s\n' "${pass_applied[@]}" >> "$applied_file"
      rm -rf "$pass_backup"
    else
      restore_manifests "$pass_backup"
      rm -rf "$pass_backup"
      echo "warning: go mod tidy rejected this update pass; restored go.mod and go.sum" >&2
      break
    fi
  else
    rm -rf "$pass_backup"
  fi
  pass=$((pass + 1))
done

if ((final_scan_done == 0)); then
  report="$REPORT_DIR/govulncheck-final.jsonl"
  stderr="$REPORT_DIR/govulncheck-final.stderr"
  updates_file="$REPORT_DIR/updates-final.tsv"
  unresolved_file="$REPORT_DIR/unresolved-final.txt"
  echo "Final govulncheck scan after automatic update attempts"
  scan_args=(-scan=module -json)
  if ! (cd "$MODULE_DIR" && govulncheck "${scan_args[@]}") >"$report" 2>"$stderr"; then
    cat "$stderr" >&2
    echo "error: final govulncheck scan failed" >&2
    exit 1
  fi
  cat "$stderr" >&2
  parse_report "$report" "$updates_file" "$unresolved_file"
  if [[ -s "$updates_file" ]]; then
    while IFS=$'\t' read -r module version; do
      [[ -n "$module" && -n "$version" ]] || continue
      printf '%s: candidate fixed version %s remains after automatic update attempts\n' "$module" "$version" >> "$unresolved_file"
    done < "$updates_file"
  fi
  if [[ -s "$updates_file" ]]; then
    echo "warning: fixed module findings remain after the maximum update passes" >&2
  fi
fi

if [[ -s "$unresolved_file" ]]; then
  echo "Residual Go vulnerability findings (reported, not a build gate):" >&2
  sed 's/^/  /' "$unresolved_file" >&2
fi
sort -u "$applied_file" -o "$applied_file"
echo "Applied module updates: $(wc -l < "$applied_file" | tr -d ' ')"
echo "govulncheck evidence: $REPORT_DIR"
