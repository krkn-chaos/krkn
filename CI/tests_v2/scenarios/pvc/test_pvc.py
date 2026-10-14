"""PVC fill lifecycle and failure-mode integration tests."""
import subprocess
import time

import pytest

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_success,
    assert_scenario_executed,
    get_pods_list,
)


def _df_used_kb(kubectl, namespace, pod_name):
    """Read the mounted filesystem's used KiB through the target container."""
    result = kubectl(
        ["exec", "-n", namespace, pod_name, "-c", "app", "--", "df", "-k", "/data"]
    )
    if result.returncode != 0:
        raise AssertionError(f"df failed in {namespace}/{pod_name}: {result.stderr}")
    rows = [line.split() for line in result.stdout.splitlines() if line.strip()]
    assert len(rows) >= 2, f"Unexpected df output: {result.stdout!r}"
    return int(rows[-1][2])


def _temp_file_size(kubectl, namespace, pod_name):
    """Return kraken.tmp size in bytes, or None while the temporary file is absent."""
    result = kubectl(
        [
            "exec",
            "-n",
            namespace,
            pod_name,
            "-c",
            "app",
            "--",
            "sh",
            "-c",
            "test -s /data/kraken.tmp && stat -c %s /data/kraken.tmp",
        ]
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


@pytest.mark.functional
@pytest.mark.xdist_group("node-resource-chaos")
@pytest.mark.pvc
class TestPVC(BaseScenarioTest):
    """Validate PVC fill effects and workload health (missing-claim failure is unit-covered)."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pvc/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pvc-target"
    SCENARIO_NAME = "pvc"
    SCENARIO_TYPE = "pvc_scenarios"
    NAMESPACE_KEY_PATH = ["pvc_scenario", "namespace"]
    OVERRIDES_KEY_PATH = ["pvc_scenario"]

    def test_fill_keeps_target_pod_healthy(self, kubectl):
        """Observe a non-empty fill file during chaos and its removal during rollback."""
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        assert len(before.items) == 1, f"Expected one PVC workload pod, found {len(before.items)}"
        pod_name = before.items[0].metadata.name
        baseline_used_kb = _df_used_kb(kubectl, self.ns, pod_name)

        # fill_percentage must exceed the current usage of whatever backs the
        # PVC (the plugin refuses targets below current fill). The default
        # local-path provisioner backs the PV with the node disk, whose
        # baseline usage varies by runner (observed 57.56% on a GHA runner),
        # so 90 keeps the target above any plausible baseline while staying
        # under the plugin's 99 cap. The assertions prove the fill via the
        # file's existence and the df usage delta, not the absolute target.
        scenario = self.load_and_patch_scenario(
            self.repo_root, self.ns, fill_percentage=90, duration=15
        )
        path = self.write_scenario(self.tmp_path, scenario, suffix="-active-fill")
        config_path = self.build_config(
            self.SCENARIO_TYPE, str(path), filename="active-fill.yaml"
        )
        proc = self.run_kraken_background(config_path)
        try:
            active_size = None
            active_used_kb = None
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and proc.poll() is None:
                active_size = _temp_file_size(kubectl, self.ns, pod_name)
                if active_size:
                    active_used_kb = _df_used_kb(kubectl, self.ns, pod_name)
                    if active_used_kb > baseline_used_kb:
                        break
                time.sleep(1)
            if not active_size or not active_used_kb or active_used_kb <= baseline_used_kb:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=20)
                stdout, stderr = proc.communicate()
                result = subprocess.CompletedProcess(
                    proc.args, proc.returncode, stdout=stdout, stderr=stderr
                )
                assert_kraken_success(
                    result,
                    context=f"PVC fill ended before demonstrating active usage namespace={self.ns}",
                    tmp_path=self.tmp_path,
                )
                pytest.fail(
                    f"PVC scenario exited successfully without a non-empty fill and increased usage\n"
                    f"stdout:\n{stdout}\nstderr:\n{stderr}"
                )
            assert active_size and active_size > 0, "PVC scenario never created non-empty kraken.tmp"
            assert active_used_kb and active_used_kb > baseline_used_kb, (
                f"PVC usage did not increase while fill was active: "
                f"before={baseline_used_kb}KiB after={active_used_kb}KiB"
            )

            proc.wait(timeout=120)
            stdout, stderr = proc.communicate()
            result = subprocess.CompletedProcess(
                proc.args, proc.returncode, stdout=stdout, stderr=stderr
            )
            assert_kraken_success(result, context=self.ns, tmp_path=self.tmp_path)
            # Execution-evidence gate (SCENARIO_EXECUTION_MARKERS["pvc"]):
            # "Creating kraken.tmp file|Finish waiting". Both branches are
            # unconditional on the success path, so the OR-marker is
            # equivalent to the previous AND-substring pair; the live
            # df/file polling above carries the primary proof.
            assert_scenario_executed(
                result, self.SCENARIO_NAME, context=self.ns, tmp_path=self.tmp_path
            )

            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if _temp_file_size(kubectl, self.ns, pod_name) is None:
                    break
                time.sleep(1)
            else:
                pytest.fail("PVC temporary fill file remained after scenario completion")
            after = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
            assert_all_pods_running_and_ready(after, namespace=self.ns)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=20)
            try:
                kubectl(
                    [
                        "exec",
                        "-n",
                        self.ns,
                        pod_name,
                        "-c",
                        "app",
                        "--",
                        "rm",
                        "-f",
                        "/data/kraken.tmp",
                    ],
                    timeout=30,
                )
            except Exception:
                pass
