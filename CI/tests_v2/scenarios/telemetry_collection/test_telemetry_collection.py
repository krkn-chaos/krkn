"""
Functional tests for telemetry collection / S3 upload.
Migrated from CI/tests/test_telemetry.sh.

Happy-path tests share one Krkn run (class cache) so we don't burn six full chaos runs
to assert six facets of the same upload.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import boto3
import pytest
import yaml
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from lib.base import BaseScenarioTest
from lib.utils import assert_kraken_success

# Live telemetry endpoint is NOT hardcoded — set TELEMETRY_API_URL explicitly
# (CI / maintainers). Skipping when unset avoids accidental POSTs to a shared Lambda.
# Krkn has no `bucket:` config key; upload goes through the telemetry API + presigned URLs.
# Unreachable host stands in for "nonexistent bucket" / unreachable storage backend.
UNREACHABLE_TELEMETRY_API_URL = "https://nonexistent-bucket-xyz.invalid"
RUN_TAG = "funtest-telemetry"
AWS_REQUIRED = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
    "AWS_BUCKET",
)
TELEMETRY_REQUIRED = ("TELEMETRY_USERNAME", "TELEMETRY_PASSWORD", "TELEMETRY_API_URL")


def telemetry_api_url() -> str:
    return (os.environ.get("TELEMETRY_API_URL") or "").rstrip("/")


def _missing(names: tuple[str, ...]) -> list[str]:
    return [n for n in names if not os.environ.get(n)]


def require_aws_env() -> None:
    """Skip when AWS verification credentials / bucket are not available."""
    missing = _missing(AWS_REQUIRED)
    if missing:
        pytest.skip(f"AWS env vars not set: {', '.join(missing)}")


def require_telemetry_creds() -> None:
    """Skip unless username, password, and TELEMETRY_API_URL are all set."""
    missing = _missing(TELEMETRY_REQUIRED)
    if missing:
        pytest.skip(f"Telemetry credentials/endpoint not set: {', '.join(missing)}")


_S3_FOLDER_RE = re.compile(
    r"telemetry data will be stored on s3 bucket folder:\s*https://\S+/files/(\S+)"
)
_UUID_RE = re.compile(
    r"(?:Generated a uuid for the run|Using the uuid defined by the user for the run):\s*"
    r"([0-9a-fA-F-]{36})"
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def parse_s3_folder(kraken_output: str) -> str:
    """Extract `{group}/{request_id}` from the telemetry S3 folder log line."""
    clean = _strip_ansi(kraken_output)
    match = _S3_FOLDER_RE.search(clean)
    if not match:
        raise AssertionError(
            "Could not find telemetry S3 folder URL in Krkn output "
            "(expected 'telemetry data will be stored on s3 bucket folder: …/files/…')."
        )
    return match.group(1).rstrip("/")


def parse_run_uuid(kraken_output: str) -> str:
    match = _UUID_RE.search(_strip_ansi(kraken_output))
    if not match:
        raise AssertionError("Could not find run_uuid in Krkn output")
    return match.group(1)


def list_s3_filenames(folder: str, *, bucket: Optional[str] = None) -> set[str]:
    """List object basenames under s3://{bucket}/{folder}/. Raises with a clear error on failure."""
    bucket = bucket or os.environ["AWS_BUCKET"]
    region = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
    client = boto3.client("s3", region_name=region)
    prefix = folder.rstrip("/") + "/"
    try:
        resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    except NoCredentialsError as e:
        raise AssertionError(
            f"AWS credentials missing while listing s3://{bucket}/{prefix}: {e}"
        ) from e
    except (ClientError, BotoCoreError) as e:
        raise AssertionError(
            f"S3 unreachable or list failed for s3://{bucket}/{prefix}: {e}"
        ) from e
    return {obj["Key"].rsplit("/", 1)[-1] for obj in resp.get("Contents") or []}


def _patch_config(config_path: str, mutator) -> None:
    path = Path(config_path)
    cfg = yaml.safe_load(path.read_text())
    mutator(cfg)
    path.write_text(yaml.dump(cfg, default_flow_style=False, sort_keys=False))


