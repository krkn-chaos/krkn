#!/usr/bin/env bash
set -Eeuo pipefail

: "${RUNNER_TEMP:?RUNNER_TEMP must point to the runner temporary directory}"
: "${GITHUB_PATH:?GITHUB_PATH must point to the GitHub Actions path file}"

GRYPE_VERSION=${GRYPE_VERSION:-0.121.3}
BIN_DIR="$RUNNER_TEMP/security-tools/bin"
TMP_DIR=$(mktemp -d "$RUNNER_TEMP/security-tools.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$BIN_DIR"

case "$(uname -m)" in
  x86_64) arch=amd64; grype_sha=e9da18cc1429e786722e32161288103600efffd8e483c90761f90485bd1bec85 ;;
  aarch64|arm64) arch=arm64; grype_sha=b7815598d48da78bfd16f5b98ef28e1bb09c03d34fc8c3e350f99b6ccb3c7cba ;;
  *) echo "unsupported runner architecture: $(uname -m)" >&2; exit 2 ;;
esac

asset="grype_${GRYPE_VERSION}_linux_${arch}.tar.gz"
url="https://github.com/anchore/grype/releases/download/v${GRYPE_VERSION}/${asset}"
curl --fail --location --silent --show-error "$url" --output "$TMP_DIR/$asset"
echo "$grype_sha  $TMP_DIR/$asset" | sha256sum --check --status || {
  echo "Grype $GRYPE_VERSION checksum verification failed for linux/$arch" >&2
  exit 1
}
tar -xzf "$TMP_DIR/$asset" -C "$TMP_DIR" grype
install -m 0755 "$TMP_DIR/grype" "$BIN_DIR/grype"
echo "$BIN_DIR" >> "$GITHUB_PATH"
"$BIN_DIR/grype" version
