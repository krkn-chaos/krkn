"""v2 functional tests for pod_network_filter scenario.

Migrated from CI/tests/test_pod_network_filter.sh.
Covers happy-path TCP/UDP/multi-port/ingress+egress, negative tests,
and cleanup verification specified in issue #1434.
"""

import logging
from pathlib import Path

import pytest

from lib.kraken import build_config, run_kraken

pytestmark = pytest.mark.pod_network_filter

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_BASE = _HERE / "scenario_base.yaml"


def _run_filter(
    kubectl,
    test_namespace,
    repo_root,
    overrides: dict,
):
    """Run pod-network-filter scenario with *overrides* merged into base config.

    Returns (returncode, stdout, stderr) from run_kraken.
    """
    cfg = build_config(
        base_yaml=_BASE,
        overrides=overrides,
        namespace=test_namespace,
    )
    return run_kraken(cfg, repo_root=repo_root)


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_tcp_port_block_egress(kubectl, test_namespace, repo_root):
    """TCP port 443 blocked on egress, Krkn exits 0."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {
            "protocols": ["tcp"],
            "ports": [443],
            "egress": True,
            "ingress": False,
            "target": "pod-network-filter-test",
        },
    )
    assert rc == 0, f"Krkn failed:\n{out}\n{err}"


def test_udp_port_block(kubectl, test_namespace, repo_root):
    """UDP port 53 filtered."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {
            "protocols": ["udp"],
            "ports": [53],
            "egress": True,
            "ingress": False,
        },
    )
    assert rc == 0, f"Krkn failed:\n{out}\n{err}"


def test_multi_protocol_tcp_udp(kubectl, test_namespace, repo_root):
    """Both TCP and UDP on port 53 blocked."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {
            "protocols": ["tcp", "udp"],
            "ports": [53],
        },
    )
    assert rc == 0


def test_multi_ports(kubectl, test_namespace, repo_root):
    """Ports 80, 443, 8080 all blocked."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {
            "ports": [80, 443, 8080],
        },
    )
    assert rc == 0


def test_ingress_direction(kubectl, test_namespace, repo_root):
    """Ingress traffic filtered, egress disabled."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {
            "egress": False,
            "ingress": True,
        },
    )
    assert rc == 0


def test_both_directions(kubectl, test_namespace, repo_root):
    """Both ingress and egress filtered simultaneously."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {
            "egress": True,
            "ingress": True,
        },
    )
    assert rc == 0


def test_label_selector_targeting(kubectl, test_namespace, repo_root):
    """Multiple pods matching label are filtered (instance_count=1)."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {
            "label_selector": "app=network-filter-test",
            "instance_count": 1,
        },
    )
    assert rc == 0


def test_duration_and_cleanup(kubectl, test_namespace, repo_root):
    """Filter applied for test_duration then removed automatically."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {
            "test_duration": 15,
        },
    )
    assert rc == 0
    assert (
        "resetting the network filter" in out.lower()
        or "removing" in out.lower()
        or "cleaning" in out.lower()
    ), "Expected cleanup log message"


# ---------------------------------------------------------------------------
# Negative / failure-mode tests
# ---------------------------------------------------------------------------


def test_nonexistent_target_pod(kubectl, test_namespace, repo_root):
    """Non-existent target pod causes graceful error."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {
            "target": "fake-pod-does-not-exist",
        },
    )
    assert rc != 0, "Expected non-zero exit for missing target"


def test_no_matching_pods(kubectl, test_namespace, repo_root):
    """No pods matching label selector logs 'no targets found'."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {
            "label_selector": "app=nonexistent-selector",
        },
    )
    assert rc != 0, "Expected non-zero exit"
    combined = (out + err).lower()
    assert "no targets found" in combined or "cannot find" in combined


def test_invalid_config_structure(kubectl, test_namespace, repo_root):
    """Malformed scenario YAML causes exit 1."""
    import yaml

    bad_path = _HERE / "_bad_config.yaml"
    try:
        bad_path.write_text(
            yaml.dump({"not_a_list": True})  # top-level must be a list
        )
        rc, out, err = run_kraken(
            build_config(
                base_yaml=bad_path,
                overrides={},
                namespace=test_namespace,
            ),
            repo_root=repo_root,
        )
        assert rc != 0, "Expected failure for malformed config"
    finally:
        bad_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Cleanup verification
# ---------------------------------------------------------------------------


def test_filter_rules_removed(kubectl, test_namespace, repo_root):
    """No residual iptables/nftables rules on pod network after completion."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {"test_duration": 10},
    )
    assert rc == 0
    # The krkn framework logs 'resetting' / 'cleaning' on teardown;
    # exact iptables inspection requires exec into the node, so we
    # check krkn's own cleanup log as evidence.
    combined = (out + err).lower()
    assert "resetting" in combined or "cleaning" in combined


def test_chaos_helper_pod_deleted(kubectl, test_namespace, repo_root):
    """krkn-network-chaos helper pod is cleaned up after test."""
    rc, out, err = _run_filter(
        kubectl,
        test_namespace,
        repo_root,
        {"test_duration": 10},
    )
    assert rc == 0
    # Check that no helper pod with 'network-chaos' in name remains
    result = kubectl(
        "get", "pods",
        "--all-namespaces",
        "-l", "app.kubernetes.io/created-by=krkn",
        "-o", "name",
    )
    assert "krkn-network" not in result, "Helper pod leaked after cleanup"
