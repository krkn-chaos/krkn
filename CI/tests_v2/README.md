# Pytest Functional Tests (tests_v2)

This directory contains a pytest-based functional test framework that runs **alongside** the existing bash tests in `CI/tests/`. It covers the **pod disruption** and **application outage** scenarios with proper assertions, retries, and reporting.

Each test runs in its **own ephemeral Kubernetes namespace** (`krkn-test-<uuid>`). Before the test, the framework creates the namespace, deploys the target workload, and waits for pods to be ready. After the test, the namespace is deleted (cascading all resources). **You do not need to deploy any workloads manually.**

## Prerequisites

Without a cluster, tests that need one will **skip** with a clear message (e.g. *"Could not load kube config"*). No manual workload deployment is required; workloads are deployed automatically into ephemeral namespaces per test.

- **KinD cluster** (or any Kubernetes cluster) running with `kubectl` configured (e.g. `KUBECONFIG` or default `~/.kube/config`).
- **Python 3.9+** and main repo deps: `pip install -r requirements.txt`.

### Supported clusters

- **KinD** (recommended): Use `make -f CI/tests_v2/Makefile setup` from the repo root. Fastest for local dev; uses a 2-node dev config by default. Override with `KIND_CONFIG=/path/to/kind-config.yml` for a larger cluster.
- **Minikube**: Should work; ensure `kubectl` context is set. Not tested in CI.
- **Remote/cloud cluster**: Tests create and delete namespaces; use with caution. Use `--require-kind` to avoid accidentally running against production (tests will skip unless context is kind/minikube).

### Setting up the cluster

**Option A: Use the setup script (recommended)**

From the repository root, with `kind` and `kubectl` installed:

