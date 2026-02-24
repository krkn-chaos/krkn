# Pytest Functional Tests (tests_v2)

This directory contains a pytest-based functional test framework that runs **alongside** the existing bash tests in `CI/tests/`. It covers the **pod disruption** and **application outage** scenarios with proper assertions, retries, and reporting.

Each test runs in its **own ephemeral Kubernetes namespace** (`krkn-test-<uuid>`). Before the test, the framework creates the namespace, deploys the target workload, and waits for pods to be ready. After the test, the namespace is deleted (cascading all resources). **You do not need to deploy any workloads manually.**

## Prerequisites

Without a cluster, tests that need one will **skip** with a clear message (e.g. *"Could not load kube config"*). No manual workload deployment is required; workloads are deployed automatically into ephemeral namespaces per test.

- **KinD cluster** (or any Kubernetes cluster) running with `kubectl` configured (e.g. `KUBECONFIG` or default `~/.kube/config`).
- **Python 3.9+** and main repo deps: `pip install -r requirements.txt`.


### Setting up the cluster

**Option A: Use the setup script (recommended)**

From the repository root, with `kind` and `kubectl` installed:

```bash
# Create KinD cluster (uses kind-config.yml)
./CI/tests_v2/setup_env.sh
```

Then in the same shell (or after `export KUBECONFIG=~/.kube/config` in another terminal), activate your venv and install Python deps:

```bash
python3 -m venv venv
source venv/bin/activate   # or: source venv/Scripts/activate on Windows
pip install -r requirements.txt
pip install -r CI/tests_v2/requirements.txt
```

**Option B: Manual setup**

