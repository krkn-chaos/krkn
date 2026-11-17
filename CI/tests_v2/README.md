# Pytest Functional Tests (tests_v2)

This directory contains a pytest-based functional test framework that runs **alongside** the existing bash tests in `CI/tests/`. It covers the **application outage**, **Cerberus**, **container**, **CPU hog**, **memory hog**, **I/O hog**, **namespace deletion**, **network chaos**, **node**, **node network chaos**, **pod disruption**, **pod error**, **pod network chaos**, **pod network filter**, **pod server**, **PVC**, **service hijacking**, **storage throttle**, **telemetry**, and **time** scenarios with proper assertions, retries, and reporting.

Each test runs in its **own ephemeral Kubernetes namespace** (`krkn-test-<uuid>`). Before the test, the framework creates the namespace, deploys the target workload, and waits for pods to be ready. After the test, the namespace is deleted (cascading all resources). **You do not need to deploy any workloads manually.**

## Prerequisites

Without a cluster, tests that need one will **skip** with a clear message (e.g. *"Could not load kube config"*). No manual workload deployment is required; workloads are deployed automatically into ephemeral namespaces per test.

- **KinD cluster** (or any Kubernetes cluster) running with `kubectl` configured (e.g. `KUBECONFIG` or default `~/.kube/config`).
- **Python 3.11+** and main repo deps: `pip install -r requirements.txt`.

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
pytest CI/tests_v2/ -v -n 4 --dist loadgroup --timeout=300
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

### Run only CPU hog tests

```bash
pytest CI/tests_v2/ -v -m cpu_hog
```

The hog family is consolidated into `scenarios/hogs/test_hogs.py` with a parameterized happy path: `-m cpu_hog`, `-m memory_hog`, and `-m io_hog` each select only the corresponding happy-path param (the negatives and the signature test are hog-type-independent), while `-m functional CI/tests_v2/scenarios/hogs/` covers the whole family.

### Run only node scenarios tests

```bash
pytest CI/tests_v2/ -v -m node_scenarios
```

> **Note:** Node scenarios stop/reboot a worker node (a KinD node is a Docker/Podman container), which is cluster-wide disruption. Run them on a KinD cluster you can afford to disrupt, and prefer a multi-worker cluster when combining with other scenarios under `-n auto` (see the parallelism note in `scenarios/node_scenarios/test_node_scenarios.py`).

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
- **Platform-scoped contracts**: Tests marked `kind_only` skip on remote clusters when their assertion requires a local KinD/Minikube node container runtime. Kubernetes API and privileged helper-pod network tests remain enabled on OpenShift.
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

  The node-selector targeting test kills a pod on a selected worker, then checks that the replacement recovers even if Kubernetes schedules it on another worker. Node selection constrains victims, not recovery placement.

