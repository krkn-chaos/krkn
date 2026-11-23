"""Cerberus unhealthy-probe integration coverage.

The healthy-path truth table (healthy + exit_on_failure combinations) is
exhaustively unit-pinned in tests/test_cerberus_setup.py:164-218, including
the KRKN-003 defect semantics, so only the unhealthy path — whose value is
proving subprocess exit-code propagation through the real run_kraken wiring
(set_url -> abstract_scenario_plugin cerberus check -> sys.exit(1)) — is
kept here.
"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml

from lib.base import BaseScenarioTest
from lib.utils import assert_scenario_executed


class _CerberusHandler(BaseHTTPRequestHandler):
    status = b"False"
    requests = 0

    def do_GET(self):
        type(self).requests += 1
        self.send_response(200)
        self.end_headers()
        self.wfile.write(type(self).status)

    def log_message(self, *_):
        pass


@pytest.mark.functional
@pytest.mark.cerberus
class TestCerberus(BaseScenarioTest):
    """Exercise the Cerberus unhealthy gate end to end."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_disruption/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pod-disruption-target"
    SCENARIO_NAME = "pod_disruption"
    SCENARIO_TYPE = "pod_disruption_scenarios"
    NAMESPACE_KEY_PATH = [0, "config", "namespace_pattern"]
    NAMESPACE_IS_REGEX = True

    def _config(self, url):
        source = yaml.safe_load(
            (self.repo_root / "CI/tests_v2/config/common_test_config.yaml").read_text()
        )
        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix="-cerberus")
        source["kraken"]["chaos_scenarios"] = [
            {self.SCENARIO_TYPE: [str(scenario_path)]}
        ]
        # exit_on_failure is False here, but the unhealthy gate is
        # unconditional: krkn/cerberus/setup.py get_status() sys.exit(1)s on
        # an unhealthy response regardless of the flag (KRKN-003 documents
        # that the continue-policy branch is unreachable dead code).
        source["kraken"]["exit_on_failure"] = False
        source["kraken"]["publish_kraken_status"] = False
        source["cerberus"].update({"cerberus_enabled": True, "cerberus_url": url})
        source["performance_monitoring"].update(
            {
                "check_critical_alerts": False,
                "enable_alerts": False,
                "enable_metrics": False,
            }
        )
        path = self.tmp_path / "cerberus-unhealthy.yaml"
        path.write_text(yaml.safe_dump(source))
        return str(path)

    def test_unhealthy_probe_reports_health_failure(self):
        """An unhealthy Cerberus response makes kraken exit with code 1.

        The exact code is asserted (not just != 0) because the unhealthy
        path exits via sys.exit(1) from krkn/cerberus/setup.py, bypassing
        run_kraken's exit-code ladder (KRKN-003); rc 2/3/4 would indicate a
        different failure mode.
        """
        _CerberusHandler.requests = 0
        _CerberusHandler.status = b"False"
        server = ThreadingHTTPServer(("127.0.0.1", 0), _CerberusHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = self.run_kraken(
                self._config(f"http://127.0.0.1:{server.server_port}")
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)
        assert _CerberusHandler.requests > 0
        assert_scenario_executed(
            result, self.SCENARIO_NAME, context=self.ns, tmp_path=self.tmp_path
        )
        assert result.returncode == 1
