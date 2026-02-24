"""
Preflight checks for CI/tests_v2: cluster reachability and test deps at session start.
"""

import logging
import subprocess

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def _preflight_checks(repo_root):
    """
    Verify cluster is reachable and test deps are importable at session start.
    Skips the session if cluster-info fails or required plugins are missing.
    """
    # Check test deps (pytest plugins)
    try:
        import pytest_rerunfailures  # noqa: F401
        import pytest_html  # noqa: F401
        import pytest_timeout  # noqa: F401
        import pytest_order  # noqa: F401
    except ImportError as e:
        pytest.skip(
            f"Missing test dependency: {e}. "
            "Run: pip install -r CI/tests_v2/requirements.txt"
        )

    # Check cluster reachable and log server URL
    result = subprocess.run(
        ["kubectl", "cluster-info"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        pytest.skip(
            f"Cluster not reachable (kubectl cluster-info failed). "
            f"Start a cluster (e.g. make setup) or check KUBECONFIG. stderr: {result.stderr or '(none)'}"
        )
    # Log first line of cluster-info (server URL) for debugging
    if result.stdout:
        first_line = result.stdout.strip().split("\n")[0]
        logger.info("Preflight: %s", first_line)