- **scenarios/application_outage/**  
  Application outage scenario (block Ingress/Egress to target pods, then restore). `resource.yaml` is the main workload (outage pod); `scenario_base.yaml` is loaded and patched with namespace (and duration/block as needed). Tests include:
  - **test_app_outage_block_restore_and_variants**: Happy path with default, exclude_label, and block variants (Ingress, Egress, both); Krkn exit 0, pods still Running/Ready.
  - **test_network_policy_created_then_deleted**: Policy with prefix `krkn-deny-` appears during run and is gone after.

  Negative config paths (invalid scenario, bad namespace) are covered at unit level; the former traffic-probe test was removed (dead code since Feb 2026 — Kind's default CNI does not enforce NetworkPolicy, making the contract unrunnable there without new infra).

- **scenarios/hogs/**
  Consolidated hog family test (`hog_scenarios`: cpu, memory, io), migrated from the legacy per-family `CI/tests/test_{cpu,memory,io}_hog.sh` and the former per-family test files. The scenario yamls stay in the per-family registry dirs (`scenarios/cpu_hog/`, `scenarios/memory_hog/`, `scenarios/io_hog/`); this module is the family-level test. Hogs target nodes (not workloads): Krkn deploys a short-lived hog pod (name prefix `<type>-hog-`) onto each selected node, runs `stress-ng` for the configured duration, then deletes the pod. Tests use `@pytest.mark.no_workload` (no app deployment needed). Tests include:
  - **test_hog_success_lifecycle_and_targeting**: Parameterized happy path (cpu/memory/io via `pytest.param` with per-family marks — `-m cpu_hog` etc. select the single corresponding param). A hog pod is created on the `node-selector` target and, while Kraken runs, the test polls it and fails if it is ever observed with phase `Failed` (terminal under `restartPolicy: Never`, so zero false positives; a broken hog image/env contract fails seconds into the run). Residual gap (accepted): a pod failing at t≈duration and deleted by the plugin within ~1s can escape the watch. The run exits 0 with execution evidence (`running <type> hog scenario` in the output) and the pod is cleaned up afterward. Runs on Kind and OpenShift (the former `kind_only` on cpu/memory happy paths was removed — the loads are test-tuned trivial and the io happy path was already proven green on OpenShift).
  - **test_hog_invalid_selector_fails**: A `node-selector` matching zero nodes causes Krkn to exit non-zero (no available nodes to schedule). Hog-type-independent — fails at node selection before any per-type branch; the demoted per-family duplicates are pinned by the local unit layer (`.local-unit-tests/test_hogs_local.py`).
  - **test_hog_invalid_config_fails**: Omitting the mandatory `hog-type` field causes Krkn to exit non-zero at config parsing. Hog-type-independent — the raise happens before any per-type field parsing.
  - **test_unsigned_legacy_hog_image_is_rejected**: Image signature verification rejects the legacy production image (pinned digest): Krkn exits non-zero with `Image signature verification failed` naming the digest, and no pod is created. Hog-agnostic — fails in `create_pod`'s image verification before any hog-type-specific branch; relocated from the former cpu_hog file.

- **scenarios/node_scenarios/**
  Node chaos scenario (`node_scenarios`), migrated from the legacy `CI/tests/test_node.sh`. Node scenarios are destructive at the *node* level: Krkn stops, starts, or reboots the container that backs a Kubernetes node. On KinD each node is a Docker/Podman container, so the tests use `cloud_type: docker` and target a **worker** node only (never the control plane). Tests use `@pytest.mark.no_workload` (no app deployment needed); `scenario_base.yaml` holds a single `node_scenarios` entry that each test patches per case. A finalizer ensures the targeted node container is running (starting it only if it was left stopped) and waits for the node to return `Ready`. Tests include:
  - **test_node_reboot_targets_node_name_and_recovers**: Happy path — `node_reboot_scenario` targeted by `node_name` reboots the worker. Krkn runs with `kube_check: False` (its in-process Unknown→Ready wait is brittle behind the multi-control-plane KinD API load balancer); disruption is proven by the node container's `StartedAt` advancing and recovery by the node returning Ready.
  - **test_node_stop_start_targets_label_selector_and_recovers**: Happy path — `node_stop_start_scenario` targeted by `label_selector` stops then starts the worker. Same approach: `kube_check: False`, disruption proven by `StartedAt` advancing and recovery by the node returning Ready.
  - **test_unknown_action_is_skipped** (`kind_only` — the docker node-scenario object needs a local Docker/Podman socket): An unrecognized action is skipped (logged, no node touched) and Krkn still exits 0.

  Config-error negatives (invalid selector/node name, missing actions, unsupported cloud type) and the worker-targeting helper's control-plane exclusion are pinned by unit tests instead of cluster runs (missing-actions and unsupported-cloud are in the pushed `tests/` suite; the rest live in the local unit layer pending a separate push).

- **scenarios/container_scenarios/**
  Container disruption scenario (`container_scenarios`). `resource.yaml` provides the target Deployment with container `fedtools` and label `scenario=container`; `resource_decoy.yaml` provides a second Deployment with the same container name but label `scenario=decoy`. `scenario_base.yaml` is a `scenarios` list whose namespace, selector, container name, count, and recovery time are patched per test; `action` stays fixed at its base value across all tests. Tests include:
  - **test_container_kill_and_recovery**: Happy path — kills the selected container, verifies that the run succeeds and the scenario executes, then waits for the target pod to recover and remain Ready.
  - **test_container_label_selector_targeting**: Deploys the decoy workload and verifies that only pods matching `scenario=container` are affected; the decoy pod remains running and ready.
  - **test_invalid_container_name_fails**: Uses a container name that does not exist and a kill count that cannot be satisfied; Kraken exits non-zero.
  - **test_invalid_label_selector_fails**: Uses a selector that matches no pods even though workloads exist; Kraken exits non-zero.

- **scenarios/namespace_deletion/**
  Namespace deletion scenario (`service_disruption_scenarios`). `resource.yaml` provides a workload in the target namespace; `scenario_base.yaml` configures namespace matching, optional namespace label selection, `delete_count`, `runs`, `sleep`, and `wait_time`. Tests include:
  - **test_single_namespace_object_deletion**: Matches exactly one namespace, verifies that its Kubernetes objects are deleted, and confirms a successful Kraken run.
  - **test_multiple_namespace_delete_count**: Creates three matching namespaces and uses `delete_count=2`; exactly two namespaces are disrupted while one remains untouched.
  - **test_multiple_runs_repeat_disruption_loop**: Sets `runs=2` and verifies that the namespace disruption loop executes twice.
  - **test_label_selector_targeting**: Leaves the namespace field empty, targets namespaces by label, and verifies that only the labeled namespace is selected.
  - **test_no_match_namespace_fails**: Uses a regex that matches no namespaces; Kraken exits non-zero with a clear failure.
  - **test_namespace_and_label_mutual_exclusion_fails**: Sets both a namespace and a `label_selector`; Kraken exits with the expected mutual-exclusion error.
  - **test_delete_count_exceeds_available_fails**: Requests more namespaces than match the selection; Kraken exits non-zero with a `not enough namespaces` failure.

- **scenarios/node_network_chaos/**
  Node network chaos scenario (`network_chaos_ng_scenarios`). `scenario_base.yaml` contains the list-based configuration for the `krkn-network-chaos` helper image, target node, packet loss, latency, bandwidth, direction, instance count, and cleanup behavior. Tests use a worker node and include:
  - **test_variants_apply_netem_and_cleanup**: Runs a list of impairment variants (packet loss, latency with ingress/egress, bandwidth limit, and egress-only direction), verifies that `netem` is applied during chaos on local runtimes and cleaned up afterward, confirms the helper pod is removed, and checks that all cluster nodes remain Ready.
  - **test_instance_count_with_label_selector**: Uses a label selector matching multiple nodes and verifies that only the configured `instance_count` is targeted.
  - **test_force_false_skips_injection_when_tc_rules_exist**: Prepares existing traffic-control rules and verifies that `force=false` warns and skips injection instead of overriding them.
  - **test_nonexistent_target_node_fails**: Specifies a node that does not exist; Kraken fails gracefully.
  - **test_no_nodes_matching_selector_warns**: Uses a selector with no matches; Kraken logs that no targets were found and exits 0 without injecting chaos.

- **scenarios/pod_error_scenarios/**
  Pod disruption failure-mode coverage using the `pod_disruption_scenarios` plugin. `resource.yaml` provides the target workload, and `scenario_base.yaml` configures the namespace pattern, label selector, recovery time, and kill count. Tests include:
  - **test_kill_multiple_pods**: Kills multiple matching pods (`kill: 2`), verifies that disruption occurs across at least two pods, and confirms that all pods recover.
  - **test_excessive_kill_count_fails**: Requests more pods than are available; Kraken exits non-zero with the count-check error.
  - **test_recovery_timeout_fails**: Deploys a workload whose replacement pods cannot become Ready within the configured recovery window and verifies that Kraken reports failure.

- **scenarios/storage_throttle/**
  Storage throttle scenario (`storage_throttle_scenarios`). `resource.yaml` provides a workload with the `krkn-throttle-pvc` volume mounted at `/data`; `scenario_base.yaml` configures the PVC, pod, mount path, throttle type, bandwidth, IOPS, duration, and helper image. Tests include:
  - **test_throttle_and_recovery**: Applies combined read/write bandwidth (`bps`) and `iops` limits (`throttle_type: both`), verifies a successful Kraken run, and confirms that target pods remain Running and Ready. Negative config-validation paths (bad namespace, invalid `throttle_type`) are covered by the unit test suite (`tests/test_storage_throttle_scenario_plugin.py`).

- **scenarios/network_chaos/**
  Legacy node network chaos scenario (`network_chaos_scenarios`). `scenario_base.yaml` configures node-level traffic control impairments (`latency`, `bandwidth`, `loss`). Tests use `@pytest.mark.no_workload` and include:
  - **test_netem_applied_and_cleaned** (`kind_only`): Parameterized across bandwidth and latency egress variants; observes an active `netem` qdisc on the target worker node during chaos, then verifies exit 0, node readiness, `netem` removal, and cleanup of helper resources.
  - **test_nonexistent_node_fails**: Targets a node name that does not exist and verifies that Kraken exits non-zero.

- **scenarios/pod_network_chaos/**
  Pod-level network impairment scenario (`network_chaos_ng_scenarios`). `resource.yaml` deploys the target workload and service, and `scenario_base.yaml` configures pod network latency and packet loss. Tests include:
  - **test_latency_loss_and_recovery**: Measures peer HTTP traffic from a traffic pod to the target service, verifies delayed responses while `netem` is active, and confirms traffic recovery and helper pod cleanup after rollback.
  - **test_nonexistent_target_fails**: Specifies a pod target that does not exist and verifies that Kraken exits non-zero with a not-found error.

- **scenarios/pod_network_filter/**
  Pod network filtering scenario (`network_chaos_ng_scenarios`) applying iptables port/protocol filtering inside pod network namespaces. `resource.yaml` deploys the target workload and service; `scenario_base.yaml` configures ingress/egress port and protocol rules. Tests include:
  - **test_filter_variants_lifecycle_and_cleanup**: Runs a list of protocol (`tcp`, `udp`), port, and direction (`ingress`, `egress`) variants, verifying exit 0, duration adherence, rule cleanup, and pod health.
  - **test_tcp_port_block_traffic_and_recovery**: Verifies that peer HTTP traffic to port 80 is blocked while the filter is active and restored once the scenario completes.
  - **test_label_selector_targeting**: Targets pods via `label_selector` with `instance_count=1` and verifies that only one matching pod is filtered.
  - **test_no_matching_pods_for_label**: Uses a label selector that matches no pods and verifies that Kraken treats it as a clean no-op (exit 0 with no helper pods left behind).
  - **test_filter_rules_removed_after_scenario**: Observes the live helper pod during execution, verifies filter cleanup afterward, and confirms a subsequent run succeeds without stale state.

- **scenarios/pvc/**
  PVC disk fill scenario (`pvc_scenarios`). `resource.yaml` deploys a PVC-backed pod with `/data` mounted, and `scenario_base.yaml` configures the target PVC, pod, fill percentage, and duration. Tests include:
  - **test_fill_keeps_target_pod_healthy**: Observes the temporary fill file (`kraken.tmp`) growing on the mounted volume during chaos, verifies its removal on rollback, and confirms the target pod stays Running and Ready.

- **scenarios/service_hijacking/**
  Service hijacking scenario (`service_hijacking_scenarios`). `resource.yaml` deploys an `nginx` pod and `nginx-service`; `scenario_base.yaml` defines the hijacking plan and custom HTTP responses. Tests include:
  - **test_plan_runs_and_restores_service**: Observes the Service selector redirecting traffic to the hijacker pod and returning the configured plan response during chaos, then verifies full selector restoration and hijacker resource cleanup after rollback.
  - **test_missing_service_fails**: Targets a Service that does not exist and verifies that Kraken exits non-zero.
  - **test_interrupted_hijack_rolls_back_service**: Sends `SIGTERM` while the Service is hijacked and verifies that Kraken's rollback handler restores the original Service selector and removes the hijacker pod.

- **scenarios/time_scenarios/**
  Pod and node clock skew scenario (`time_scenarios`). `resource.yaml` deploys the target pod workload, and `scenario_base.yaml` configures `skew_time` actions against pods or nodes. Tests include:
  - **test_pod_time_action_resets_safely**: Executes a pod `skew_time` action, verifies that Kraken logs the date check/reset flow and exits 0, and confirms the pod remains healthy.
  - **test_worker_date_action_ntp_safe**: Executes a node `skew_time` action against a worker node and verifies NTP-safe reset handling and node readiness.

- **scenarios/cerberus/**
  Cerberus health-gate integration coverage (`cerberus`). Runs a pod disruption scenario configured to poll a local mock Cerberus HTTP endpoint:
  - **test_unhealthy_probe_reports_health_failure**: Configures Cerberus to return an unhealthy (`False`) status and verifies that Kraken exits with code `1` when the health check fails.

- **scenarios/pod_server/**
  Kraken daemon mode and HTTP status-server (`PAUSE`/`RUN`/`STOP`) control-plane integration coverage (`pod_server`). Tests include:
  - **test_daemon_stop_via_status_api**: Starts Kraken in `daemon_mode` and verifies that posting `STOP` to the status endpoint terminates the daemon cleanly (exit 0).
  - **test_pause_waits_then_run_signal_releases**: Starts Kraken with `signal_state: PAUSE`, verifies that no pod disruption occurs while paused, then posts `RUN` and confirms the disruption executes and pods recover.

- **scenarios/telemetry/**
  Credential-gated S3 telemetry upload integration coverage (`telemetry`). Skips automatically when `AWS_BUCKET` or the `aws` CLI is unavailable:
  - **test_telemetry_uploads_core_artifacts**: Runs Kraken with telemetry enabled and verifies that the core telemetry artifacts are uploaded under the run's unique S3 request prefix.

## Configuration

- **pytest.ini**: Markers (`functional`, `pod_disruption`, `pod_error_scenarios`, `application_outage`, `storage_throttle`, `cpu_hog`, `memory_hog`, `io_hog`, `container_scenarios`, `node_scenarios`, `kind_only`, `node_network_chaos`, `namespace_deletion`, `no_workload`, `order`, `xdist_group`, `network_chaos`, `pvc`, `time_scenarios`, `service_hijacking`, `pod_network_chaos`, `pod_network_filter`, `cerberus`, `telemetry`, `pod_server`). Use `--timeout=300`, `--reruns=2`, `--reruns-delay=10` on the command line for full runs.
- **conftest.py**: Re-exports fixtures from `lib/k8s.py`, `lib/namespace.py`, `lib/deploy.py`, `lib/kraken.py` (e.g. `test_namespace`, `deploy_workload`, `k8s_core`, `wait_for_pods_running`, `run_kraken`, `build_config`). Configs are built from `CI/tests_v2/config/common_test_config.yaml` with monitoring disabled for local runs. Timeout constants in `lib/base.py` can be overridden via env vars.
- **Cluster access**: Reads and applies use the Kubernetes Python client; `kubectl` is still used for `port-forward` and for running Kraken.
- **utils.py**: Pod/network policy helpers and assertion helpers (`assert_all_pods_running_and_ready`, `assert_pod_count_unchanged`, `assert_kraken_success`, `assert_kraken_failure`, `patch_namespace_in_docs`).

## Relationship to existing CI

- The **existing** bash tests in `CI/tests/` and `CI/run.sh` are **unchanged**. They continue to run as before in GitHub Actions.
- This framework is **additive**. The `Tests v2 (pytest functional)` workflow in `.github/workflows/tests_v2.yml` creates a KinD cluster and runs `pytest CI/tests_v2/ ...` on pull requests and pushes to `main`.

## Troubleshooting

- **`pytest.skip: Could not load kube config`** — No cluster or bad KUBECONFIG. Run `make -f CI/tests_v2/Makefile setup` (or `make setup` from `CI/tests_v2`) or check `kubectl cluster-info`.
- **KinD cluster creation hangs** — Docker is not running. Start Docker Desktop or run `systemctl start docker`.
- **`Bind for 0.0.0.0:9090 failed: port is already allocated`** — Another process (e.g. Prometheus) is using the port. The default dev config (`kind-config-dev.yml`) no longer maps host ports; if you use `KIND_CONFIG=kind-config.yml` or a custom config with `extraPortMappings`, free the port or switch to `kind-config-dev.yml`.
- **`TimeoutError: Pods did not become ready`** — Slow image pull or node resource limits. Increase `KRKN_TEST_READINESS_TIMEOUT` or check node resources.
- **`ModuleNotFoundError: pytest_rerunfailures`** — Missing test deps. Run `pip install -r CI/tests_v2/requirements.txt` (or `make setup`).
- **Stale `krkn-test-*` namespaces** — Left over from a previous crashed run. They are auto-cleaned at session start (older than 30 min). To remove cluster and reports: `make -f CI/tests_v2/Makefile clean`.
- **Wrong cluster targeted** — Multiple kube contexts. Use `--require-kind` to skip unless context is kind/minikube, or set context explicitly: `kubectl config use-context kind-ci-krkn`.
- **`OSError: [Errno 48] Address already in use` when running tests in parallel** — Kraken normally starts an HTTP status server on port 8081. With `-n auto` (pytest-xdist), multiple Kraken processes would all try to bind to 8081. The test framework disables this server (`publish_kraken_status: False`) in the generated config, so parallel runs should not hit this. If you see it, ensure you're using the framework's `build_config` and not a config that has `publish_kraken_status: True`.
