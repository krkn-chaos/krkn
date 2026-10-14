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
- **Production location:** `server.py` (repo root; GET handler returns `server_status`, which is initialized from the configured `signal_state` at bind time); signal polled in `run_kraken.py` chaos loop (~line 607; server started ~line 355).
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

## KRKN-003 — Cerberus `exit_on_failure` inverts documented semantics; healthy runs exit 1; "continue" branch unreachable

- **Issue ID:** KRKN-003
- **Title:** `krkn/cerberus/setup.py` exit policy: healthy + `exit_on_failure=True` → `sys.exit(1)`; unhealthy kills the run even with `exit_on_failure=False`; SystemExit bypasses run_kraken's exit-code ladder
- **Severity:** High — a user setting `exit_on_failure: true` gets a failing exit code (rc 1) on perfectly healthy runs after the first scenario; an unhealthy cluster under the "continue" policy still terminates the run; the exit also skips report/telemetry generation.
- **Status:** Reproduced (code-verified + git archaeology; integration tests currently pin the behavior).
- **Affected scenario:** `CI/tests_v2/scenarios/cerberus` (unhealthy-probe test retained; healthy-path tests removed as unit-pinned duplicates).
- **Production location:** `krkn/cerberus/setup.py` — `get_status()` exits 1 on unhealthy regardless of policy (:84-85); `publish_kraken_status()` healthy+`exit_on_failure` branch exits 1 (:113-118). Called per-scenario from `krkn/scenario_plugins/abstract_scenario_plugin.py:191`.
- **Evidence:** Git archaeology: the healthy+exit_on_failure exit is an accidental regression from #710 (commit 544cac8), which dropped the `failed_post_scenarios` gate required by the original logic (716057e). The unhealthy+continue-policy branch in `publish_kraken_status` is unreachable dead code because `get_status` exits first. Unit suite pins all four branches at `tests/test_cerberus_setup.py:183-218`.
- **Reproduction steps:**
  1. Configure `cerberus_enabled: true`, `cerberus_url` pointing at a healthy cerberus (returns `True`), `exit_on_failure: true`.
  2. Run kraken with one scenario.
  3. Observe rc 1 with "cluster is healthy, but exit_on_failure is set — exiting" (or equivalent) in logs.
