"""
Shared fixtures for pytest functional tests (CI/tests_v2).
Tests must be run from the repository root so run_kraken.py and config paths resolve.
"""

import logging
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from kubernetes import client, config, utils as k8s_utils

from lib.base import NS_CLEANUP_TIMEOUT, READINESS_TIMEOUT
from lib.utils import patch_namespace_in_docs

logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption(
        "--keep-ns-on-fail",
        action="store_true",
        default=False,
        help="Don't delete test namespaces on failure (for debugging)",
    )
    parser.addoption(
        "--require-kind",
        action="store_true",
        default=False,
        help="Skip tests unless current context is a known dev cluster (kind, minikube)",
    )


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def _kraken_cmd(config_path: str, repo_root: Path):
    return [
        "python3", "-m", "coverage", "run", "-a",
        "run_kraken.py", "-c", str(config_path),
    ]


def _repo_root() -> Path:
    """Repository root (directory containing run_kraken.py and CI/)."""
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def repo_root():
    return _repo_root()


STALE_NS_AGE_MINUTES = 30


def _namespace_age_minutes(metadata) -> float:
    """Return age of namespace in minutes from its creation_timestamp."""
    if not metadata or not metadata.creation_timestamp:
        return 0.0
    created = metadata.creation_timestamp
    if hasattr(created, "timestamp"):
        created_ts = created.timestamp()
    else:
        # RFC3339 string
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created_ts = dt.timestamp()
        except Exception:
            return 0.0
    return (time.time() - created_ts) / 60.0


def _wait_for_namespace_gone(k8s_core, name: str, timeout: int = 60):
    """Poll until the namespace no longer exists."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            k8s_core.read_namespace(name=name)
        except client.rest_api.ApiException as e:
            if e.status == 404:
                return
            raise
        time.sleep(1)
    raise TimeoutError(f"Namespace {name} did not disappear within {timeout}s")


@pytest.fixture(scope="function")
def test_namespace(request, k8s_core):
    """
    Create an ephemeral namespace for the test. Deleted after the test unless
    --keep-ns-on-fail is set and the test failed.
    """
    name = f"krkn-test-{uuid.uuid4().hex[:8]}"
    ns = client.V1Namespace(metadata=client.V1ObjectMeta(name=name))
    k8s_core.create_namespace(body=ns)
    logger.info("Created test namespace: %s", name)

    yield name

    keep_on_fail = request.config.getoption("--keep-ns-on-fail", False)
    rep_call = getattr(request.node, "rep_call", None)
    failed = rep_call is not None and rep_call.failed
    if keep_on_fail and failed:
        logger.info("[keep-ns-on-fail] Keeping namespace %s for debugging", name)
        return

    try:
        k8s_core.delete_namespace(
            name=name,
            body=client.V1DeleteOptions(propagation_policy="Foreground"),
        )
        _wait_for_namespace_gone(k8s_core, name, timeout=NS_CLEANUP_TIMEOUT)
        logger.debug("Deleted test namespace: %s", name)
    except Exception as e:
        logger.warning("Failed to delete namespace %s: %s", name, e)


@pytest.fixture(scope="function")
def deploy_workload(test_namespace, k8s_client, wait_for_pod_ready, repo_root, tmp_path):
    """
    Helper that applies a manifest into the test namespace and waits for pods.
    Yields a callable: deploy(manifest_path_or_content, label_selector, *, is_path=True)
    which applies the manifest, waits for readiness, and returns the namespace name.
    """

    def _deploy(manifest_path_or_content, label_selector, *, is_path=True, timeout=READINESS_TIMEOUT):
        try:
            if is_path:
                path = Path(manifest_path_or_content)
                if not path.is_absolute():
                    path = repo_root / path
                with open(path) as f:
                    docs = list(yaml.safe_load_all(f))
            else:
                docs = list(yaml.safe_load_all(manifest_path_or_content))
            docs = patch_namespace_in_docs(docs, test_namespace)
            k8s_utils.create_from_yaml(
                k8s_client,
                yaml_objects=docs,
                namespace=test_namespace,
            )
        except k8s_utils.FailToCreateError as e:
            msgs = [str(exc) for exc in e.api_exceptions]
            raise RuntimeError(f"Failed to create resources: {'; '.join(msgs)}") from e
        logger.info("Workload applied in namespace=%s, waiting for pods with selector=%s", test_namespace, label_selector)
        wait_for_pod_ready(test_namespace, label_selector, timeout=timeout)
        logger.info("Pods ready in namespace=%s", test_namespace)
        return test_namespace

    return _deploy


@pytest.fixture(scope="session", autouse=True)
def _configure_logging():
    """Set log format with timestamps for test runs."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )


@pytest.fixture(scope="session")
def _kube_config_loaded():
    """Load kubeconfig once per session. Skips if cluster unreachable."""
    try:
        config.load_kube_config()
        logger.info("Kube config loaded successfully")
    except config.ConfigException as e:
        logger.warning("Could not load kube config: %s", e)
        pytest.skip(f"Could not load kube config (is a cluster running?): {e}")


@pytest.fixture(scope="session")
def k8s_core(_kube_config_loaded):
    """Kubernetes CoreV1Api for pods, etc. Uses default kubeconfig."""
    return client.CoreV1Api()


@pytest.fixture(scope="session")
def k8s_networking(_kube_config_loaded):
    """Kubernetes NetworkingV1Api for network policies."""
    return client.NetworkingV1Api()


@pytest.fixture(scope="session")
def k8s_client(_kube_config_loaded):
    """Kubernetes ApiClient for create_from_yaml and other generic API calls."""
    return client.ApiClient()


