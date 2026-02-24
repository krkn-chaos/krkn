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

The script prints a line to add to `CI/tests_v2/pytest.ini` under `markers`, for example:

```
service_hijacking: marks a test as a service_hijacking scenario test
```

**Next steps after scaffolding:**

1. Add the marker to `pytest.ini` as instructed.
2. Edit `scenario_base.yaml` with the structure your Krkn scenario type expects (see `scenarios/application_outage/scenario_base.yaml` and `scenarios/pod_disruption/scenario_base.yaml` for examples).
3. In the test file, implement `_load_and_patch_scenario(repo_root, namespace, **overrides)` so it loads `scenario_base.yaml` (via `load_scenario_base(repo_root, "service_hijacking")`), patches namespace and any overrides, and returns the structure. Use `scenario_dir(repo_root, "service_hijacking")` if you need to resolve paths to other files in the folder.
4. In `test_happy_path`, write the patched scenario to `tmp_path`, call `build_config(scenario_type, scenario_path)`, run Kraken, then assert with `assert_kraken_success`, `assert_pod_count_unchanged`, and `assert_all_pods_running_and_ready`.
5. Add more test methods (e.g. negative tests with `@pytest.mark.no_workload`) as needed.
6. Adjust `resource.yaml` if your scenario needs a different workload (e.g. specific image or labels).

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
   - Import `BaseScenarioTest` from `lib.base` and helpers from `lib.utils` (including `load_scenario_base`, `scenario_dir` if needed).
   - Define a class extending `BaseScenarioTest` with:
     - `WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/<scenario_name>/resource.yaml"`
     - `WORKLOAD_IS_PATH = True`
     - `LABEL_SELECTOR = "app=<label>"`
   - Add `@pytest.mark.functional` and `@pytest.mark.<scenario>` on the class.
   - Implement a helper that loads and patches the scenario from `scenario_base.yaml`, then at least one test that builds the scenario, runs Kraken via `build_config` + `run_kraken`, and asserts with `assert_kraken_success`, `assert_pod_count_unchanged`, and `assert_all_pods_running_and_ready`.

5. **Register the marker**  
   In `CI/tests_v2/pytest.ini`, under `markers`:
   ```
   <scenario>: marks a test as a <scenario> scenario test
   ```

## Conventions

- **Folder-per-scenario**: One directory per scenario under `scenarios/`. All assets (test, resource.yaml, scenario_base.yaml, and any extra YAMLs) live there for easy tracking and onboarding.
- **Ephemeral namespace**: Every test gets a unique `krkn-test-<uuid>` namespace. The base class deploys the workload into it before the test; no manual deploy is required.
- **Negative tests**: For tests that don’t need a workload (e.g. invalid scenario, bad namespace), use `@pytest.mark.no_workload`. The test will still get a namespace but no workload will be deployed.
- **Scenario type**: The string passed to `build_config` must match the key in Kraken’s config (e.g. `application_outages_scenarios`, `pod_disruption_scenarios`). See `CI/config/common_test_config.yaml` and the scenario plugin’s `get_scenario_types()`.
- **Assertions**: Use `assert_kraken_success(result, context=f"namespace={ns}", tmp_path=tmp_path)` so failures include stdout/stderr and optional log files in `tmp_path`.
- **Timeouts**: Use constants from `lib.base` (`READINESS_TIMEOUT`, `POLICY_WAIT_TIMEOUT`, etc.) instead of magic numbers.

## Running your new tests

```bash
pytest CI/tests_v2/ -v -m <scenario>
```

For debugging with logs and keeping failed namespaces:

```bash
pytest CI/tests_v2/ -v -m <scenario> --log-cli-level=DEBUG --keep-ns-on-fail
```
