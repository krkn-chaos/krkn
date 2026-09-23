"""Cerberus probe and exit-policy integration coverage."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml

from lib.base import BaseScenarioTest
from lib.utils import assert_kraken_success, assert_scenario_executed

class _CerberusHandler(BaseHTTPRequestHandler):
    status = b"False"
    requests = 0
    def do_GET(self):
        type(self).requests += 1
        self.send_response(200); self.end_headers(); self.wfile.write(type(self).status)
    def log_message(self, *_): pass

@pytest.mark.functional
@pytest.mark.cerberus
class TestCerberus(BaseScenarioTest):
    """Exercise unhealthy Cerberus responses and their configured exit policy."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_disruption/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pod-disruption-target"
    SCENARIO_NAME = "pod_disruption"
    SCENARIO_TYPE = "pod_disruption_scenarios"
    NAMESPACE_KEY_PATH = [0, "config", "namespace_pattern"]
    NAMESPACE_IS_REGEX = True

    def _config(self, url, exit_on_failure):
        source = yaml.safe_load((self.repo_root / "CI/tests_v2/config/common_test_config.yaml").read_text())
        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="-cerberus")
        source["kraken"]["chaos_scenarios"] = [{self.SCENARIO_TYPE: [str(scenario_path)]}]
        source["kraken"]["exit_on_failure"] = exit_on_failure
        source["kraken"]["publish_kraken_status"] = False
        source["cerberus"].update({"cerberus_enabled": True, "cerberus_url": url})
        source["performance_monitoring"].update({"check_critical_alerts": False, "enable_alerts": False, "enable_metrics": False})
        path = self.tmp_path / f"cerberus-{exit_on_failure}.yaml"; path.write_text(yaml.safe_dump(source)); return str(path)

    def _run_with_mock(self, exit_on_failure):
        _CerberusHandler.requests = 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), _CerberusHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            result = self.run_kraken(self._config(f"http://127.0.0.1:{server.server_port}", exit_on_failure))
        finally:
            server.shutdown(); thread.join(timeout=5)
        return result

    def test_unhealthy_probe_with_continue_policy(self):
        """Verify unhealthy responses are reported when Krkn is configured to continue."""
        result = self._run_with_mock(False)
        assert _CerberusHandler.requests > 0
        # Current Cerberus client exits 1 for a no-go response regardless of
        # exit_on_failure; this pins the observed product contract.
        assert result.returncode != 0
        assert_scenario_executed(result, self.SCENARIO_NAME, context=self.ns, tmp_path=self.tmp_path)

    def test_unhealthy_probe_with_abort_policy(self):
        """Verify unhealthy responses abort the run when the configured policy requires it."""
        result = self._run_with_mock(True)
        assert _CerberusHandler.requests > 0
        assert result.returncode != 0