@pytest.fixture(scope="session")
def k8s_apps(_kube_config_loaded):
    """Kubernetes AppsV1Api for deployment status polling."""
    return client.AppsV1Api()


@pytest.fixture(scope="session", autouse=True)
def _log_cluster_context(request):
    """Log current cluster context at session start; skip if --require-kind and not a dev cluster."""
    try:
        contexts, active = config.list_kube_config_contexts()
    except Exception as e:
        logger.warning("Could not list kube config contexts: %s", e)
        return
    if not active:
        return
    context_name = active.get("name", "?")
    cluster = (active.get("context") or {}).get("cluster", "?")
    logger.info("Running tests against cluster: context=%s cluster=%s", context_name, cluster)
    if not request.config.getoption("--require-kind", False):
        return
    cluster_lower = (cluster or "").lower()
    if "kind" in cluster_lower or "minikube" in cluster_lower:
        return
    pytest.skip(
        f"Cluster '{cluster}' does not look like kind/minikube. "
        "Use default kubeconfig or pass --require-kind only on dev clusters."
    )


@pytest.fixture(scope="session", autouse=True)
def _cleanup_stale_namespaces(k8s_core):
    """Delete krkn-test-* namespaces older than STALE_NS_AGE_MINUTES at session start."""
    try:
        namespaces = k8s_core.list_namespace()
    except Exception as e:
        logger.warning("Could not list namespaces for stale cleanup: %s", e)
        return
    for ns in namespaces.items or []:
        name = ns.metadata.name if ns.metadata else ""
        if not name.startswith("krkn-test-"):
            continue
        if _namespace_age_minutes(ns.metadata) <= STALE_NS_AGE_MINUTES:
            continue
        try:
            logger.warning("Deleting stale namespace: %s", name)
            k8s_core.delete_namespace(
                name=name,
                body=client.V1DeleteOptions(propagation_policy="Background"),
            )
        except Exception as e:
            logger.warning("Failed to delete stale namespace %s: %s", name, e)


@pytest.fixture
def kubectl(repo_root):
    """Run kubectl with given args from repo root. Returns CompletedProcess."""

    def run(args, timeout=120):
        cmd = ["kubectl"] + (args if isinstance(args, list) else list(args))
        return subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    return run


@pytest.fixture
def run_kraken(repo_root):
    """Run Kraken with the given config path. Returns CompletedProcess. Default timeout 300s."""

    def run(config_path, timeout=300, extra_args=None):
        cmd = _kraken_cmd(config_path, repo_root)
        if extra_args:
            cmd.extend(extra_args)
        return subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    return run


@pytest.fixture
def run_kraken_background(repo_root):
    """Start Kraken in background. Returns (Popen, kill_fn). Call kill_fn() or proc.terminate() to stop."""

    def start(config_path):
        cmd = _kraken_cmd(config_path, repo_root)
        proc = subprocess.Popen(
            cmd,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc

    return start


@pytest.fixture
def build_config(repo_root, tmp_path):
    """
    Build a Kraken config from common_test_config.yaml with scenario_type and scenario_file
    substituted. Disables Prometheus/Elastic checks for local runs.
    Returns the path to the written config file.
    """

    def _build(scenario_type: str, scenario_file: str, filename: str = "test_config.yaml"):
        common_path = repo_root / "CI" / "config" / "common_test_config.yaml"
        content = common_path.read_text()
        content = content.replace("$scenario_type", scenario_type)
        content = content.replace("$scenario_file", scenario_file)
        content = content.replace("$post_config", "")

        config = yaml.safe_load(content)
        # Disable monitoring that requires Prometheus/Elastic for easy local runs
        if "performance_monitoring" in config:
            config["performance_monitoring"]["check_critical_alerts"] = False
            config["performance_monitoring"]["enable_alerts"] = False
            config["performance_monitoring"]["enable_metrics"] = False
        if "elastic" in config:
            config["elastic"]["enable_elastic"] = False

        out_path = tmp_path / filename
        with open(out_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        return str(out_path)

    return _build


@pytest.fixture
def wait_for_pod_ready(k8s_core):
    """
    Poll until all matching pods are Running and all containers ready.
    Uses exponential backoff: 1s, 2s, 4s, ... capped at 10s.
    Raises TimeoutError with diagnostic details on failure.
    """

    def _wait(namespace: str, label_selector: str, timeout: int = READINESS_TIMEOUT):
        deadline = time.monotonic() + timeout
        interval = 1.0
        max_interval = 10.0
        last_list = None
        while time.monotonic() < deadline:
            try:
                pod_list = k8s_core.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector,
                )
            except Exception as e:
                time.sleep(min(interval, max_interval))
                interval = min(interval * 2, max_interval)
                continue
            last_list = pod_list
            items = pod_list.items or []
            if not items:
                time.sleep(min(interval, max_interval))
                interval = min(interval * 2, max_interval)
                continue
            all_running = all(
                (p.status and p.status.phase == "Running") for p in items
            )
            if not all_running:
                time.sleep(min(interval, max_interval))
                interval = min(interval * 2, max_interval)
                continue
            all_ready = True
            for p in items:
                if not p.status or not p.status.container_statuses:
                    all_ready = False
                    break
                for cs in p.status.container_statuses:
                    if not getattr(cs, "ready", False):
                        all_ready = False
                        break
            if all_ready:
                return
            time.sleep(min(interval, max_interval))
            interval = min(interval * 2, max_interval)

        diag = ""
        if last_list and last_list.items:
            p = last_list.items[0]
            diag = f" e.g. pod {p.metadata.name}: phase={getattr(p.status, 'phase', None)}"
        raise TimeoutError(
            f"Pods in {namespace} with label {label_selector} did not become ready within {timeout}s.{diag}"
        )

    return _wait
