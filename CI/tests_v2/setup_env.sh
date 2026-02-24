#!/usr/bin/env bash
# Setup environment for CI/tests_v2 pytest functional tests.
# Run from the repository root: ./CI/tests_v2/setup_env.sh
#
# - Creates a KinD cluster using the repo's kind-config.yml (if not already present).
# - Waits for the cluster and for local-path-provisioner pods (required by pod disruption test).
# - Does not install Python deps; use a venv and pip install -r requirements.txt and CI/tests_v2/requirements.txt yourself.

set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KIND_CONFIG="${KIND_CONFIG:-${REPO_ROOT}/CI/tests_v2/kind-config-dev.yml}"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-ci-krkn}"

echo "Repository root: $REPO_ROOT"
cd "$REPO_ROOT"

# Check required tools
command -v kind >/dev/null 2>&1 || { echo "Error: kind is not installed. Install from https://kind.sigs.k8s.io/docs/user/quick-start/"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "Error: kubectl is not installed."; exit 1; }

# Python 3.9+
python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null || { echo "Error: Python 3.9+ required. Check: python3 --version"; exit 1; }

# Docker running (required for KinD)
docker info >/dev/null 2>&1 || { echo "Error: Docker is not running. Start Docker Desktop or run: systemctl start docker"; exit 1; }

# Tool versions for reproducibility
echo "kind: $(kind --version 2>/dev/null || kind version 2>/dev/null)"
echo "kubectl: $(kubectl version --client --short 2>/dev/null || kubectl version --client 2>/dev/null)"

# Create cluster if it doesn't exist (use "kind get clusters" so we skip when nodes exist even if kubeconfig check would fail)
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "KinD cluster '$CLUSTER_NAME' already exists, skipping creation."
else
  echo "Creating KinD cluster '$CLUSTER_NAME' from $KIND_CONFIG ..."
  kind create cluster --name "$CLUSTER_NAME" --config "$KIND_CONFIG"
fi

# kind merges into default kubeconfig (~/.kube/config), so kubectl should work in this shell.
# If you need to use this cluster from another terminal: export KUBECONFIG=~/.kube/config
# and ensure context: kubectl config use-context kind-$CLUSTER_NAME

echo "Waiting for cluster nodes to be Ready..."
kubectl wait --for=condition=Ready nodes --all --timeout=120s 2>/dev/null || true

echo "Waiting for local-path-provisioner pods (namespace local-path-storage, label app=local-path-provisioner)..."
for i in {1..60}; do
  if kubectl get pods -n local-path-storage -l app=local-path-provisioner -o name 2>/dev/null | grep -q .; then
    echo "Found local-path-provisioner pod(s). Waiting for Ready..."
    kubectl wait --for=condition=ready pod -l app=local-path-provisioner -n local-path-storage --timeout=120s 2>/dev/null && break
  fi
  echo "Attempt $i: local-path-provisioner not ready yet..."
  sleep 3
done

if ! kubectl get pods -n local-path-storage -l app=local-path-provisioner -o name 2>/dev/null | grep -q .; then
  echo "Warning: No pods with label app=local-path-provisioner in local-path-storage."
  echo "KinD usually deploys this by default. Check: kubectl get pods -n local-path-storage"
  exit 1
fi

echo ""
echo "Cluster is ready for CI/tests_v2."
echo "  kubectl uses the default kubeconfig (kind merged it). For another terminal: export KUBECONFIG=~/.kube/config"
echo ""
echo "Next: activate your venv, install deps, and run tests from repo root:"
echo "  pip install -r requirements.txt"
echo "  pip install -r CI/tests_v2/requirements.txt"
echo "  pytest CI/tests_v2/ -v --timeout=300 --reruns=2 --reruns-delay=10"
