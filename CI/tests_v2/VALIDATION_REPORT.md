# Section 14 — CI/tests_v2 Reliability Validation Report

**Date:** 2026-10-14
**Branch:** `ddjain:fix/ci-tests-v2-kind-openshift` (upstream PR: krkn-chaos/krkn#1604)
**Executor:** local macOS arm64 + GitHub Actions ubuntu-latest

## A. Actual GitHub Actions workflow (source of truth: `.github/workflows/tests_v2.yml`)

- **Workflow name:** `Tests v2 (pytest functional)`; job `tests-v2`, `runs-on: ubuntu-latest`, `timeout-minutes: 60`.
- **Triggers:** `pull_request` (any), `push` to `main` only. No `workflow_dispatch`.
- **Steps (in order):**
  1. `actions/checkout@v3` (pinned).
  2. Free disk space (`rm -rf` dotnet/ghc/android/AGENTS_TOOLSDIRECTORY, `docker image prune -af`).
  3. **Cluster provisioning:** `redhat-chaos/actions/kind@main` (pinned SHA aa42122…): installs kind v0.26.0 + latest stable kubectl, creates cluster with `kind-config.yml` from repo root if present — **3 control-plane + 2 worker nodes**, `--wait 300s`, 3 attempts; waits for nodes Ready.
  4. **Pre-load images:** `docker pull nginx:alpine`, `kind load docker-image nginx:alpine`, `docker pull quay.io/krkn-chaos/krkn:tools`, `kind load docker-image quay.io/krkn-chaos/krkn:tools`. ⚠️ The service-hijacking image `quay.io/krkn-chaos/krkn-service-hijacking:v0.1.3` (~350MB) is **not** preloaded — pulled cold during the suite (see KRKN-003 note in issues file).
  5. **Python:** `setup-python@v4`, Python **3.11** x64, pip cache.
  6. **Dependencies:** `apt-get install build-essential python3-dev`; `pip install -r requirements.txt`; `pip install -r CI/tests_v2/requirements.txt`; `pip install --force-reinstall --no-deps setuptools==81.0.0`.
  7. **Test command (exact):**
     `KRKN_TEST_COVERAGE=1 python -m pytest CI/tests_v2/ -v --timeout=300 --reruns=1 --reruns-delay=5 --html=CI/tests_v2/report.html -n auto --dist loadgroup --junitxml=CI/tests_v2/results.xml`
     (working dir = repo root; env `KRKN_TEST_COVERAGE=1`)
  8. **Artifacts:** always upload `report.html`, `results.xml`, `assets/`.
- **Cleanup:** none (ephemeral runner); namespace cleanup is test-side (`lib/namespace.py` + `--keep-ns-on-fail` opt-out).

## Local reproduction fidelity

| Aspect | GitHub Actions | Local kind runs | Fidelity |
|---|---|---|---|
| Cluster | kind v0.26.0, 3 CP + 2 workers, repo `kind-config.yml` | kind v0.31.0, same `kind-config.yml`, same topology | Topology identical; kind version newer locally (v0.31 vs v0.26 — action pins v0.26; k8s patch level differs accordingly) |
| Images preloaded | nginx:alpine, krkn:tools | same, via `kind load docker-image` | Identical (hijacker image cold in both) |

**Unverifiable locally:** ubuntu/x64-specific behavior, CI runner disk/network characteristics, `apt-get`-built wheels, exact kind v0.26 + k8s version pairing. Covered instead by the actual-workflow CI gate (§CI).

## B/C. Local Kind validation (exact CI command)

Runs from repo root, `KUBECONFIG` → `kind-kind` (3 CP + 2 workers). Logs: `.test-runs/ciexact-kind-*.log`.

| Run | Date (local) | Result | Notes |
|---|---|---|---|
| 1 | 2026-10-13 23:35 | **FAIL** — 88 passed, 1 failed, 1 rerun, 2 skipped | `service_hijacking::test_plan_runs_and_restores_service` — "Service selector never redirected" |
| (repro a) | isolated, warm cache | PASS (90s) | failure is load/cold-pull dependent |
| (repro b) | isolated, image evicted from all nodes | **FAIL** (78s) — same signature; kube events: image pull took **48.35s** for 350MB | deterministic cold-pull repro |
| fix | `test_service_hijacking.py` | observation window 45s → 150s (kraken's own pod-start budget is 120s) | test-only fix; see defect analysis below |
| (fix check) | isolated, image evicted from all nodes | PASS (156s) | cold pull absorbed |
| 2 | 2026-10-14 00:15 | **PASS** — 89 passed, 2 skipped, 0 rerun (27:05) | namespaces fully cleaned (3 were mid-Terminating at check, cleared) |
| 3 | 2026-10-14 00:42 | **PASS** — 89 passed, 2 skipped (27:15) | 0 reruns |
| 4 | 2026-10-14 01:10 | **PASS** — 89 passed, 2 skipped (26:54) | 0 reruns |
| 5 | 2026-10-14 01:37 | **PASS** — 89 passed, 2 skipped (26:52) | 0 reruns |
| 6 | 2026-10-14 02:04 | **PASS** — 89 passed, 2 skipped (27:06) | 0 reruns; gate met — **5 consecutive clean runs post-fix** |

### Failure analysis: `test_plan_runs_and_restores_service` (run 1)

- **Classification: test defect** (timing assumption), not a Krkn production defect.
- Kraken's flow (`krkn/scenario_plugins/service_hijacking/service_hijacking_scenario_plugin.py`: `deploy_service_hijacking` → krkn-lib `create_pod` blocks until hijacker pod is Running, **timeout 120s** → only then `replace_service_selector`). The test polled for selector redirection for only **45s**. With a cold ~350MB image pull (48.35s observed; quay multi-arch, not preloaded by CI), the selector legitimately arrives after the test's deadline.
- **Evidence:** kube events `Successfully pulled image … in 48.352s … Image size: 350667185 bytes`; deterministic fail on evicted cache, pass with warm cache; pass after extending the window.
- **Fix (test-only):** observation window raised to 150s with a comment documenting the budget. Verified: cold-cache repro now passes.

## D. Local OpenShift validation

- **Kubeconfig:** `example/event-driven-triggers/gcp/kubeconfig` — exists, `current-context: admin`, `cluster-info` OK, `clusterversion 4.22.14`, 9/9 nodes Ready, `auth can-i create namespace` → yes, `delete pods` → yes. No credential contents printed or committed.
- **Execution:** exact CI command with `KUBECONFIG` pointed at the OpenShift kubeconfig (only adaptation allowed by spec).
- **Prior local evidence (2026-09-29/30, `.test-runs/openshift-*.log`, same branch state minus this task's test fix):** full-suite runs with `-n 4` — final 3 consecutive EXIT:0 (79 passed / 12 skipped each; 5 kind_only tests auto-skip on non-kind cluster, plus scenario-conditional skips), after earlier flaky failures were fixed test-side in prior iterations (recorded in PR #1604 history).
- **This task's runs (exact CI command, `KUBECONFIG` → OpenShift kubeconfig, isolated `$HOME`):** logs `.test-runs/ciexact-ocp-*.log`

| Run | Date (local) | Result | Notes |
|---|---|---|---|
| 1 | 2026-10-14 02:34 | **PASS** — 79 passed, 12 skipped (49:49) | 0 reruns; namespaces drained |
| 2 | 2026-10-14 03:25 | **PASS** — 79 passed, 12 skipped (49:16) | 0 reruns |
| 3 | 2026-10-14 04:15 | **PASS** — 79 passed, 12 skipped (49:56) | 0 reruns |
| 4 | 2026-10-14 05:05 | **PASS** — 79 passed, 12 skipped (49:31) | 0 reruns |
| 5 | 2026-10-14 05:54 | **PASS** — 79 passed, 12 skipped (59:23) | 0 reruns; gate met — **5 consecutive clean runs**; namespaces drained |

Skips on OpenShift (12): 5 `kind_only` tests (require local KinD node containers), NTP-probe skip (`timedatectl` unavailable in OCP nodes — unsafe clock mutation correctly refused), telemetry (no `AWS_BUCKET`), instance-count limiting (single-schedulable-worker check), plus scenario-conditional skips. No failures, no reruns, no leaked namespaces across all 5 runs.

## CI gate (GitHub Actions, actual workflow)

- Channel: upstream PR #1604 (`pull_request` events on `ddjain:fix/ci-tests-v2-kind-openshift`).
- Prior runs on this branch: 38420493352 (success, 2026-10-13 15:15Z), 38427198646 (success, 2026-10-13 16:02Z) — predate this task's new fix.
- Post-push runs: (pending — need ≥5 consecutive successes)

## Test status summary

Per-environment classification; updated as runs complete.

| Test / area | Kind | OpenShift |
|---|---|---|
| Full `CI/tests_v2` suite | run 1 FAIL (test defect, fixed) → run 2 PASS | NOT RUN (this task yet; prior-iteration evidence only) |
| `service_hijacking::test_plan_runs_and_restores_service` | FLAKY→fixed (test-side), cold-cache verified | NOT RUN |
| All other tests (88 scenarios/tests) | PASS (runs 1–2) | prior-iteration PASS evidence only |
