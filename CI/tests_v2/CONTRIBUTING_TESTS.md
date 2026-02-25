# Adding a New Scenario Test (CI/tests_v2)

This guide explains how to add a new chaos scenario test to the v2 pytest framework. The layout is **folder-per-scenario**: each scenario has its own directory under `scenarios/<scenario_name>/` containing the test file, Kubernetes resources, and the Krkn scenario base YAML.

## Option 1: Scaffold script (recommended)

From the **repository root**:

```bash
python CI/tests_v2/scaffold.py --scenario service_hijacking
```

This creates:

- `CI/tests_v2/scenarios/service_hijacking/test_service_hijacking.py` — A test class extending `BaseScenarioTest` with a stub `test_happy_path` and `WORKLOAD_MANIFEST` pointing to the folder’s `resource.yaml`.
- `CI/tests_v2/scenarios/service_hijacking/resource.yaml` — A placeholder Deployment (namespace is patched at deploy time).
- `CI/tests_v2/scenarios/service_hijacking/scenario_base.yaml` — A placeholder Krkn scenario; edit this with the structure expected by your scenario type.

The script automatically registers the marker in `CI/tests_v2/pytest.ini`. For example, it adds:

```
service_hijacking: marks a test as a service_hijacking scenario test
```

**Next steps after scaffolding:**

1. Verify the marker was added to `pytest.ini` (the scaffold does this automatically).
2. Edit `scenario_base.yaml` with the structure your Krkn scenario type expects (see `scenarios/application_outage/scenario_base.yaml` and `scenarios/pod_disruption/scenario_base.yaml` for examples). The top-level key should match `SCENARIO_NAME`.
3. If your scenario uses a **list** structure (like pod_disruption) instead of a **dict** with a top-level key, set `NAMESPACE_KEY_PATH` (e.g. `[0, "config", "namespace_pattern"]`) and `NAMESPACE_IS_REGEX = True` if the namespace is a regex pattern.
4. The generated `test_happy_path` already uses `self.run_scenario(self.tmp_path, ns)` and assertions. Add more test methods (e.g. negative tests with `@pytest.mark.no_workload`) as needed.
5. Adjust `resource.yaml` if your scenario needs a different workload (e.g. specific image or labels).

If your Kraken scenario type string is not `<scenario>_scenarios`, pass it explicitly:

```bash
python CI/tests_v2/scaffold.py --scenario node_disruption --scenario-type node_scenarios
```

## Option 2: Manual setup

1. **Create the scenario folder**  
   `CI/tests_v2/scenarios/<scenario_name>/`.

2. **Add resource.yaml**  
   Kubernetes manifest(s) for the workload (Deployment or Pod). Use a distinct label (e.g. `app: <scenario>-target`). Omit or leave `metadata.namespace`; the framework patches it at deploy time.

3. **Add scenario_base.yaml**  
   The canonical Krkn scenario structure. Tests will load this, patch namespace (and any overrides), write to `tmp_path`, and pass to `build_config`. See existing scenarios for the format your scenario type expects.

4. **Add test_<scenario>.py**  
   - Import `BaseScenarioTest` from `lib.base` and helpers from `lib.utils` (e.g. `assert_kraken_success`, `get_pods_list`, `scenario_dir` if needed).
   - Define a class extending `BaseScenarioTest` with:
     - `WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/<scenario_name>/resource.yaml"`
     - `WORKLOAD_IS_PATH = True`
     - `LABEL_SELECTOR = "app=<label>"`
     - `SCENARIO_NAME = "<scenario_name>"`
     - `SCENARIO_TYPE = "<scenario_type>"` (e.g. `application_outages_scenarios`)
     - `NAMESPACE_KEY_PATH`: path to the namespace field (e.g. `["application_outage", "namespace"]` for dict-based, or `[0, "config", "namespace_pattern"]` for list-based)
     - `NAMESPACE_IS_REGEX = False` (or `True` for regex patterns like pod_disruption)
     - `OVERRIDES_KEY_PATH = ["<top-level key>"]` if the scenario supports overrides (e.g. duration, block).
   - Add `@pytest.mark.functional` and `@pytest.mark.<scenario>` on the class.
   - In at least one test, call `self.run_scenario(self.tmp_path, self.ns)` and assert with `assert_kraken_success`, `assert_pod_count_unchanged`, and `assert_all_pods_running_and_ready`. Use `self.k8s_core`, `self.tmp_path`, etc. (injected by the base class).

5. **Register the marker**  
   In `CI/tests_v2/pytest.ini`, under `markers`:
   ```
   <scenario>: marks a test as a <scenario> scenario test
   ```

## Conventions

- **Folder-per-scenario**: One directory per scenario under `scenarios/`. All assets (test, resource.yaml, scenario_base.yaml, and any extra YAMLs) live there for easy tracking and onboarding.
- **Ephemeral namespace**: Every test gets a unique `krkn-test-<uuid>` namespace. The base class deploys the workload into it before the test; no manual deploy is required.
- **Negative tests**: For tests that don’t need a workload (e.g. invalid scenario, bad namespace), use `@pytest.mark.no_workload`. The test will still get a namespace but no workload will be deployed.
- **Scenario type**: `SCENARIO_TYPE` must match the key in Kraken’s config (e.g. `application_outages_scenarios`, `pod_disruption_scenarios`). See `CI/tests_v2/config/common_test_config.yaml` and the scenario plugin’s `get_scenario_types()`.
- **Assertions**: Use `assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)` so failures include stdout/stderr and optional log files.
- **Timeouts**: Use constants from `lib.base` (`READINESS_TIMEOUT`, `POLICY_WAIT_TIMEOUT`, etc.) instead of magic numbers.

