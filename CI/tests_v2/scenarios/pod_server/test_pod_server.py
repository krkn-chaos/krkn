"""Kraken daemon and PAUSE/RUN control-plane integration tests."""
import subprocess
import time
import urllib.error
import urllib.request

import pytest
import yaml

from lib.base import BaseScenarioTest
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_success,
    assert_scenario_executed,
    get_pods_list,
    pod_uids,
)


@pytest.mark.functional
@pytest.mark.pod_server
@pytest.mark.xdist_group("pod_server")
class TestPodServer(BaseScenarioTest):
    """Exercise Kraken daemon and PAUSE/RUN status-server controls."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_disruption/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pod-disruption-target"
    SCENARIO_NAME = "pod_disruption"
    SCENARIO_TYPE = "pod_disruption_scenarios"
    NAMESPACE_KEY_PATH = [0, "config", "namespace_pattern"]
    NAMESPACE_IS_REGEX = True

    def _config(self, state="RUN", daemon=False):
        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        sf = self.write_scenario(self.tmp_path, scenario, suffix=f"-{state}-{daemon}")
        data = yaml.safe_load((self.repo_root / "CI/tests_v2/config/common_test_config.yaml").read_text())
        data["kraken"].update({"signal_state": state, "publish_kraken_status": True, "port": 18081, "signal_address": "127.0.0.1", "exit_on_failure": False})
        data["kraken"]["chaos_scenarios"][0] = {self.SCENARIO_TYPE: [str(sf)]}
        data["tunings"]["daemon_mode"] = daemon
        data["performance_monitoring"].update({"check_critical_alerts": False, "enable_alerts": False, "enable_metrics": False})
        path = self.tmp_path / f"server-{state}-{daemon}.yaml"; path.write_text(yaml.safe_dump(data)); return str(path)

    def _post(self, value):
        """Poll the status endpoint until the daemon has finished binding."""
        request = urllib.request.Request(f"http://127.0.0.1:18081/{value}", method="POST")
        deadline = time.monotonic() + 30
        last_error = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.status
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = error
                time.sleep(1)
        raise AssertionError(f"Status endpoint did not accept {value} within 30s: {last_error}")

    @staticmethod
    def _completed(proc, timeout):
        proc.wait(timeout=timeout)
        stdout, stderr = proc.communicate()
        return subprocess.CompletedProcess(
            proc.args, proc.returncode, stdout=stdout, stderr=stderr
        )

    def test_daemon_stop_via_status_api(self):
        """Stop a daemon-mode Kraken run through its status API."""
        proc = self.run_kraken_background(self._config(daemon=True))
        try:
            time.sleep(5)
            assert self._post("STOP") == 200
            result = self._completed(proc, timeout=60)
            assert_kraken_success(result, context="daemon STOP", tmp_path=self.tmp_path)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def test_pause_waits_then_run_signal_releases(self):
        """Prove PAUSE prevents disruption and RUN releases it into pod recovery."""
        before = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
        assert before.items, "Expected a pod-disruption target before starting PAUSE"
        before_uids = set(pod_uids(before))
        proc = self.run_kraken_background(self._config(state="PAUSE"))
        try:
            time.sleep(5)
            assert proc.poll() is None
            paused = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
            assert set(pod_uids(paused)) == before_uids, "PAUSE allowed disruption before RUN"
            assert self._post("RUN") == 200
            result = self._completed(proc, timeout=120)
            assert_kraken_success(result, context="RUN signal", tmp_path=self.tmp_path)
            assert_scenario_executed(
                result, self.SCENARIO_NAME, context=f"RUN namespace={self.ns}", tmp_path=self.tmp_path
            )
            output = f"{result.stdout or ''}\n{result.stderr or ''}"
            pause_index = output.find("Pausing Kraken run")
            delete_index = output.lower().find("deleting pod")
            assert pause_index >= 0 and delete_index > pause_index, (
                "Pod disruption evidence was not emitted after the PAUSE interval"
            )

            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                after = get_pods_list(self.k8s_core, self.ns, self.LABEL_SELECTOR)
                if set(pod_uids(after)) != before_uids:
                    break
                time.sleep(1)
            else:
                pytest.fail("RUN released Kraken but no pod disruption/replacement was observed")
            assert_all_pods_running_and_ready(after, namespace=self.ns)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
