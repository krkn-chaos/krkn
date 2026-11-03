#!/usr/bin/env bash
set -uo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/test-go-container-tools.sh [OPTIONS]

Clone, build, vulnerability-scan, try dependency updates, and rebuild the two
Go tools other than oc that ship in the Krkn image: virtctl and yq.
All source checkouts are temporary. Logs and binaries are kept under /tmp.

Options:
  --dry-run-only             Do not apply proposed dependency upgrades.
  --exclude-virtctl MODULE   Skip automatic updates for this module in virtctl (repeatable).
  --exclude-yq MODULE        Skip automatic updates for this module in yq (repeatable).
  -h, --help                 Show this help.

Requires: Go 1.26+, git, Python 3. govulncheck is installed into the temp
work directory automatically when it is not already on PATH.
USAGE
}

DRY_RUN_ONLY=0
VIRTCTL_EXCLUDES=()
YQ_EXCLUDES=()
while (($#)); do
  case "$1" in
    --dry-run-only)
      DRY_RUN_ONLY=1
      shift
      ;;
    --exclude-virtctl)
      if (($# < 2)) || [[ -z "$2" ]]; then
        echo "error: --exclude-virtctl requires a Go module path" >&2
        exit 2
      fi
      VIRTCTL_EXCLUDES+=("$2")
      shift 2
      ;;
    --exclude-yq)
      if (($# < 2)) || [[ -z "$2" ]]; then
        echo "error: --exclude-yq requires a Go module path" >&2
        exit 2
      fi
      YQ_EXCLUDES+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

KRKN_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for command_name in go git python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "error: required command not found: $command_name" >&2
    exit 127
  fi
done

go_version=$(go env GOVERSION 2>/dev/null || go version)
echo "Go toolchain: $go_version"

WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/krkn-go-tools.XXXXXX") || exit 1
SRC_DIR="$WORK_DIR/src"
BIN_DIR="$WORK_DIR/bin"
LOG_DIR="$WORK_DIR/logs"
BASELINE_DIR="$BIN_DIR/baseline"
UPDATED_DIR="$BIN_DIR/updated"
mkdir -p "$SRC_DIR" "$LOG_DIR" "$BASELINE_DIR" "$UPDATED_DIR"
trap 'rm -rf "$SRC_DIR"' EXIT

echo "Results directory: $WORK_DIR"

govulncheck_bin=$(command -v govulncheck || true)
if [[ -z "$govulncheck_bin" ]]; then
  mkdir -p "$WORK_DIR/tools"
  echo "Installing govulncheck into $WORK_DIR/tools ..."
  if ! GOBIN="$WORK_DIR/tools" go install golang.org/x/vuln/cmd/govulncheck@latest; then
    echo "error: could not install govulncheck; see Go/network errors above" >&2
    exit 1
  fi
  govulncheck_bin="$WORK_DIR/tools/govulncheck"
fi
export PATH="$(dirname "$govulncheck_bin"):$PATH"

run_logged() {
  local label=$1
  local logfile=$2
  shift 2
  echo
  echo "==> $label"
  if "$@" >"$logfile" 2>&1; then
    tail -n 25 "$logfile"
    return 0
  else
    local status=$?
    echo "FAILED (exit $status); final log lines: $logfile" >&2
    tail -n 60 "$logfile" >&2
    return "$status"
  fi
}

make_update_args() {
  local pattern=$1
  shift
  UPDATE_ARGS=("$KRKN_ROOT/scripts/update-go-vulnerabilities.sh" --pattern "$pattern")
  local module
  for module in "$@"; do
    UPDATE_ARGS+=(--exclude-module "$module")
  done
}

FAILURES=0
UPDATE_ISSUES=0

# virtctl: use the same repository and dependency edits as build-container-tool.sh.
VIRTCTL_SRC="$SRC_DIR/kubevirt"
if run_logged "Clone KubeVirt sources for virtctl" "$LOG_DIR/virtctl-clone.log" \
  git clone https://github.com/kubevirt/kubevirt.git "$VIRTCTL_SRC"; then
  git -C "$VIRTCTL_SRC" rev-parse HEAD | tee "$LOG_DIR/virtctl-source-commit.txt"
  if run_logged "Prepare and build baseline virtctl" "$LOG_DIR/virtctl-baseline-build.log" \
    bash -c 'set -euo pipefail
      cd "$1"
      go mod edit -go 1.26
      go mod edit -require golang.org/x/net@v0.60.0
      go mod edit -replace golang.org/x/net=golang.org/x/net@v0.60.0
      go mod edit -replace github.com/moby/spdystream=github.com/moby/spdystream@v0.5.1
      go mod edit -replace github.com/aws/aws-sdk-go-v2/aws/protocol/eventstream=github.com/aws/aws-sdk-go-v2/aws/protocol/eventstream@v1.7.8
      go mod edit -replace github.com/aws/aws-sdk-go-v2/service/s3=github.com/aws/aws-sdk-go-v2/service/s3@v1.97.3
      go work edit -go 1.26
      go work edit -replace golang.org/x/net=golang.org/x/net@v0.60.0
      go mod tidy
      go work use
      go work vendor
      go build -o "$2/virtctl" ./cmd/virtctl/' _ "$VIRTCTL_SRC" "$BASELINE_DIR"; then
    cp "$VIRTCTL_SRC/go.mod" "$LOG_DIR/virtctl-go.mod.baseline"
    cp "$VIRTCTL_SRC/go.sum" "$LOG_DIR/virtctl-go.sum.baseline"
    cp "$VIRTCTL_SRC/go.work" "$LOG_DIR/virtctl-go.work.baseline"
    rm -rf "$VIRTCTL_SRC/vendor"

    make_update_args ./cmd/virtctl "${VIRTCTL_EXCLUDES[@]}"
    if run_logged "Scan virtctl and show proposed updates" "$LOG_DIR/virtctl-dry-run.log" \
      bash "$KRKN_ROOT/scripts/update-go-vulnerabilities.sh" --dry-run "${UPDATE_ARGS[@]:1}" "$VIRTCTL_SRC"; then
      if ((DRY_RUN_ONLY)); then
        echo "Dry-run-only: virtctl dependency updates were not applied."
      else
        make_update_args ./cmd/virtctl "${VIRTCTL_EXCLUDES[@]}"
        if ! run_logged "Apply virtctl vulnerability updates in the temporary clone" "$LOG_DIR/virtctl-update.log" \
          bash "${UPDATE_ARGS[@]}" "$VIRTCTL_SRC"; then
          UPDATE_ISSUES=$((UPDATE_ISSUES + 1))
          echo "Update scan reported unresolved findings or an update conflict; attempting a build of the resulting checkout."
        fi
        if run_logged "Re-vendor and build updated virtctl" "$LOG_DIR/virtctl-updated-build.log" \
          bash -c 'set -euo pipefail
            cd "$1"
            go work vendor
            go build -o "$2/virtctl" ./cmd/virtctl/' _ "$VIRTCTL_SRC" "$UPDATED_DIR"; then
          :
        else
          FAILURES=$((FAILURES + 1))
        fi
        diff -u "$LOG_DIR/virtctl-go.mod.baseline" "$VIRTCTL_SRC/go.mod" >"$LOG_DIR/virtctl-go.mod-updates.diff" || true
        diff -u "$LOG_DIR/virtctl-go.work.baseline" "$VIRTCTL_SRC/go.work" >"$LOG_DIR/virtctl-go.work-updates.diff" || true
      fi
    else
      echo "virtctl dry run failed; inspect $LOG_DIR/virtctl-dry-run.log" >&2
      UPDATE_ISSUES=$((UPDATE_ISSUES + 1))
    fi
  else
    FAILURES=$((FAILURES + 1))
  fi
else
  FAILURES=$((FAILURES + 1))
fi

# yq: use the same pinned source tag and dependency edits as the image build.
YQ_SRC="$SRC_DIR/yq"
if run_logged "Clone yq v4.44.6 sources" "$LOG_DIR/yq-clone.log" \
  git clone --depth 1 --branch v4.44.6 https://github.com/mikefarah/yq.git "$YQ_SRC"; then
  git -C "$YQ_SRC" rev-parse HEAD | tee "$LOG_DIR/yq-source-commit.txt"
  if run_logged "Prepare and build baseline yq" "$LOG_DIR/yq-baseline-build.log" \
    bash -c 'set -euo pipefail
      cd "$1"
      go mod edit -require golang.org/x/net@v0.60.0
      go mod edit -require golang.org/x/text@v0.39.0
      go mod edit -replace golang.org/x/net=golang.org/x/net@v0.60.0
      go mod edit -replace golang.org/x/text=golang.org/x/text@v0.39.0
      go mod edit -replace github.com/moby/spdystream=github.com/moby/spdystream@v0.5.1
      go mod tidy
      go build -ldflags="-s -w" -o "$2/yq" .' _ "$YQ_SRC" "$BASELINE_DIR"; then
    cp "$YQ_SRC/go.mod" "$LOG_DIR/yq-go.mod.baseline"
    cp "$YQ_SRC/go.sum" "$LOG_DIR/yq-go.sum.baseline"

    make_update_args . "${YQ_EXCLUDES[@]}"
    if run_logged "Scan yq and show proposed updates" "$LOG_DIR/yq-dry-run.log" \
      bash "$KRKN_ROOT/scripts/update-go-vulnerabilities.sh" --dry-run "${UPDATE_ARGS[@]:1}" "$YQ_SRC"; then
      if ((DRY_RUN_ONLY)); then
        echo "Dry-run-only: yq dependency updates were not applied."
      else
        make_update_args . "${YQ_EXCLUDES[@]}"
        if ! run_logged "Apply yq vulnerability updates in the temporary clone" "$LOG_DIR/yq-update.log" \
          bash "${UPDATE_ARGS[@]}" "$YQ_SRC"; then
          UPDATE_ISSUES=$((UPDATE_ISSUES + 1))
          echo "Update scan reported unresolved findings or an update conflict; attempting a build of the resulting checkout."
        fi
        if run_logged "Build updated yq" "$LOG_DIR/yq-updated-build.log" \
          bash -c 'set -euo pipefail
            cd "$1"
            go build -ldflags="-s -w" -o "$2/yq" .' _ "$YQ_SRC" "$UPDATED_DIR"; then
          :
        else
          FAILURES=$((FAILURES + 1))
        fi
        diff -u "$LOG_DIR/yq-go.mod.baseline" "$YQ_SRC/go.mod" >"$LOG_DIR/yq-go.mod-updates.diff" || true
      fi
    else
      echo "yq dry run failed; inspect $LOG_DIR/yq-dry-run.log" >&2
      UPDATE_ISSUES=$((UPDATE_ISSUES + 1))
    fi
  else
    FAILURES=$((FAILURES + 1))
  fi
else
  FAILURES=$((FAILURES + 1))
fi

echo
echo "=== Results ==="
echo "Baseline binaries: $BASELINE_DIR"
if ((DRY_RUN_ONLY)); then
  echo "Dry-run logs: $LOG_DIR"
else
  echo "Updated candidate binaries (if builds passed): $UPDATED_DIR"
  echo "Update plans, findings, and go.mod diffs: $LOG_DIR"
fi
echo "Source revision logs: $LOG_DIR/*-source-commit.txt"
echo "Temporary source clones will be removed when this script exits."
if ((FAILURES)); then
  echo "Completed with $FAILURES build failure(s); inspect the corresponding logs." >&2
  exit 1
fi
if ((UPDATE_ISSUES)); then
  echo "Builds completed, but one or more update scans reported unresolved CVEs or update conflicts; inspect the logs." >&2
  exit 1
fi
echo "All requested build, scan, update, and rebuild steps completed. Review logs for excluded modules and remaining findings."