def enable_telemetry(cfg: dict, *, enabled: bool = True, api_url: Optional[str] = None) -> None:
    """Enable telemetry upload settings on a config produced by build_config."""
    tel = cfg.setdefault("telemetry", {})
    tel["enabled"] = enabled
    if not enabled:
        return
    url = (api_url if api_url is not None else telemetry_api_url()).rstrip("/")
    if not url:
        raise AssertionError(
            "TELEMETRY_API_URL is unset; refusing to enable telemetry without an explicit endpoint"
        )
    tel["api_url"] = url
    tel["username"] = os.environ.get("TELEMETRY_USERNAME", "")
    tel["password"] = os.environ.get("TELEMETRY_PASSWORD", "")
    tel["full_prometheus_backup"] = True
    tel["prometheus_backup"] = True
    tel["run_tag"] = RUN_TAG
    # ponytail: max_retries=3 (config 0 = retry forever). Raise if uploads flake under load.
    tel["max_retries"] = 3
    perf = cfg.setdefault("performance_monitoring", {})
    # build_config forces check_critical_alerts=False; override so prometheus_plugin.critical_alerts
    # can fill ChaosRunAlertSummary and put_critical_alerts can upload critical-alerts-*.log
    # (queries ALERTS{severity="critical"} — not enable_alerts / alert_profile).
    perf["check_critical_alerts"] = True
    perf["prometheus_url"] = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")