1. Install [kind](https://kind.sigs.k8s.io/docs/user/quick-start/) and [kubectl](https://kubernetes.io/docs/tasks/tools/).
2. Create a cluster (from repo root):
   ```bash
   kind create cluster --name kind --config kind-config.yml
   ```
3. Wait for the cluster:
   ```bash
   kubectl wait --for=condition=Ready nodes --all --timeout=120s
   ```
4. Create a virtualenv, activate it, and install dependencies (as in Option A).
5. Run tests from repo root: `pytest CI/tests_v2/ -v ...`

## Install test dependencies

From the repository root:

```bash
pip install -r CI/tests_v2/requirements.txt
```

This adds `pytest-rerunfailures`, `pytest-html`, `pytest-timeout`, and `pytest-order` (pytest and coverage come from the main `requirements.txt`).

## Run tests

All commands below are from the **repository root**.

### Basic run (with retries and HTML report)

```bash
pytest CI/tests_v2/ -v --timeout=300 --reruns=2 --reruns-delay=10 --html=CI/tests_v2/report.html --junitxml=CI/tests_v2/results.xml
```

- Failed tests are **retried up to 2 times** with a 10s delay (configurable in `CI/tests_v2/pytest.ini`).
- Each test has a **5-minute timeout**.
- Open `CI/tests_v2/report.html` in a browser for a detailed report.

### Run without retries (for debugging)

```bash
pytest CI/tests_v2/ -v -p no:rerunfailures
```

### Run with coverage

```bash
python -m coverage run -m pytest CI/tests_v2/ -v
python -m coverage report
```

To append to existing coverage from unit tests, ensure coverage was started with `coverage run -a` for earlier runs, or run the full test suite in one go.

### Run only pod disruption tests

```bash
pytest CI/tests_v2/ -v -m pod_disruption
```

### Run only application outage tests

```bash
pytest CI/tests_v2/ -v -m application_outage
```

### Run with verbose output and no capture

```bash
pytest CI/tests_v2/ -v -s
```

### Keep failed test namespaces for debugging

When a test fails, its ephemeral namespace is normally deleted. To **keep** the namespace so you can inspect pods, logs, and network policies:

```bash
pytest CI/tests_v2/ -v --keep-ns-on-fail
```

On failure, the namespace name is printed (e.g. `[keep-ns-on-fail] Keeping namespace krkn-test-a1b2c3d4 for debugging`). Use `kubectl get pods -n krkn-test-a1b2c3d4` (and similar) to debug, then delete the namespace manually when done.

### Logging and cluster options

- **Structured logging**: Use `--log-cli-level=DEBUG` to see namespace creation, workload deploy, and readiness in the console. Use `--log-file=test.log` to capture logs to a file.
- **Require dev cluster**: To avoid running against the wrong cluster, use `--require-kind`. Tests will skip unless the current kube context cluster name contains "kind" or "minikube".
- **Stale namespace cleanup**: At session start, namespaces matching `krkn-test-*` that are older than 30 minutes are deleted (e.g. from a previous crashed run).

## Architecture

- **Folder-per-scenario**: Each scenario lives under `scenarios/<scenario_name>/` with:
  - **test_<scenario>.py** — Test class extending `BaseScenarioTest`; sets `WORKLOAD_MANIFEST` to the folder’s `resource.yaml`.
  - **resource.yaml** — Kubernetes resources (Deployment/Pod) for the scenario; namespace is patched at deploy time.
  - **scenario_base.yaml** — Canonical Krkn scenario; tests load it, patch namespace (and any overrides), write to `tmp_path`, and pass to `build_config`. Optional extra YAMLs (e.g. `nginx_http.yaml` for application_outage traffic test) can live in the same folder.
- **lib/**: Shared framework — `lib/base.py` defines `BaseScenarioTest` and timeout constants; `lib/utils.py` provides helpers (`assert_all_pods_running_and_ready`, `assert_pod_count_unchanged`, `assert_kraken_success`, `load_scenario_base`, `scenario_dir`, etc.).
- **conftest.py**: Session fixtures load kubeconfig once, provide K8s API clients, `test_namespace`, `deploy_workload`, `run_kraken`, `build_config`. Manifests are applied with namespace patching.
- **Adding a new scenario**: Use the scaffold script (see [CONTRIBUTING_TESTS.md](CONTRIBUTING_TESTS.md)) to create `scenarios/<name>/` with test file, `resource.yaml`, and `scenario_base.yaml`, or copy an existing scenario folder and adapt.

## What is tested

Each test runs in an isolated ephemeral namespace; workloads are deployed automatically before the test and the namespace is deleted after (unless `--keep-ns-on-fail` is set and the test failed).

- **scenarios/pod_disruption/**  
  Pod disruption scenario. `resource.yaml` is a deployment with label `app=krkn-pod-disruption-target`; `scenario_base.yaml` is loaded and `namespace_pattern` is patched to the test namespace. The test:
  1. Records baseline pod UIDs and restart counts.
  2. Runs Kraken with the pod disruption scenario.
  3. Asserts that chaos had an effect (UIDs changed or restart count increased).
  4. Waits for pods to be Running and all containers Ready.
  5. Asserts pod count is unchanged and all pods are healthy.

- **scenarios/application_outage/**  
  Application outage scenario (block Ingress/Egress to target pods, then restore). `resource.yaml` is the main workload (outage pod); `scenario_base.yaml` is loaded and patched with namespace (and duration/block as needed). Optional `nginx_http.yaml` is used by the traffic test. Tests include:
  - **test_app_outage_block_and_restore**: Happy path; Krkn exit 0, pods still Running/Ready.
  - **test_network_policy_created_then_deleted**: Policy with prefix `krkn-deny-` appears during run and is gone after.
  - **test_traffic_blocked_during_outage**: Deploys nginx with label `scenario=outage`, port-forwards; during outage curl fails, after run curl succeeds.
  - **test_block_type_variants** (parametrized): Runs with `block: [Ingress]`, `[Egress]`, and `[Ingress, Egress]`; each exits 0 and pods remain.
  - **test_exclude_label_e2e**: Scenario with `exclude_label: {"env": "prod"}` runs and restores.
  - **test_invalid_scenario_fails**: Invalid scenario file (missing `application_outage` key) causes Kraken to exit non-zero.
  - **test_bad_namespace_fails**: Scenario targeting a non-existent namespace causes Kraken to exit non-zero.

## Configuration

- **pytest.ini**: Markers (`functional`, `pod_disruption`, `application_outage`, `no_workload`). Use `--timeout=300`, `--reruns=2`, `--reruns-delay=10` on the command line for full runs.
- **conftest.py**: Shared fixtures (`test_namespace`, `deploy_workload`, `k8s_core`, `k8s_apps`, `k8s_client`, `k8s_networking`, `kubectl`, `run_kraken`, `build_config`, `wait_for_pod_ready`). Kubeconfig is loaded once per session. Configs are built from `CI/config/common_test_config.yaml` with monitoring disabled for local runs. Timeout constants live in `base.py` and are used across waits.
- **Cluster access**: Reads and applies use the Kubernetes Python client; `kubectl` is still used for `port-forward` and for running Kraken.
- **utils.py**: Pod/network policy helpers and assertion helpers (`assert_all_pods_running_and_ready`, `assert_pod_count_unchanged`, `assert_kraken_success`, `patch_namespace_in_docs`).

## Relationship to existing CI

- The **existing** bash tests in `CI/tests/` and `CI/run.sh` are **unchanged**. They continue to run as before in GitHub Actions.
- This framework is **additive**. To run it in CI later, add a separate job or step that runs `pytest CI/tests_v2/ ...` from the repo root.
