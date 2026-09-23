"""Kraken daemon and PAUSE/RUN control-plane integration tests."""
import subprocess
import time
import urllib.request

import pytest
import yaml

from lib.base import BaseScenarioTest

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
        request = urllib.request.Request(f"http://127.0.0.1:18081/{value}", method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status

    def test_daemon_stop_via_status_api(self):
        """Stop a daemon-mode Kraken run through its status API."""
        proc = self.run_kraken_background(self._config(daemon=True))
        try:
            time.sleep(5)
            assert self._post("STOP") == 200
            proc.wait(timeout=60)
            assert proc.returncode == 0
        finally:
            if proc.poll() is None: proc.kill(); proc.wait()

    def test_pause_waits_then_run_signal_releases(self):
        """Release a paused Kraken run with the RUN status signal."""
        proc = self.run_kraken_background(self._config(state="PAUSE"))
        try:
            time.sleep(5)
            assert proc.poll() is None
            assert self._post("RUN") == 200
            proc.wait(timeout=120)
            assert proc.returncode == 0
        finally:
            if proc.poll() is None: proc.kill(); proc.wait()