```bash
# Create KinD cluster (defaults to CI/tests_v2/kind-config-dev.yml; override with KIND_CONFIG=...)
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

## Dependency Management

Dependencies are split into two files:

- **Root `requirements.txt`** — Kraken runtime (cloud SDKs, Kubernetes client, krkn-lib, pytest, coverage, etc.). Required to run Kraken.
- **`CI/tests_v2/requirements.txt`** — Test-only pytest plugins (rerunfailures, html, timeout, order, xdist). Not needed by Kraken itself.

**Rule of thumb:** If Kraken needs it at runtime, add to root. If only the functional tests need it, add to `CI/tests_v2/requirements.txt`.

Running `make -f CI/tests_v2/Makefile setup` (or `make setup` from `CI/tests_v2`) creates the venv and installs **both** files automatically; you do not need to install them separately. The Makefile re-installs when either file changes (via the `.installed` sentinel).

## Run tests

All commands below are from the **repository root**.

### Basic run (with retries and HTML report)

```bash
pytest CI/tests_v2/ -v --timeout=300 --reruns=2 --reruns-delay=10 --html=CI/tests_v2/report.html --junitxml=CI/tests_v2/results.xml
```

- Failed tests are **retried up to 2 times** with a 10s delay (configurable in `CI/tests_v2/pytest.ini`).
- Each test has a **5-minute timeout**.
- Open `CI/tests_v2/report.html` in a browser for a detailed report.

### Run in parallel (faster suite)

```bash
pytest CI/tests_v2/ -v -n 4 --timeout=300
```

Ephemeral namespaces make tests parallel-safe; use `-n` with the number of workers (e.g. 4).

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
- **Timeout overrides**: Set env vars to tune timeouts (e.g. in CI): `KRKN_TEST_READINESS_TIMEOUT`, `KRKN_TEST_DEPLOY_TIMEOUT`, `KRKN_TEST_NS_CLEANUP_TIMEOUT`, `KRKN_TEST_POLICY_WAIT_TIMEOUT`, `KRKN_TEST_KRAKEN_PROC_WAIT_TIMEOUT`, `KRKN_TEST_TIMEOUT_BUDGET`.

## Architecture

- **Folder-per-scenario**: Each scenario lives under `scenarios/<scenario_name>/` with:
  - **test_<scenario>.py** — Test class extending `BaseScenarioTest`; sets `WORKLOAD_MANIFEST`, `SCENARIO_NAME`, `SCENARIO_TYPE`, `NAMESPACE_KEY_PATH`, and optionally `OVERRIDES_KEY_PATH`.
  - **resource.yaml** — Kubernetes resources (Deployment/Pod) for the scenario; namespace is patched at deploy time.
  - **scenario_base.yaml** — Canonical Krkn scenario; the base class loads it, patches namespace (and overrides), and passes it to Kraken via `run_scenario()`. Optional extra YAMLs (e.g. `nginx_http.yaml` for application_outage) can live in the same folder.
- **lib/**: Shared framework — `lib/base.py` defines `BaseScenarioTest`, timeout constants (env-overridable), and scenario helpers (`load_and_patch_scenario`, `run_scenario`); `lib/utils.py` provides assertion and K8s helpers; `lib/k8s.py` provides K8s client fixtures; `lib/namespace.py` provides namespace lifecycle; `lib/deploy.py` provides `deploy_workload`, `wait_for_pods_running`, `wait_for_deployment_replicas`; `lib/kraken.py` provides `run_kraken`, `build_config` (using `CI/tests_v2/config/common_test_config.yaml`).
- **conftest.py**: Re-exports fixtures from the lib modules and defines `pytest_addoption`, logging, and `repo_root`.
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
  - **test_app_outage_block_restore_and_variants**: Happy path with default, exclude_label, and block variants (Ingress, Egress, both); Krkn exit 0, pods still Running/Ready.
  - **test_network_policy_created_then_deleted**: Policy with prefix `krkn-deny-` appears during run and is gone after.
  - **test_traffic_blocked_during_outage** (disabled, planned): Deploys nginx with label `scenario=outage`, port-forwards; during outage curl fails, after run curl succeeds.
  - **test_invalid_scenario_fails**: Invalid scenario file (missing `application_outage` key) causes Kraken to exit non-zero.
  - **test_bad_namespace_fails**: Scenario targeting a non-existent namespace causes Kraken to exit non-zero.

## Configuration

- **pytest.ini**: Markers (`functional`, `pod_disruption`, `application_outage`, `no_workload`). Use `--timeout=300`, `--reruns=2`, `--reruns-delay=10` on the command line for full runs.
- **conftest.py**: Re-exports fixtures from `lib/k8s.py`, `lib/namespace.py`, `lib/deploy.py`, `lib/kraken.py` (e.g. `test_namespace`, `deploy_workload`, `k8s_core`, `wait_for_pods_running`, `run_kraken`, `build_config`). Configs are built from `CI/tests_v2/config/common_test_config.yaml` with monitoring disabled for local runs. Timeout constants in `lib/base.py` can be overridden via env vars.
- **Cluster access**: Reads and applies use the Kubernetes Python client; `kubectl` is still used for `port-forward` and for running Kraken.
- **utils.py**: Pod/network policy helpers and assertion helpers (`assert_all_pods_running_and_ready`, `assert_pod_count_unchanged`, `assert_kraken_success`, `assert_kraken_failure`, `patch_namespace_in_docs`).

## Relationship to existing CI

- The **existing** bash tests in `CI/tests/` and `CI/run.sh` are **unchanged**. They continue to run as before in GitHub Actions.
- This framework is **additive**. To run it in CI later, add a separate job or step that runs `pytest CI/tests_v2/ ...` from the repo root.

## Troubleshooting

- **`pytest.skip: Could not load kube config`** — No cluster or bad KUBECONFIG. Run `make -f CI/tests_v2/Makefile setup` (or `make setup` from `CI/tests_v2`) or check `kubectl cluster-info`.
- **KinD cluster creation hangs** — Docker is not running. Start Docker Desktop or run `systemctl start docker`.
- **`Bind for 0.0.0.0:9090 failed: port is already allocated`** — Another process (e.g. Prometheus) is using the port. The default dev config (`kind-config-dev.yml`) no longer maps host ports; if you use `KIND_CONFIG=kind-config.yml` or a custom config with `extraPortMappings`, free the port or switch to `kind-config-dev.yml`.
- **`TimeoutError: Pods did not become ready`** — Slow image pull or node resource limits. Increase `KRKN_TEST_READINESS_TIMEOUT` or check node resources.
- **`ModuleNotFoundError: pytest_rerunfailures`** — Missing test deps. Run `pip install -r CI/tests_v2/requirements.txt` (or `make setup`).
- **Stale `krkn-test-*` namespaces** — Left over from a previous crashed run. They are auto-cleaned at session start (older than 30 min). To remove cluster and reports: `make -f CI/tests_v2/Makefile clean`.
- **Wrong cluster targeted** — Multiple kube contexts. Use `--require-kind` to skip unless context is kind/minikube, or set context explicitly: `kubectl config use-context kind-ci-krkn`.
- **`OSError: [Errno 48] Address already in use` when running tests in parallel** — Kraken normally starts an HTTP status server on port 8081. With `-n auto` (pytest-xdist), multiple Kraken processes would all try to bind to 8081. The test framework disables this server (`publish_kraken_status: False`) in the generated config, so parallel runs should not hit this. If you see it, ensure you're using the framework's `build_config` and not a config that has `publish_kraken_status: True`.