@pytest.mark.functional
@pytest.mark.telemetry_collection
class TestTelemetryCollection(BaseScenarioTest):
    """Telemetry upload to S3 via the telemetry API (legacy test_telemetry.sh)."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/telemetry_collection/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "app=krkn-telemetry-target"
    SCENARIO_NAME = "telemetry_collection"
    SCENARIO_TYPE = "pod_disruption_scenarios"
    NAMESPACE_KEY_PATH = [0, "config", "namespace_pattern"]
    NAMESPACE_IS_REGEX = True

    _upload: Optional[dict] = None

    @pytest.fixture(scope="class", autouse=True)
    def _reset_upload_cache(self):
        """Keep the shared happy-path cache scoped to one class execution (reruns / re-runs)."""
        type(self)._upload = None
        yield
        type(self)._upload = None

    def _write_telemetry_config(self, *, suffix: str, mutator) -> str:
        scenario = self.load_and_patch_scenario(self.repo_root, self.ns)
        scenario_path = self.write_scenario(self.tmp_path, scenario, suffix=suffix)
        config_path = self.build_config(
            self.SCENARIO_TYPE,
            str(scenario_path),
            filename=f"telemetry{suffix}.yaml",
        )
        _patch_config(config_path, mutator)
        return config_path

    def _run_telemetry_upload(self) -> dict:
        """Run Krkn once with telemetry enabled; cache result for sibling happy-path asserts."""
        if TestTelemetryCollection._upload is not None:
            return TestTelemetryCollection._upload

        require_aws_env()
        require_telemetry_creds()

        config_path = self._write_telemetry_config(
            suffix="_upload",
            mutator=enable_telemetry,
        )

        if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
            pytest.skip("KRKN_TEST_DRY_RUN=1: skipping live telemetry upload")

        result = self.run_kraken(config_path)
        # 0 = success; 2 = critical alerts still firing (legacy bash mapped 2→0).
        # check_critical_alerts must stay on so critical-alerts-*.log is uploaded.
        assert_kraken_success(
            result,
            allowed_codes=(0, 2),
            context=f"namespace={self.ns}",
            tmp_path=self.tmp_path,
        )
        combined = f"{result.stdout or ''}\n{result.stderr or ''}"
        folder = parse_s3_folder(combined)
        run_uuid = parse_run_uuid(combined)
        files = list_s3_filenames(folder)
        TestTelemetryCollection._upload = {
            "result": result,
            "folder": folder,
            "run_uuid": run_uuid,
            "files": files,
            "combined": combined,
        }
        return TestTelemetryCollection._upload

    # --- Happy path (shared upload) -------------------------------------------------
    # Only order(1) deploys a workload; 2–6 read the class-scoped _upload cache (no_workload).

    @pytest.mark.order(1)
    def test_kraken_exits_cleanly_with_telemetry(self):
        """Krkn runs with telemetry enabled, collects data, exits 0 (or 2 if alerts fire)."""
        upload = self._run_telemetry_upload()
        assert upload["result"].returncode in (0, 2)

    @pytest.mark.order(2)
    @pytest.mark.no_workload
    def test_run_uuid_generated_and_embedded(self):
        """Run UUID and run_tag are generated and embedded in the telemetry folder path."""
        upload = self._run_telemetry_upload()
        assert upload["run_uuid"]
        assert upload["run_uuid"] in upload["folder"], (
            f"run_uuid {upload['run_uuid']} not embedded in S3 folder {upload['folder']}"
        )
        assert RUN_TAG in upload["folder"], (
            f"run_tag {RUN_TAG!r} not embedded in S3 folder {upload['folder']}"
        )

    @pytest.mark.order(3)
    @pytest.mark.no_workload
    def test_critical_alerts_log_uploaded(self):
        """critical-alerts-00.log is present under the run folder in S3 (legacy hard-fail)."""
        upload = self._run_telemetry_upload()
        assert any(f.startswith("critical-alerts-") and f.endswith(".log") for f in upload["files"]), (
            f"critical-alerts-*.log not in s3://$AWS_BUCKET/{upload['folder']}/: {sorted(upload['files'])}. "
            "Ensure Prometheus is reachable and check_critical_alerts collected a non-empty summary "
            "(krkn-lib skips the upload when chaos_alerts and post_chaos_alerts are both empty)."
        )

    @pytest.mark.order(4)
    @pytest.mark.no_workload
    def test_prometheus_archive_uploaded(self):
        """prometheus-00.tar archive is present under the run folder in S3."""
        upload = self._run_telemetry_upload()
        assert any(f.startswith("prometheus-") and f.endswith(".tar") for f in upload["files"]), (
            f"prometheus-*.tar not in s3://$AWS_BUCKET/{upload['folder']}/: {sorted(upload['files'])}"
        )

    @pytest.mark.order(5)
    @pytest.mark.no_workload
    def test_telemetry_json_uploaded(self):
        """telemetry.json metadata is present under the run folder in S3."""
        upload = self._run_telemetry_upload()
        assert "telemetry.json" in upload["files"], (
            f"telemetry.json not in s3://$AWS_BUCKET/{upload['folder']}/: {sorted(upload['files'])}"
        )

    @pytest.mark.order(6)
    @pytest.mark.no_workload
    def test_artifacts_under_expected_s3_folder(self):
        """Uploaded objects live under telemetry_group / request_id folder structure."""
        upload = self._run_telemetry_upload()
        parts = upload["folder"].split("/")
        assert len(parts) >= 2, f"Expected group/request_id folder, got {upload['folder']!r}"
        assert parts[0] == "funtests", f"Expected telemetry_group 'funtests', got {parts[0]!r}"
        assert upload["run_uuid"] in parts[1]
        assert RUN_TAG in parts[1]
        assert upload["files"], f"No objects under s3 folder {upload['folder']}"

    # --- Failure / skip modes (exercise Krkn, not helpers alone) --------------------

    def test_missing_aws_credentials_handled(self, monkeypatch):
        """Krkn handles missing AWS_* gracefully (no crash); telemetry uses API auth, not AWS keys."""
        require_telemetry_creds()
        for name in AWS_REQUIRED:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)

        config_path = self._write_telemetry_config(
            suffix="_no_aws",
            mutator=enable_telemetry,
        )
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
            pytest.skip("KRKN_TEST_DRY_RUN=1")

        result = self.run_kraken(config_path)
        combined = _strip_ansi(f"{result.stdout or ''}\n{result.stderr or ''}")
        assert result.returncode == 0, (
            f"Krkn should exit 0 without AWS env vars (telemetry uses API creds), "
            f"got rc={result.returncode}.\n--- stderr ---\n{result.stderr or '(empty)'}"
        )
        assert "Traceback (most recent call last)" not in combined
        # Upload may succeed via telemetry API, or log a clear failure — either is graceful.
        assert (
            "telemetry data will be stored on s3 bucket folder:" in combined
            or "failed to send telemetry data:" in combined
            or "skipping telemetry upload" in combined
        ), "Expected an explicit telemetry success/skip/error log from Krkn"

    def test_unreachable_s3_bucket_fails_explicitly(self):
        """Krkn logs an explicit telemetry/storage failure when the upload backend is unreachable.

        Krkn has no `bucket:` setting; storage is behind telemetry.api_url (presigned S3).
        Pointing api_url at a nonexistent host is the config-level equivalent of a bad bucket.
        """
        require_telemetry_creds()

        def _mutator(cfg: dict) -> None:
            enable_telemetry(cfg, api_url=UNREACHABLE_TELEMETRY_API_URL)
            cfg["telemetry"]["max_retries"] = 1
            # Avoid a long prometheus archive attempt against a dead API.
            cfg["telemetry"]["prometheus_backup"] = False

        config_path = self._write_telemetry_config(suffix="_bad_bucket", mutator=_mutator)
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
            pytest.skip("KRKN_TEST_DRY_RUN=1")

        result = self.run_kraken(config_path)
        combined = _strip_ansi(f"{result.stdout or ''}\n{result.stderr or ''}")
        assert "failed to send telemetry data:" in combined, (
            "Expected Krkn to log an explicit telemetry upload failure for unreachable storage.\n"
            f"--- output (last 40 lines) ---\n" + "\n".join(combined.splitlines()[-40:])
        )
        # Must not hang/crash with an unhandled traceback; scenario itself should still complete.
        assert "Traceback (most recent call last)" not in combined
        assert result.returncode == 0, (
            f"Telemetry upload failure should be logged without failing the scenario "
            f"(got rc={result.returncode})"
        )

    def test_telemetry_disabled_skips_upload(self):
        """With telemetry disabled, Krkn does not crash and skips the upload."""
        config_path = self._write_telemetry_config(
            suffix="_disabled",
            mutator=lambda cfg: enable_telemetry(cfg, enabled=False),
        )
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
            pytest.skip("KRKN_TEST_DRY_RUN=1")

        result = self.run_kraken(config_path)
        assert_kraken_success(result, context="telemetry disabled", tmp_path=self.tmp_path)
        combined = _strip_ansi(f"{result.stdout or ''}\n{result.stderr or ''}")
        assert "skipping telemetry upload" in combined, (
            "Expected skip-upload log when telemetry is disabled"
        )
        assert "telemetry data will be stored on s3 bucket folder:" not in combined

    @pytest.mark.no_workload
    def test_skip_when_aws_env_not_set(self, monkeypatch):
        """Happy-path upload path skips cleanly when AWS env vars are absent (not a hard fail)."""
        type(self)._upload = None  # don't return a prior happy-path cache
        for name in AWS_REQUIRED:
            monkeypatch.delenv(name, raising=False)
        with pytest.raises(pytest.skip.Exception, match="AWS env vars not set"):
            self._run_telemetry_upload()

    def test_missing_prometheus_endpoint_handled(self):
        """Missing / bad Prometheus endpoint is handled without crashing Krkn."""
        require_telemetry_creds()

        def _mutator(cfg: dict) -> None:
            enable_telemetry(cfg, enabled=True)
            cfg["performance_monitoring"]["prometheus_url"] = "http://127.0.0.1:1"
            cfg["telemetry"]["prometheus_pod_name"] = "prometheus-does-not-exist"
            cfg["telemetry"]["prometheus_namespace"] = "does-not-exist"

        config_path = self._write_telemetry_config(suffix="_noprom", mutator=_mutator)
        if os.environ.get("KRKN_TEST_DRY_RUN", "0") == "1":
            pytest.skip("KRKN_TEST_DRY_RUN=1")

        result = self.run_kraken(config_path)
        assert_kraken_success(
            result,
            allowed_codes=(0,),
            context="missing prometheus endpoint",
            tmp_path=self.tmp_path,
        )
