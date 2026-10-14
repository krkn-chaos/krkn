# Krkn Production Issues — Consolidated Report

**Scope:** All Krkn production (non-test) defects discovered during `CI/tests_v2` reliability validation (Section 14). Production fixes are **separate action items**; nothing in this file was patched in production code during this task.

**Rule:** One entry per defect. Update the existing entry when new evidence arrives; never duplicate.

---

## KRKN-001 — Node-scoped victim selection incorrectly constrains recovery wait

- **Issue ID:** KRKN-001
- **Title:** `PodDisruptionScenarioPlugin.wait_for_pods` applies the victim node selector during recovery, so replacements scheduled to other nodes are never counted
- **Severity:** High — breaks recovery on any multi-node cluster whenever the controller reschedules the replacement pod off the originally selected node(s); intermittently fails upstream CI on `main`.
- **Status:** Reproduced (intermittently on upstream `main` CI; deterministic variant reproduced locally during PR #1604 investigation).
- **Affected scenario:** `CI/tests_v2/scenarios/pod_disruption` (targeting tests); legacy `CI/tests/test_customapp_pod.sh` customapp scenario; upstream workflow "Functional & Unit Tests" runs (e.g. runs 36593648586, 36463110004 failed on `main`).
- **Production location:** `krkn/scenario_plugins/pod_disruption/pod_disruption_scenario_plugin.py`, `PodDisruptionScenarioPlugin.wait_for_pods` (~line 282 as of 2026-10).
- **Evidence:**
  - Upstream CI runs 36593648586 and 36463110004 (`Functional & Unit Tests` on `main`): `test_customapp_pod` fails with "timeout while waiting for pods to come up" after killing a coredns pod selected by `node_label_selector: node-role.kubernetes.io/control-plane=`.
  - Mechanism: kube-scheduler places the replacement coredns pod on a worker node; the recovery query still filters by the control-plane node selector, so the restored pod is invisible to the recovery wait; the 180s wait times out and the scenario fails.
  - PR #1604 commit 8a0de91 fixed it in production (cluster-wide `recovery_count`) and was deliberately reverted in 376c417 to keep that PR test-only.
- **Reproduction steps:**
  1. Kind cluster with ≥1 worker node (CI topology: 3 CP + 2 workers).
  2. Deploy a multi-replica workload without a node pin; run a pod-disruption scenario with `node_label_selector` matching only some nodes.
  3. Kraken deletes a pod whose replacement is scheduled elsewhere; observe the 180s recovery timeout and scenario failure.
- **Environment:** Kind (CI and local); expected to affect OpenShift identically (scheduler behavior), not yet observed there.
- **Expected behavior:** Recovery waits for the disrupted workload's pod count/health cluster-wide (or at least without the victim-scoping node filter), since the victim selector describes where victims were found, not where replacements must land.
- **Actual behavior:** Recovery wait inherits the victim node selector; replacements on other nodes are not counted; scenario fails with "timeout while waiting for pods to come up".
- **Impact:** False-negative chaos results and CI flakiness for any node-scoped pod disruption scenario on multi-node clusters. This intermittently fails upstream `main` CI today.
- **Related test:** `CI/tests_v2/scenarios/pod_disruption/test_pod_disruption_targeting.py::test_worker_selector_limits_victim_to_selected_node` (works around it by pinning its Deployment via nodeSelector); `CI/tests/test_customapp_pod.sh` (works around by patching coredns Deployment nodeSelector before the run).
- **Suggested follow-up:** Separate production-fix task: restore the 8a0de91 behavior — compute `recovery_count` cluster-wide when node selectors are used and drop node constraints from the recovery query. Then remove both test-side workarounds.
- **Validation status:** Root cause reproduced locally during PR #1604 (deterministic variant) and evidenced by upstream `main` CI failures; upstream fix not yet applied.

---

## KRKN-002 — No externally observable "signal observed" acknowledgment in the status server

- **Issue ID:** KRKN-002
- **Title:** Status-server GET `/` returns the *configured* signal state, so clients cannot distinguish "PAUSE configured" from "Kraken is honoring PAUSE"
- **Severity:** Low — no functional failure; makes PAUSE/RUN control-plane clients (including tests) rely on log scraping to prove Kraken has actually polled the signal.
- **Status:** Observed (design limitation, not a crash/failure).
- **Affected scenario:** `CI/tests_v2/scenarios/pod_server` (PAUSE/RUN control tests).
- **Production location:** `krkn/server.py` (GET handler returns `server_status`, which is initialized from the configured `signal_state` at bind time); signal polled in `run_kraken.py` chaos loop (~line 607; server started ~line 355).
- **Evidence:** During PR #1604 investigation: GET `/` after bind always reflects the configured state; the first signal poll happens only when the chaos loop starts. A client that POSTs RUN after bind but before the first poll causes Kraken to skip PAUSE entirely (observed as `pause_index == -1` in `test_pause_waits_then_run_signal_releases`, CI run 36643150388).
- **Reproduction steps:**
  1. Start Kraken with `signal_state: PAUSE`, `publish_kraken_status: true`.
  2. Immediately after the server accepts requests, POST `RUN`.
  3. Kraken's first poll sees RUN and never pauses; no "Pausing Kraken run" is logged.
- **Environment:** Kind (local + CI); environment-independent (control-plane logic).
- **Expected behavior:** An endpoint (or GET payload field) exposing Kraken's internal, last-polled `run_signal` so clients can prove the pause was observed before releasing.
- **Actual behavior:** Only the configured state is visible; observability of the actual signal handling requires log scraping.
- **Impact:** Testability only; forces tests to scrape stderr markers. No end-user functional impact.
- **Related test:** `CI/tests_v2/scenarios/pod_server/test_pod_server.py::test_pause_waits_then_run_signal_releases` (uses `_wait_for_output("Pausing Kraken run")` as the acknowledgment gate).
- **Suggested follow-up:** Separate enhancement task: publish Kraken's internal `run_signal` (last-polled state) via the status server.
- **Validation status:** Observed directly during PR #1604 debugging; mechanism fully understood; no fix attempted (out of scope).

---

## Investigation notes (not production defects)

- **`test_pause_waits_then_run_signal_releases` CI failure (run 36643150388):** test-side race, not a Krkn bug — fixed test-only in commit 961b6c6 by gating the RUN POST on the live "Pausing Kraken run" stderr marker. Recorded here because the failure signature (pod-disruption evidence missing, `pause_index == -1`) initially resembles KRKN-002.
- A local kind failure of the same test on 2026-09-30 (`.test-runs/kind-20260930-005417.log`, `AssertionError: assert 1 is None` from `proc.poll()`) occurred on a stale environment (krkn-lib 6.1.5 in venv while requirements pin 7.0.3). Environment defect, not production. Re-validated under the correct krkn-lib 7.0.3 with the exact CI command during this task (see validation report).

---

## Validation context (2026-10-14)

Full-suite reliability validation executed with the exact `tests_v2.yml` CI command (`KRKN_TEST_COVERAGE=1 python -m pytest CI/tests_v2/ -v --timeout=300 --reruns=1 --reruns-delay=5 -n auto --dist loadgroup`) on both environments:

- **Kind (3 CP + 2 workers, CI topology):** run 1 exposed a test-side timing defect in `service_hijacking::test_plan_runs_and_restores_service` (see note below — **not** a production defect); after the test-only fix, **5 consecutive clean runs** (89 passed / 2 skipped, zero failures, zero reruns, full namespace cleanup).
- **OpenShift 4.22.14 (blue-cluster, 9 nodes, kubeconfig `example/event-driven-triggers/gcp/kubeconfig`, context `admin`):** **5 consecutive clean runs** (79 passed / 12 skipped — 5 `kind_only` + NTP/telemetry/second-worker conditional skips — zero failures, zero reruns, full namespace cleanup).

### Non-defect: `service_hijacking::test_plan_runs_and_restores_service` cold-pull timeout (test-side, fixed)

Kind run 1 failed with "Service selector never redirected from {'app': 'nginx'}". Root cause: the test polled for the Service selector redirect for only 45s, but Kraken legitimately blocks up to 120s waiting for the hijacker pod to reach Running (krkn-lib `create_pod`) before patching the selector. The workflow does not preload `quay.io/krkn-chaos/krkn-service-hijacking:v0.1.3` (~350MB); a cold pull was measured at **48.35s** (kube event: `Successfully pulled image … in 48.352s … Image size: 350667185 bytes`). Deterministic reproduction: evicting the image from all kind nodes → failure with identical signature; warm cache → pass. Fix (test-only): observation window raised 45s → 150s with the budget documented; verified passing against a cold cache. No Krkn production code changed.