- **Environment:** Environment-independent (control-plane logic).
- **Expected behavior:** `exit_on_failure` should gate the unhealthy case (exit 1 only when unhealthy AND exit_on_failure); a healthy cluster should never cause an exit.
- **Actual behavior:** Healthy + exit_on_failure → exit 1; unhealthy + continue-policy → exit 1 (policy ignored).
- **Impact:** False failures for any user who enables exit_on_failure with a healthy cluster; suppressed report/telemetry on cerberus-driven exits (SystemExit bypasses run_kraken's exit ladder at run_kraken.py:975-1010).
- **Related test:** `tests/test_cerberus_setup.py::test_publish_kraken_status_healthy_exit_on_failure_true` (regression pin, annotated); `CI/tests_v2/scenarios/cerberus/test_cerberus_unhealthy.py` (unhealthy path, rc==1).
- **Suggested follow-up:** Separate production-fix task: restore the failed-scenarios gate semantics in `publish_kraken_status` (healthy should continue; unhealthy should honor exit_on_failure), then invert the unit pin and extend the integration test.
- **Validation status:** Code-verified with git history; behavior pinned by existing unit tests; no production change made (out of scope).

---

## KRKN-005 — `PvcScenarioPlugin` string-division TypeError when `fill_percentage` is omitted

- **Issue ID:** KRKN-005
- **Title:** `pvc_scenario_plugin.py:190` computes `float(target_fill_percentage / 100)` — division happens before the float cast, and the in-code default is the string `"50"`, so `"50" / 100` raises TypeError
- **Severity:** Low-Medium — latent only because every YAML in the repo supplies an integer `fill_percentage`; any user relying on the documented default crashes.
- **Status:** Observed (code-verified).
- **Affected scenario:** `CI/tests_v2/scenarios/pvc` (integration test always supplies an int override, so it does not trip).
- **Production location:** `krkn/scenario_plugins/pvc/pvc_scenario_plugin.py:51-53` (string default `"50"`), `:190` (`float(target_fill_percentage / 100)`).
- **Evidence:** Direct code read during the tests_v2 audit: line 176 correctly casts before dividing (`float(target_fill_percentage) / 100`-equivalent logic for the percentage check), line 190 divides first. The unit suite pins fill-percentage validation only for supplied values.
- **Reproduction steps:**
  1. Configure a pvc scenario without `fill_percentage`.
  2. Run kraken.
  3. Observe `TypeError: unsupported operand type(s) for /: 'str' and 'int'` from line 190.
- **Environment:** Environment-independent.
- **Expected behavior:** The default fill percentage applies (50%) and the run proceeds.
- **Actual behavior:** TypeError on the file-size computation.
- **Impact:** Crash for any user omitting `fill_percentage` (or supplying it as a string).
- **Related test:** `tests/test_pvc_scenario_plugin.py` (invalid-percentage validation), `CI/tests_v2/scenarios/pvc/test_pvc.py::test_fill_keeps_target_pod_healthy` (passes only because it overrides with an int).
- **Suggested follow-up:** Separate production-fix task: `float(target_fill_percentage) / 100` and/or an int default. One-line fix.
- **Validation status:** Code-verified; not reproduced by execution (test scope forbids production changes); no fix attempted.

---

## KRKN-006 — `server.py` unknown POST path returns an empty reply instead of 404

- **Issue ID:** KRKN-006
- **Title:** `do_POST` in the repo-root status server sends no response for unknown paths; clients fail fast with an empty-reply error (curl rc 52)
- **Severity:** Low — no hang (connection closes immediately); clients get an opaque transport error instead of a 404.
- **Status:** Observed (empirically: `curl -X POST` to an unknown path returns rc 52 "Empty reply from server" in ~0.02s).
- **Affected scenario:** `CI/tests_v2/scenarios/pod_server` (adjacent; unit-covered at `tests/test_server.py:170-182` that no setter fires).
- **Production location:** `server.py:39-45` — `do_POST` handles `/STOP`, `/RUN`, `/PAUSE` with no else branch.
- **Evidence:** Empirical probe during the tests_v2 audit: POST to `/BOGUS` → connection closed with empty reply, rc 52, no 404.
- **Reproduction steps:**
  1. Start kraken with `publish_kraken_status: true`.
  2. `curl -v -X POST http://127.0.0.1:<port>/BOGUS`.
  3. Observe "Empty reply from server" (rc 52) instead of an HTTP 404.
- **Environment:** Environment-independent.
- **Expected behavior:** Unknown POST paths respond 404 (or 405) so clients can distinguish routing errors.
- **Actual behavior:** No response bytes; transport-level empty reply.
- **Impact:** Client ergonomics only; no state is mutated.
- **Related test:** `tests/test_server.py` (unknown-path no-setter coverage).
- **Suggested follow-up:** Separate production-fix task: add an else branch sending 404.
- **Validation status:** Observed empirically; mechanism trivial; no production change made (out of scope).


---

## KRKN-004 — `skew_node` NTP-off branch execs into a pod that was never created; node time-skew silently no-ops

- **Issue ID:** KRKN-004
- **Title:** `TimeActionsScenarioPlugin.skew_node` NTP-off branch runs `timedatectl set-time` against `skew_pod_name`, a pod that is never created; the exception is swallowed, so node date/time skew silently no-ops and exits 0
- **Severity:** Medium — the node clock-skew mutation path is dead in production; users running time_scenarios against NTP-disabled nodes get a run that logs "skewing" but changes nothing and exits 0.
- **Status:** Reproduced (code-verified by two independent auditors; unit-level repro in `.local-unit-tests/test_nodeinfra_local.py`). No runtime repro attempted — exercising it on KinD would mutate the shared host kernel clock.
- **Affected scenario:** `CI/tests_v2/scenarios/time_scenarios` (node object_type path; only the NTP-on refusal path is live and tested).
- **Production location:** `krkn/scenario_plugins/time_actions/time_actions_scenario_plugin.py:140-178` (`skew_node`): `status_pod_name`/`skew_pod_name` are two different random names; only `status_pod_name` is ever created via `kubecli.exec_command_on_node`; the NTP-off branch execs `timedatectl set-time` against the never-created `skew_pod_name`; `except ApiException: pass` and a generic `except Exception` swallow the failure; the finally block also deletes the nonexistent pod.
- **Evidence:** Line-verified: `skew_pod_name` is never passed to any pod-creating call in the file.
- **Reproduction steps:** (safe, unit-level) instantiate the plugin, mock `kubecli.exec_command_on_node` to return `"Network time on: no"`, call `skew_node(node, "skew_date", kubecli)`; the skew exec targets a pod name no create call produced.
- **Environment:** Environment-independent.
- **Expected behavior:** The `timedatectl set-time` exec targets a pod that exists (reuse the status exec pod or actually create the skew pod).
- **Actual behavior:** Exec against a nonexistent pod; exception swallowed; run exits 0 having skewed nothing. Compounded by KRKN-008 (check_date_time failures also never affect the exit code), so the no-op is invisible at every level.
- **Impact:** Silent no-op of node time chaos on NTP-off nodes.
- **Related test:** `CI/tests_v2/scenarios/time_scenarios/test_time_scenarios.py::test_worker_date_action_ntp_safe` (covers only the NTP-on refusal path).
- **Suggested follow-up:** Separate production-fix task: create/reuse a real pod for the skew exec and stop swallowing the ApiException.
- **Validation status:** Code-read confirmation by investigator and judge independently; no fix attempted (out of scope).

---

## KRKN-007 — invalid `node_name` fails only via accidental TypeError

- **Issue ID:** KRKN-007
- **Title:** `NodeActionsScenarioPlugin` with a non-existent `node_name` fails only through an accidental `TypeError` (`for single_node in None`), not a designed validation error
- **Severity:** Low — the exit code is correct (rc 1) by accident; the log shows a TypeError instead of a clear "node not found" message, and any future refactor to graceful handling silently changes failure semantics.
- **Status:** Observed (code-verified; the former integration negative passed through this path in all clean runs).
- **Affected scenario:** `CI/tests_v2/scenarios/node_scenarios` (invalid-node-name negative, demoted to unit).
- **Production location:** `krkn/scenario_plugins/node_actions/common_node_functions.py:22-31` (`get_node_by_name` logs "does not exist" and returns None); `krkn/scenario_plugins/node_actions/node_actions_scenario_plugin.py:206-228` (`inject_node_scenario` does not None-check; `for single_node in nodes` iterates None → TypeError) → caught by run()'s except → rc 1.
- **Evidence:** Line-verified; `get_node_by_name` has no raise path for missing names.
- **Reproduction steps:** Scenario yaml with `node_name: krkn-nonexistent-node-zzz` → kraken exits 1 with a TypeError traceback in the log.
- **Environment:** Environment-independent.
- **Expected behavior:** Explicit validation with a descriptive error (or documented graceful skip) when `node_name` is not a killable node.
- **Actual behavior:** `TypeError: 'NoneType' object is not iterable`, caught by the broad except; rc 1 by accident.
- **Impact:** Fragile contract; misleading diagnostics.
- **Related test:** `.local-unit-tests/test_nodeinfra_local.py::test_run_returns_error_when_node_name_not_killable` (annotated pin of the incidental behavior).
- **Suggested follow-up:** Separate production-fix task: None-check the `get_node_by_name` result and raise a descriptive error; then update the pinning unit test.
- **Validation status:** Code-read plus existing green integration evidence; no fix attempted (out of scope).

---

## KRKN-008 — `check_date_time` non-reset failures never affect the exit code

- **Issue ID:** KRKN-008
- **Title:** `TimeActionsScenarioPlugin`: `check_date_time` failures only log "Object times were not reset" and never produce a non-zero exit
- **Severity:** Low — a time scenario can exit 0 without having restored object clocks (false-positive success), compounding KRKN-004's invisibility.
- **Status:** Observed (code-verified: run() logs the not-reset result, never returns non-zero).
- **Affected scenario:** `CI/tests_v2/scenarios/time_scenarios`.
- **Production location:** `krkn/scenario_plugins/time_actions/time_actions_scenario_plugin.py:45-51` (run) and `:336-401` (check_date_time polling).
- **Evidence:** Direct code read during the audit; failures only logged.
- **Reproduction steps:** Run any time scenario whose target clock ends outside the observed window; rc stays 0.
- **Environment:** Environment-independent.
- **Expected behavior:** Non-reset clocks should fail the scenario or be explicitly configurable.
- **Actual behavior:** rc 0 with an info log only.
- **Impact:** False-positive "success" for time scenarios.
- **Related test:** None by design (a test pinning the quirk would cement it; document only).
- **Suggested follow-up:** Production decision task on check_date_time semantics; revisit coverage after.
- **Validation status:** Code-verified; no fix attempted (out of scope).

---

## KRKN-009 — Hog image `run.sh` writes to its read-only working directory on OpenShift

- **Issue ID:** KRKN-009
- **Title:** `workload-krkn-hog` image's `run.sh` writes `hog-jobfile.conf`/`output.yaml` into its working directory (`/stress-ng`), which OpenShift mounts read-only even for privileged pods — cpu/memory hog pods fail with "Read-only file system" (exit 1) on any OpenShift cluster
- **Severity:** Medium — cpu_hog and memory_hog scenarios are unusable on OpenShift (the pod always enters phase Failed); io_hog is unaffected because its `STRESS_PATH` hostPath is writable.
- **Status:** Reproduced (OpenShift gate run, 2026-10-14; isolated repro below).
- **Affected scenario:** `CI/tests_v2/scenarios/hogs` (cpu_hog, memory_hog happy paths).
- **Production location:** `workload-krkn-hog` image entrypoint `/stress-ng/run.sh` (line 32: `envsubst < cpu-hog.conf.template > hog-jobfile.conf` in CWD; `$STRESSNG -j hog-jobfile.conf -Y output.yaml` also writes to CWD). The pod template (krkn-lib `hog_pod.j2`) sets no workingDir/command override.
- **Evidence:** OpenShift gate run `.test-runs/audit-ocp-gate1-20261014-120403.log`: `test_hog_success_lifecycle_and_targeting[cpu_hog]`/`[memory_hog]` failed with "pod observed with phase Failed". Isolated repro (privileged pod exactly as `hog_pod.j2` renders, on OpenShift 4.22): container logs end with `run.sh: line 32: hog-jobfile.conf: Read-only file system` / `aborting: temp-path '.' must be readable and writeable`; exit code 1. Same pod on Kind: succeeds. Control experiment: running `cd /tmp && cp /stress-ng/*.conf.template . && /stress-ng/run.sh` on OpenShift completes with phase Succeeded, exit 0 — confirming the only blocker is the read-only CWD.
- **Reproduction steps:**
  1. On OpenShift, create a privileged pod with image `quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-hog`, env `HOG_TYPE=cpu LOAD_PERCENTAGE=50 CPU_METHOD=all WORKERS=1 DURATION=10`, default command.
  2. Observe phase Failed, exit 1, and the "Read-only file system" log lines.
- **Environment:** OpenShift (any; rootfs is read-only by SCC default regardless of privilege). Kind unaffected (container rootfs writable).
- **Expected behavior:** The hog image works on any conformant Kubernetes/OpenShift cluster (e.g. `run.sh` uses a guaranteed-writable temp dir such as `/tmp` for its jobfile/output, or the pod template mounts an emptyDir at the workdir).
- **Actual behavior:** cpu/memory hog pods always fail on OpenShift.
- **Impact:** cpu_hog/memory_hog chaos is broken for OpenShift users; the defect was previously masked in CI by `kind_only` markers on those tests (removed during the tests_v2 audit, which exposed it via the new Failed-phase watch).
- **Related test:** `CI/tests_v2/scenarios/hogs/test_hogs.py::test_hog_success_lifecycle_and_targeting[cpu_hog|memory_hog]` — now `kind_only` pending this fix (remove the marks when fixed).
- **Suggested follow-up:** Separate production-fix task in the hog image (or krkn-lib `hog_pod.j2`): write jobfiles to `/tmp` or mount an emptyDir. Then re-enable cpu/memory hog coverage on OpenShift.
- **Validation status:** Reproduced on OpenShift with an isolated pod; control experiment proves the read-only CWD is the sole cause. No production change made (out of scope).

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