## Running your new tests

```bash
pytest CI/tests_v2/ -v -m <scenario>
```

For debugging with logs and keeping failed namespaces:

```bash
pytest CI/tests_v2/ -v -m <scenario> --log-cli-level=DEBUG --keep-ns-on-fail
```

---

## Naming Conventions

Follow these conventions so the framework stays consistent as new scenarios are added.

### Quick Reference

| Element | Pattern | Example |
|---|---|---|
| Scenario folder | `scenarios/<snake_case>/` | `scenarios/node_disruption/` |
| Test file | `test_<scenario>.py` | `test_node_disruption.py` |
| Test class | `Test<CamelCase>(BaseScenarioTest)` | `TestNodeDisruption` |
| Pytest marker | `@pytest.mark.<scenario>` (matches folder) | `@pytest.mark.node_disruption` |
| Scenario YAML | `scenario_base.yaml` | — |
| Workload YAML | `resource.yaml` | — |
| Extra YAMLs | `<descriptive_name>.yaml` | `nginx_http.yaml` |
| Lib modules | `lib/<concern>.py` | `lib/deploy.py` |
| Public fixtures | `<verb>_<noun>` or `<noun>` | `run_kraken`, `test_namespace` |
| Private/autouse fixtures | `_<descriptive>` | `_cleanup_stale_namespaces` |
| Assertion helpers | `assert_<condition>` | `assert_pod_count_unchanged` |
| Query helpers | `get_<resource>` or `find_<resource>_by_<criteria>` | `get_pods_list`, `find_network_policy_by_prefix` |
| Env var overrides | `KRKN_TEST_<NAME>` | `KRKN_TEST_READINESS_TIMEOUT` |

### Folders

- One folder per scenario under `scenarios/`. The folder name is `snake_case` and must match the `SCENARIO_NAME` class attribute in the test.
- Shared framework code lives in `lib/`. Each module covers a single concern (`k8s`, `namespace`, `deploy`, `kraken`, `utils`, `base`, `preflight`).
- Do **not** add scenario-specific code to `lib/`; keep it in the scenario folder as module-level helpers.

### Files

- Test files: `test_<scenario>.py`. This is required for pytest discovery (`test_*.py`).
- Workload manifests: always `resource.yaml`. If a scenario needs additional K8s resources (e.g. a Service for traffic testing), use a descriptive name like `nginx_http.yaml`.
- Scenario config: always `scenario_base.yaml`. This is the template that `load_and_patch_scenario` loads and patches.

### Classes

- One test class per file: `Test<CamelCase>` extending `BaseScenarioTest`.
- The CamelCase name must be the PascalCase equivalent of the folder name (e.g. `pod_disruption` -> `TestPodDisruption`).

### Test Methods

- Prefix: `test_` (pytest requirement).
- Use descriptive names that convey **what is being verified**, not implementation details.
- Good: `test_pod_crash_and_recovery`, `test_traffic_blocked_during_outage`, `test_invalid_scenario_fails`.
- Avoid: `test_run_1`, `test_scenario`, `test_it_works`.

### Fixtures

- **Public fixtures** (intended for use in tests): use `<verb>_<noun>` or plain `<noun>`. Examples: `run_kraken`, `deploy_workload`, `test_namespace`, `kubectl`.
- **Private/autouse fixtures** (framework internals): prefix with `_`. Examples: `_kube_config_loaded`, `_preflight_checks`, `_inject_common_fixtures`.
- K8s client fixtures use the `k8s_` prefix: `k8s_core`, `k8s_apps`, `k8s_networking`, `k8s_client`.

### Helpers and Utilities

- **Assertions**: `assert_<what_is_expected>`. Always raise `AssertionError` with a message that includes the namespace.
- **K8s queries**: `get_<resource>_list` for direct API calls, `find_<resource>_by_<criteria>` for filtered lookups.
- **Private helpers**: prefix with `_` for module-internal functions (e.g. `_pods`, `_policies`, `_get_nested`).

### Constants and Environment Variables

- Timeout constants: `UPPER_CASE` in `lib/base.py`. Each is overridable via an env var prefixed `KRKN_TEST_`.
- Feature flags: `KRKN_TEST_DRY_RUN`, `KRKN_TEST_COVERAGE`. Always use the `KRKN_TEST_` prefix so all tunables are discoverable with `grep KRKN_TEST_`.

### Markers

- Every test class gets `@pytest.mark.functional` (framework-wide) and `@pytest.mark.<scenario>` (scenario-specific).
- The scenario marker name matches the folder name exactly.
- Behavioral modifiers use plain descriptive names: `no_workload`, `order`.
- Register all custom markers in `pytest.ini` to avoid warnings.
