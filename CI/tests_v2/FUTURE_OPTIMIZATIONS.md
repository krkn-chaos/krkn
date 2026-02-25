# Future Optimizations (CI/tests_v2)

This document captures medium- and long-term performance and scalability improvements identified during the test framework performance audit. These items are **not** planned for immediate implementation; they are recorded for future consideration as the test suite grows or CI budgets tighten.

---

## Lighter workload images

**Context:** The application outage workload uses `quay.io/krkn-chaos/krkn:tools` but only runs `sleep infinity`. The pod is used as a NetworkPolicy target; no tooling inside the container is exercised by current tests.

**Idea:** Evaluate replacing this image with a minimal image such as `busybox` or `registry.k8s.io/pause` (or equivalent). Benefits:

- Much smaller image size (1–5 MB vs. potentially hundreds of MB).
- Faster first-run pulls and lower registry rate-limit pressure in CI.
- Same functional behavior for existing tests (label selector + `sleep infinity`).

**Caveat:** Confirm that no scenario or future test depends on tools inside that container before changing.

---

## Module/class-scoped workload fixtures

**Context:** Today every test method gets its own ephemeral namespace and deploys the same workload (e.g. one namespace per test in `TestApplicationOutage`). With 7 test methods in that class, that means 7 full deploy/teardown cycles for identical infrastructure.

**Idea:** Introduce a module- or class-scoped fixture that creates one namespace and deploys the workload once, then reuse it across test methods in the same class. Teardown happens once at the end of the class/module.

**Benefits:**

- Fewer namespace lifecycles and fewer workload deployments.
- Significant time savings as test count grows (e.g. 20–50+ tests).

**Risks:**

- Tests must not mutate shared state in ways that break subsequent tests.
- Requires careful review of test order and isolation; may need a “reset” step (e.g. wait for pods to re-settle) between tests.

**Recommendation:** Revisit when the number of tests in a single scenario class exceeds ~15–20, or when CI runtime becomes a bottleneck.

---

## Kraken-as-library (in-process execution)

**Context:** Each test run invokes Kraken via `subprocess.run(python run_kraken.py ...)`. Every invocation pays full Python interpreter startup, import of krkn_lib/kubernetes/cloud SDKs, `ScenarioPluginFactory` loading, K8s client init, and post-run telemetry. This fixed overhead (on the order of 15–35 seconds per run) often exceeds the actual scenario execution time.

**Idea:** Call Kraken’s `main()` (or a dedicated entry point) in-process from the test process instead of spawning a subprocess. That would remove:

- Per-invocation Python startup and heavy imports.
- Repeated plugin factory and K8s client initialization.
- Process teardown and output capture overhead.

**Blockers:**

- Kraken’s `main()` and supporting code use module-level state, global config, and `logging.basicConfig`. It is not currently designed to be “run multiple times” in the same process.
- Requires refactoring in the Kraken application (run_kraken.py and related modules), not just the test framework.

**Recommendation:** Treat as a long-term Kraken core refactoring project. Do not pursue from the test framework alone unless Kraken exposes a clean, re-entrant execution API.

---

## Telemetry skip gate

**Context:** Even with Prometheus/Elastic disabled in test configs, Kraken still runs `telemetry_k8s.collect_cluster_metadata(chaos_telemetry)` and related serialization/logging at the end of every run. This adds roughly 5–15 seconds per Kraken invocation.

**Idea:** Add an environment variable (e.g. `KRKN_TEST_SKIP_TELEMETRY=1`) that, when set, skips cluster metadata collection (and optionally other telemetry) during test runs.

**Blocker:** This requires a change in the Kraken application (e.g. in `run_kraken.py` or the telemetry module), not in the test framework. The test framework cannot implement this without modifying Kraken.

**Recommendation:** If and when Kraken adds a “lightweight” or “test” mode, request such a gate and use it from CI/tests_v2.

---

## Multi-node KinD and resource scaling

**Context:** With `pytest-xdist -n auto`, multiple tests run in parallel. On a small KinD cluster (e.g. 1 control-plane + 1 worker), many concurrent namespace creations, workload deployments, and Kraken subprocesses can saturate CPU/memory/API server.

**Ideas:**

- Use a KinD config with more worker nodes when targeting high parallelism (e.g. 50+ tests).
- Consider resource limits or quotas per test (e.g. limit replicas or namespace count per worker).
- Document recommended CI runner resources (CPU, memory) and max workers (e.g. `-n 4` vs `-n auto`) for stability.

**Recommendation:** Revisit when regularly running 20+ tests in parallel or when CI jobs show resource-related flakes.

---

## Scalability projections

Rough expectations from the performance audit (single worker; with xdist, wall time scales down by worker count, but cluster load increases).

| Test count | Sequential (approx.) | With xdist -n 4 (approx.) | What tends to break first |
|-----------|----------------------|----------------------------|----------------------------|
| 8 (current) | 7–19 min | 2–5 min | Nothing; acceptable. |
| 20 | 18–48 min | 5–12 min | CI time budget (e.g. 15–30 min). |
| 50 | 45–120 min | 12–30 min | CI budget and developer patience. |
| 100 | 90–240 min | 25–60 min | Unusable without structural changes. |

Before scaling beyond ~20 tests, the following are recommended:

- Background namespace deletion (already implemented).
- Image pre-pull in setup (already implemented for nginx:alpine).
- Reduced `wait_duration` in test config (already implemented).
- Ensuring xdist is used in CI.

Before scaling beyond ~50 tests, consider:

- Module/class-scoped workload fixtures.
- Lighter workload images where safe.
- Multi-node KinD and documented resource/worker limits.
- Any Kraken-side optimizations (telemetry skip, or in-process execution if available).

---

## Summary

Short-term, low-risk improvements (background namespace deletion, `wait_duration` patch, nginx image pre-pull) are implemented in the framework. The items above are deferred: either they require Kraken application changes, or they are only justified at higher test count/CI load. Revisit this document when adding many new tests or when CI duration becomes a problem.
