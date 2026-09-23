"""Credential-gated telemetry integration tests; never mutate shared config."""

import os
import re
import shutil
import subprocess

import pytest
import yaml

from lib.base import BaseScenarioTest
from lib.utils import assert_kraken_success

@pytest.mark.functional
@pytest.mark.telemetry
class TestTelemetry(BaseScenarioTest):
    """Verify telemetry artifacts uploaded for one Kraken invocation."""
    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_disruption/resource.yaml"
    LABEL_SELECTOR = "app=krkn-pod-disruption-target"
    SCENARIO_NAME = "pod_disruption"
    SCENARIO_TYPE = "pod_disruption_scenarios"
    NAMESPACE_KEY_PATH = [0, "config", "namespace_pattern"]
    NAMESPACE_IS_REGEX = True

    @pytest.mark.skipif(not os.getenv("AWS_BUCKET"), reason="AWS_BUCKET is not configured")
    @pytest.mark.skipif(shutil.which("aws") is None, reason="aws CLI is unavailable")
    def test_telemetry_uploads_core_artifacts(self):
        """Require core artifacts under this run's unique telemetry request prefix."""
        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        sf = self.write_scenario(self.tmp_path, scenario, suffix="-telemetry")
        data = yaml.safe_load((self.repo_root / "CI/tests_v2/config/common_test_config.yaml").read_text())
        data["kraken"]["chaos_scenarios"][0] = {self.SCENARIO_TYPE: [str(sf)]}
        data["telemetry"].update({"enabled": True, "full_prometheus_backup": True, "run_tag": f"pytest-{self.ns}"})
        data["telemetry"]["username"] = os.getenv("TELEMETRY_USERNAME", "")
        data["telemetry"]["password"] = os.getenv("TELEMETRY_PASSWORD", "")
        data["performance_monitoring"].update({"check_critical_alerts": False, "enable_alerts": False, "enable_metrics": False})
        path = self.tmp_path / "telemetry.yaml"; path.write_text(yaml.safe_dump(data))
        result = self.run_kraken(str(path), timeout=300)
        assert_kraken_success(result, context="telemetry", tmp_path=self.tmp_path)

        output = (result.stdout or "") + "\n" + (result.stderr or "")
        request_match = re.search(
            r"telemetry data will be stored on s3 bucket folder: "
            r".*/files/([^/\s]+)/([^\s]+)",
            output,
        )
        assert request_match, "Kraken did not log the telemetry request prefix"
        group, request_id = request_match.groups()
        listing = subprocess.run(
            [
                "aws",
                "s3",
                "ls",
                f"s3://{os.environ['AWS_BUCKET']}/{group}/{request_id}/",
                "--recursive",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert listing.returncode == 0, listing.stderr
        for artifact in ("prometheus-00.tar", "telemetry.json"):
            assert artifact in listing.stdout, (
                f"Missing telemetry artifact {artifact} for request {request_id}"
            )
