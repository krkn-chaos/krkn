#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
command -v go >/dev/null 2>&1 || { echo 'error: go is required' >&2; exit 127; }

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/krkn-go-transitive-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT
module_dir="$tmp_dir/module"
mock_bin="$tmp_dir/bin"
reports="$tmp_dir/reports"
mkdir -p "$module_dir" "$mock_bin"

cat > "$module_dir/go.mod" <<'EOF'
module example.com/transitive-exclusion-test

go 1.25.0

require (
	golang.org/x/crypto v0.57.0
	golang.org/x/net v0.59.0
)
EOF
cat > "$module_dir/main.go" <<'EOF'
package main

import (
	_ "golang.org/x/crypto/ssh"
	_ "golang.org/x/net/http2"
)

func main() {}
EOF

cat > "$mock_bin/govulncheck" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
count=0
[[ ! -f "$GOVULNCHECK_COUNT_FILE" ]] || count=$(<"$GOVULNCHECK_COUNT_FILE")
count=$((count + 1))
printf '%s\n' "$count" > "$GOVULNCHECK_COUNT_FILE"
printf '%s\n' '{"config":{"protocol_version":"v1.0.0"}}'
if ((count == 1)); then
  printf '%s\n' '{"finding":{"osv":"GO-TEST-XNET","fixed_version":"v0.62.0","trace":[{"module":"golang.org/x/net","version":"v0.59.0"}]}}'
  xcrypto_version=v0.57.0
else
  xcrypto_version=v0.58.0
fi
printf '%s\n' "{\"finding\":{\"osv\":\"GO-TEST-XCRYPTO\",\"fixed_version\":\"v0.59.0\",\"trace\":[{\"module\":\"golang.org/x/crypto\",\"version\":\"$xcrypto_version\"}]}}"
EOF
chmod 0755 "$mock_bin/govulncheck"

PATH="$mock_bin:$PATH" GOVULNCHECK_COUNT_FILE="$tmp_dir/scan-count" \
  "$repo_root/scripts/update-go-vulnerabilities.sh" \
  --exclude-module golang.org/x/crypto \
  --max-passes 3 \
  --report-dir "$reports" \
  "$module_dir"

xnet=$(go -C "$module_dir" list -m -f '{{.Version}}' golang.org/x/net)
xcrypto=$(go -C "$module_dir" list -m -f '{{.Version}}' golang.org/x/crypto)
[[ "$xnet" == v0.62.0 ]] || { echo "expected x/net v0.62.0, got $xnet" >&2; exit 1; }
[[ "$xcrypto" == v0.58.0 ]] || { echo "expected transitive x/crypto v0.58.0, got $xcrypto" >&2; exit 1; }
grep -q 'GO-TEST-XCRYPTO: golang.org/x/crypto@v0.58.0 has fix v0.59.0, excluded by compatibility policy' \
  "$reports/unresolved-final.txt"

echo "PASS: x/net fixed to $xnet; excluded x/crypto was allowed to update transitively to $xcrypto and its finding remains reported"
