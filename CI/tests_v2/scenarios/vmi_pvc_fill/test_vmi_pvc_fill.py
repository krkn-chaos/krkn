"""VMI PVC fill plugin tests using a filesystem PVC, without requiring a VMI."""

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


def _filesystem_used_kb(kubectl, namespace, pod_name):
    """Read used KiB for the test PVC mount from the workload container."""
    result = kubectl(
        ["exec", "-n", namespace, pod_name, "-c", "app", "--", "df", "-k", "/data"]
    )
    if result.returncode != 0:
        raise AssertionError(
            f"df failed in {namespace}/{pod_name}: {result.stderr}"
        )
    rows = [line.split() for line in result.stdout.splitlines() if line.strip()]
    assert len(rows) >= 2, f"Unexpected df output: {result.stdout!r}"
    return int(rows[-1][2])


def _fill_file_size(kubectl, namespace, pod_name):
    """Return current kraken.tmp size, or None if the fill file is absent."""
    result = kubectl(
        [
            "exec", "-n", namespace, pod_name, "-c", "app", "--",
            "sh", "-c", "test -s /data/kraken.tmp && stat -c %s /data/kraken.tmp",
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
@pytest.mark.vmi_pvc_fill
class TestVmiPvcFill(BaseScenarioTest):
    """Exercise the VMI PVC fill scenario's filesystem-PVC path on a Pod target."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/vmi_pvc_fill/resource.yaml"
    LABEL_SELECTOR = "app=krkn-vmi-pvc-fill-target"
    SCENARIO_NAME = "vmi_pvc_fill"
    SCENARIO_TYPE = "vmi_pvc_fill_scenarios"
    NAMESPACE_KEY_PATH = ["vmi_pvc_fill_scenario", "namespace"]
    OVERRIDES_KEY_PATH = ["vmi_pvc_fill_scenario"]

    def test_filesystem_pvc_fill_is_observable_and_cleaned(self, kubectl):
        """Verify the plugin fills the mounted PVC while keeping its Pod healthy."""
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        assert len(before.items) == 1, (
            f"Expected one PVC workload Pod, found {len(before.items)}"
        )
        pod_name = before.items[0].metadata.name
        baseline_used_kb = _filesystem_used_kb(kubectl, self.ns, pod_name)

        scenario = self.load_and_patch_scenario(
            self.repo_root,
            self.ns,
            pod_name=pod_name,
            fill_percentage=90,
            duration=15,
        )
        scenario_path = self.write_scenario(
            self.tmp_path, scenario, suffix="-filesystem-fill"
        )
        config_path = self.build_config(
            self.SCENARIO_TYPE,
            str(scenario_path),
            filename="vmi-pvc-fill-filesystem.yaml",
        )

        proc = self.run_kraken_background(config_path)
        try:
            active_size = None
            active_used_kb = None
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and proc.poll() is None:
                active_size = _fill_file_size(kubectl, self.ns, pod_name)
                if active_size:
                    active_used_kb = _filesystem_used_kb(kubectl, self.ns, pod_name)
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
                    context=f"VMI PVC fill did not become observable in {self.ns}",
                    tmp_path=self.tmp_path,
                )
                pytest.fail(
                    "VMI PVC fill completed without an observable non-empty file "
                    "and usage increase\nstdout:\n"
                    f"{stdout}\nstderr:\n{stderr}"
                )

            assert active_size > 0, "VMI PVC fill file was empty"
            assert active_used_kb > baseline_used_kb, (
                f"PVC usage did not increase: before={baseline_used_kb}KiB "
                f"after={active_used_kb}KiB"
            )

            proc.wait(timeout=180)
            stdout, stderr = proc.communicate()
            result = subprocess.CompletedProcess(
                proc.args, proc.returncode, stdout=stdout, stderr=stderr
            )
            assert_kraken_success(result, context=self.ns, tmp_path=self.tmp_path)
            assert_scenario_executed(
                result,
                self.SCENARIO_NAME,
                context=self.ns,
                tmp_path=self.tmp_path,
            )

            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if _fill_file_size(kubectl, self.ns, pod_name) is None:
                    break
                time.sleep(1)
            else:
                pytest.fail("VMI PVC fill file remained after scenario completion")

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
                        "exec", "-n", self.ns, pod_name, "-c", "app", "--",
                        "rm", "-f", "/data/kraken.tmp",
                    ],
                    timeout=30,
                )
            except Exception:
                pass
