#!/usr/bin/env python3

"""
Test suite for krkn.summarized_reports.transform_html module

Usage:
    python -m coverage run -a -m unittest tests/test_summarized_reports_html.py -v

Mirrors the structure of test_summarized_reports.py for the HTML report.
"""

import os
import tempfile
import unittest

from krkn.summarized_reports.transform_html import build_chaos_report_html


def _minimal_chaos_output(**overrides):
    base = {
        "telemetry": {
            "run_uuid": "test-uuid-1234",
            "cluster_version": "4.22.0",
            "cloud_infrastructure": "AWS",
            "cloud_type": "self-managed",
            "total_node_count": 6,
            "network_plugins": ["OVNKubernetes"],
            "scenarios": [],
            "overall_resiliency_report": {
                "total_slos": 0,
                "passed_slos": 0,
                "resiliency_score": 100,
                "scenarios": {},
            },
        },
    }
    base.update(overrides)
    return base


def _make_scenario(scenario_name="test.yml", scenario_type="pod_disruption_scenarios",
                   exit_status=0, parameters=None, affected_pods=None,
                   affected_vmis=None, affected_nodes=None,
                   additional_telemetry=None, cluster_events=None,
                   start_timestamp=1000000, end_timestamp=1000060):
    s = {
        "scenario": scenario_name,
        "scenario_type": scenario_type,
        "exit_status": exit_status,
        "parameters": parameters or {},
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
    }
    if affected_pods is not None:
        s["affected_pods"] = affected_pods
    if affected_vmis is not None:
        s["affected_vmis"] = affected_vmis
    if affected_nodes is not None:
        s["affected_nodes"] = affected_nodes
    if additional_telemetry is not None:
        s["additional_telemetry"] = additional_telemetry
    if cluster_events is not None:
        s["cluster_events"] = cluster_events
    return s


def _generate_html(output):
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        path = f.name
    try:
        build_chaos_report_html(output, path)
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    finally:
        if os.path.exists(path):
            os.unlink(path)


class TestBuildChaosReportHtmlStructure(unittest.TestCase):

    def test_contains_all_sections(self):
        output = _minimal_chaos_output()
        html = _generate_html(output)
        self.assertIn("KRKN Run Summary", html)
        self.assertIn("Run UUID", html)
        self.assertIn("Targets", html)
        self.assertIn("Alerts &amp; SLOs", html)
        self.assertIn("Resiliency Score", html)

    def test_run_metadata(self):
        output = _minimal_chaos_output()
        html = _generate_html(output)
        self.assertIn("test-uuid-1234", html)
        self.assertIn("4.22.0", html)
        self.assertIn("AWS", html)
        self.assertIn("OVNKubernetes", html)

    def test_empty_scenarios(self):
        output = _minimal_chaos_output()
        html = _generate_html(output)
        self.assertIn("Targets", html)
        self.assertNotIn("Key Metrics", html)

    def test_missing_telemetry_key(self):
        html = _generate_html({})
        self.assertIn("KRKN Run Summary", html)
        self.assertIn("N/A", html)

    def test_generates_valid_html(self):
        html = _generate_html(_minimal_chaos_output())
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("</html>", html)

    def test_alerts_title_not_double_escaped(self):
        html = _generate_html(_minimal_chaos_output())
        self.assertIn("Alerts &amp; SLOs", html)
        self.assertNotIn("&amp;amp;", html)


class TestBuildChaosReportHtmlExitStatusOnly(unittest.TestCase):
    """Scenarios like hog_scenarios that only have exit status, no pod/node recovery."""

    def test_pass(self):
        scenario = _make_scenario(scenario_name="cpu-hog.yml", scenario_type="hog_scenarios", exit_status=0)
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("PASS", html)
        self.assertNotIn("Pods Recovered", html)

    def test_fail(self):
        scenario = _make_scenario(exit_status=1)
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("FAIL", html)


class TestBuildChaosReportHtmlPodRecovery(unittest.TestCase):

    def _pod_scenario(self, rescheduling=0.5, readiness=3.0, total=3.5):
        return _make_scenario(
            scenario_name="etcd.yml",
            exit_status=0,
            parameters=[{"id": "kill-pods", "config": {
                "namespace_pattern": "^openshift-etcd$",
                "label_selector": "k8s-app=etcd",
            }}],
            affected_pods={
                "recovered": [{
                    "namespace": "openshift-etcd",
                    "pod_name": "etcd-0",
                    "total_recovery_time": total,
                    "pod_rescheduling_time": rescheduling,
                    "pod_readiness_time": readiness,
                }],
                "unrecovered": [],
            },
        )

    def test_recovery_times_displayed(self):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [self._pod_scenario()]
        html = _generate_html(output)
        self.assertIn("Pods Recovered", html)
        self.assertIn("Pods Unrecovered", html)
        self.assertIn("Total Recovery Time", html)
        self.assertIn("Rescheduling", html)
        self.assertIn("Readiness", html)

    def test_pod_listed_in_targets(self):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [self._pod_scenario()]
        html = _generate_html(output)
        self.assertIn("openshift-etcd/etcd-0", html)
        self.assertIn("k8s-app=etcd", html)
        self.assertIn("^openshift-etcd$", html)

    def test_none_rescheduling_time_coalesced(self):
        scenario = _make_scenario(
            affected_pods={
                "recovered": [{
                    "total_recovery_time": 5.0,
                    "pod_rescheduling_time": None,
                    "pod_readiness_time": None,
                }],
                "unrecovered": [],
            },
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("Rescheduling: 0.00s", html)
        self.assertIn("Readiness: 0.00s", html)

    def test_unrecovered_pods(self):
        scenario = _make_scenario(
            affected_pods={
                "recovered": [],
                "unrecovered": [{"namespace": "ns", "pod_name": "dead-pod"}],
            },
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("Key Metrics", html)
        self.assertIn("Pods Unrecovered", html)
        self.assertIn(">1<", html)


class TestBuildChaosReportHtmlNodeRecovery(unittest.TestCase):

    def test_node_timings(self):
        scenario = _make_scenario(
            scenario_name="cluster_shut_down.yml",
            scenario_type="cluster_shut_down_scenarios",
            parameters={"cloud_type": "aws"},
            affected_nodes=[{
                "node_name": "ip-10-0-1-1.compute.internal",
                "node_id": "i-abc123",
                "stopped_time": 138.5,
                "running_time": 17.0,
            }],
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("Node Recovery", html)
        self.assertIn("ip-10-0-1-1.compute.internal", html)
        self.assertIn("138.50s", html)

    def test_node_without_id(self):
        scenario = _make_scenario(
            affected_nodes=[{"node_name": "worker-1", "node_id": "", "stopped_time": 10.0}],
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("worker-1", html)

    def test_node_only_scenario_renders_without_pods(self):
        """Node recovery must render even when there are no affected pods."""
        scenario = _make_scenario(
            scenario_name="node_shutdown.yml",
            scenario_type="node_scenarios",
            affected_nodes=[{
                "node_name": "worker-1",
                "node_id": "i-abc123",
                "stopped_time": 138.5,
                "running_time": 17.0,
            }],
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("Key Metrics", html)
        self.assertIn("Node Recovery", html)

    def test_zero_duration_renders_as_zero(self):
        scenario = _make_scenario(
            affected_nodes=[{
                "node_name": "worker-1",
                "node_id": "",
                "stopped_time": 0.0,
                "running_time": 0.0,
                "terminating_time": None,
                "not_ready_time": 0.0,
                "ready_time": 5.0,
            }],
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("0.00s", html)
        self.assertIn("5.00s", html)


class TestBuildChaosReportHtmlVMIRecovery(unittest.TestCase):

    def test_vmi_recovery_times(self):
        scenario = _make_scenario(
            affected_vmis={
                "recovered": [{
                    "namespace": "kubevirt",
                    "vmi_name": "test-vm",
                    "total_recovery_time": 10.0,
                    "vmi_rescheduling_time": 2.0,
                    "vmi_readiness_time": 8.0,
                }],
                "unrecovered": [],
            },
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("VMIs Recovered", html)
        self.assertIn("VMI Recovery", html)
        self.assertIn("kubevirt/test-vm", html)

    def test_none_vmi_times_coalesced(self):
        scenario = _make_scenario(
            affected_vmis={
                "recovered": [{
                    "total_recovery_time": 5.0,
                    "vmi_rescheduling_time": None,
                    "vmi_readiness_time": None,
                }],
                "unrecovered": [],
            },
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("Rescheduling: 0.00s", html)

    def test_vmi_only_scenario_renders_without_pods(self):
        """VMI recovery must render even when there are no affected pods."""
        scenario = _make_scenario(
            affected_vmis={
                "recovered": [{
                    "namespace": "kubevirt",
                    "vmi_name": "test-vm",
                    "total_recovery_time": 10.0,
                    "vmi_rescheduling_time": 2.0,
                    "vmi_readiness_time": 8.0,
                }],
                "unrecovered": [],
            },
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("Key Metrics", html)
        self.assertIn("VMI Recovery", html)


class TestBuildChaosReportHtmlLoadTestMetrics(unittest.TestCase):

    def test_additional_telemetry_displayed(self):
        scenario = _make_scenario(
            scenario_name="http_load.yml",
            scenario_type="http_load_scenarios",
            additional_telemetry={
                "requests_per_sec": 150.5,
                "p99_latency_ms": 42.3,
            },
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("Load Test Metrics", html)
        self.assertIn("requests_per_sec", html)
        self.assertIn("150.5", html)


class TestBuildChaosReportHtmlSLOs(unittest.TestCase):

    def test_slo_counts(self):
        output = _minimal_chaos_output()
        output["telemetry"]["overall_resiliency_report"] = {
            "total_slos": 27,
            "passed_slos": 13,
            "resiliency_score": 93,
            "scenarios": {"etcd.yml": 100},
        }
        html = _generate_html(output)
        self.assertIn("27", html)
        self.assertIn("13 / 27", html)
        self.assertIn("14", html)

    def test_failed_slos_listed(self):
        output = _minimal_chaos_output()
        output["scenario_slo_details"] = [{
            "scenario": "etcd.yml",
            "slo_details": [
                {"name": "etcd latency too high", "severity": "warning", "passed": False},
                {"name": "api latency ok", "severity": "warning", "passed": True},
            ],
        }]
        html = _generate_html(output)
        self.assertIn("Failed SLOs", html)
        self.assertIn("etcd latency too high", html)
        self.assertNotIn("api latency ok", html)

    def test_no_failed_slos_section_when_all_pass(self):
        output = _minimal_chaos_output()
        output["scenario_slo_details"] = [{
            "scenario": "etcd.yml",
            "slo_details": [
                {"name": "check1", "severity": "warning", "passed": True},
            ],
        }]
        html = _generate_html(output)
        self.assertNotIn("Failed SLOs", html)


class TestBuildChaosReportHtmlResiliencyScore(unittest.TestCase):

    def test_high_score(self):
        output = _minimal_chaos_output()
        output["telemetry"]["overall_resiliency_report"]["resiliency_score"] = 95
        html = _generate_html(output)
        self.assertIn("95 / 100", html)
        self.assertIn("score-green", html)

    def test_per_scenario_scores(self):
        output = _minimal_chaos_output()
        output["telemetry"]["overall_resiliency_report"]["scenarios"] = {
            "etcd.yml": 100,
            "node.yml": 75,
        }
        html = _generate_html(output)
        self.assertIn("etcd.yml", html)
        self.assertIn("100 / 100", html)
        self.assertIn("node.yml", html)
        self.assertIn("75 / 100", html)

    def test_low_score_red(self):
        output = _minimal_chaos_output()
        output["telemetry"]["overall_resiliency_report"]["resiliency_score"] = 50
        html = _generate_html(output)
        self.assertIn("score-red", html)


class TestBuildChaosReportHtmlAlerts(unittest.TestCase):

    def test_critical_alerts_displayed(self):
        output = _minimal_chaos_output()
        output["critical_alerts"] = {
            "chaos_alerts": [{"alertname": "EtcdDown", "severity": "critical",
                              "namespace": "openshift-etcd", "alertstate": "firing"}],
            "post_chaos_alerts": [],
        }
        html = _generate_html(output)
        self.assertIn("EtcdDown", html)

    def test_no_alerts(self):
        output = _minimal_chaos_output()
        html = _generate_html(output)
        self.assertIn("None", html)


class TestBuildChaosReportHtmlErrorLogs(unittest.TestCase):

    def test_error_logs_displayed(self):
        output = _minimal_chaos_output()
        output["telemetry"]["error_logs"] = [
            {"timestamp": "2026-07-27T10:00:00Z", "message": "Pod creation failed"},
        ]
        html = _generate_html(output)
        self.assertIn("Pod creation failed", html)

    def test_error_logs_truncated_at_20(self):
        output = _minimal_chaos_output()
        output["telemetry"]["error_logs"] = [
            {"timestamp": f"ts-{i}", "message": f"error {i}"} for i in range(25)
        ]
        html = _generate_html(output)
        self.assertIn("... and 5 more", html)

    def test_string_error_logs(self):
        output = _minimal_chaos_output()
        output["telemetry"]["error_logs"] = ["raw error string"]
        html = _generate_html(output)
        self.assertIn("raw error string", html)


class TestBuildChaosReportHtmlSecurityFlags(unittest.TestCase):

    def test_fips_shown(self):
        output = _minimal_chaos_output()
        output["telemetry"]["fips_enabled"] = True
        html = _generate_html(output)
        self.assertIn("FIPS", html)

    def test_no_security_when_all_false(self):
        output = _minimal_chaos_output()
        output["telemetry"]["fips_enabled"] = False
        html = _generate_html(output)
        self.assertNotIn("Security", html)


class TestBuildChaosReportHtmlClusterOverview(unittest.TestCase):

    def test_node_summary_table(self):
        output = _minimal_chaos_output()
        output["telemetry"]["node_summary_infos"] = [{
            "nodes_type": "worker",
            "count": 3,
            "instance_type": "m6i.xlarge",
            "architecture": "amd64",
            "kubelet_version": "v1.35.5",
            "os_version": "RHCOS 9.8",
        }]
        html = _generate_html(output)
        self.assertIn("Cluster Overview", html)
        self.assertIn("worker", html)
        self.assertIn("m6i.xlarge", html)

    def test_node_summary_with_none_values(self):
        """Test that None node metadata fields render as N/A without crashing."""
        output = _minimal_chaos_output()
        output["telemetry"]["node_summary_infos"] = [{
            "nodes_type": None,
            "count": 3,
            "instance_type": None,
            "architecture": "amd64",
            "kubelet_version": "v1.28.0",
            "os_version": "Linux",
        }]
        html = _generate_html(output)
        self.assertIn("Cluster Overview", html)
        overview_start = html.index("Cluster Overview")
        overview_section = html[overview_start:overview_start + 500]
        self.assertIn("N/A", overview_section)
        self.assertNotIn(">None<", overview_section)

    def test_no_overview_when_empty(self):
        output = _minimal_chaos_output()
        output["telemetry"]["node_summary_infos"] = []
        html = _generate_html(output)
        self.assertNotIn("Cluster Overview", html)


class TestBuildChaosReportHtmlMultipleScenarios(unittest.TestCase):

    def test_all_scenarios_rendered(self):
        s1 = _make_scenario(scenario_name="etcd.yml")
        s2 = _make_scenario(scenario_name="cpu-hog.yml")
        s3 = _make_scenario(scenario_name="node.yml")
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [s1, s2, s3]
        html = _generate_html(output)
        self.assertIn("etcd.yml", html)
        self.assertIn("cpu-hog.yml", html)
        self.assertIn("node.yml", html)


class TestBuildChaosReportHtmlClusterEvents(unittest.TestCase):

    def test_events_shown(self):
        scenario = _make_scenario(
            cluster_events=[{
                "type": "Warning",
                "reason": "BackOff",
                "message": "Back-off restarting failed container",
                "involved_object_kind": "Pod",
                "involved_object_name": "etcd-0",
                "namespace": "openshift-etcd",
            }],
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("Cluster Events", html)
        self.assertIn("BackOff", html)

    def test_no_events_section_when_empty(self):
        scenario = _make_scenario(cluster_events=[])
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertNotIn("Cluster Events", html)


class TestBuildChaosReportHtmlHealthChecks(unittest.TestCase):

    def test_health_checks_shown(self):
        output = _minimal_chaos_output()
        output["telemetry"]["health_checks"] = [
            {"url": "https://api.cluster.local:6443", "status_code": 200,
             "status": True, "duration": 0.12},
        ]
        html = _generate_html(output)
        self.assertIn("Health Checks", html)
        self.assertIn("PASS", html)
        self.assertIn("api.cluster.local", html)

    def test_no_health_checks_when_null(self):
        output = _minimal_chaos_output()
        output["telemetry"]["health_checks"] = None
        html = _generate_html(output)
        self.assertNotIn("Health Checks", html)

    def test_string_health_check(self):
        output = _minimal_chaos_output()
        output["telemetry"]["health_checks"] = ["raw check string"]
        html = _generate_html(output)
        self.assertIn("raw check string", html)


class TestBuildChaosReportHtmlKubevirtChecks(unittest.TestCase):

    def test_virt_checks_shown(self):
        output = _minimal_chaos_output()
        output["telemetry"]["virt_checks"] = [{
            "vm_name": "test-vm",
            "namespace": "kubevirt",
            "node_name": "worker-1",
            "ip_address": "10.0.0.5",
            "status": True,
            "duration": 1.23,
        }]
        html = _generate_html(output)
        self.assertIn("KubeVirt Health Checks (Pre-Chaos)", html)
        self.assertIn("10.0.0.5", html)

    def test_post_virt_checks_shown(self):
        output = _minimal_chaos_output()
        output["telemetry"]["post_virt_checks"] = [{
            "vmi_name": "test-vmi",
            "namespace": "kubevirt",
            "node_name": "worker-2",
            "ip_address": "10.0.0.6",
            "new_ip_address": "10.0.0.7",
            "status": True,
            "duration": 2.5,
        }]
        html = _generate_html(output)
        self.assertIn("KubeVirt Health Checks (Post-Chaos)", html)
        self.assertIn("10.0.0.6", html)
        self.assertIn("10.0.0.7", html)

    def test_string_virt_check(self):
        output = _minimal_chaos_output()
        output["telemetry"]["virt_checks"] = ["raw virt check"]
        html = _generate_html(output)
        self.assertIn("raw virt check", html)

    def test_post_virt_string_check(self):
        output = _minimal_chaos_output()
        output["telemetry"]["post_virt_checks"] = ["raw post check"]
        html = _generate_html(output)
        self.assertIn("raw post check", html)


class TestBuildChaosReportHtmlEdgeCases(unittest.TestCase):

    def test_security_flags_etcd_and_ipsec(self):
        output = _minimal_chaos_output()
        output["telemetry"]["etcd_encryption_enabled"] = True
        output["telemetry"]["ipsec_enabled"] = True
        html = _generate_html(output)
        self.assertIn("etcd encryption", html)
        self.assertIn("IPSec", html)

    def test_exclude_label_in_targets(self):
        scenario = _make_scenario(
            parameters=[{"id": "kill", "config": {
                "label_selector": "app=etcd",
                "exclude_label": "component=backup",
            }}],
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("component=backup", html)

    def test_pod_monitoring_error(self):
        scenario = _make_scenario(
            affected_pods={"recovered": [], "unrecovered": [], "error": "timeout reached"},
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("timeout reached", html)

    def test_vmi_monitoring_error(self):
        scenario = _make_scenario(
            affected_vmis={"recovered": [], "unrecovered": [], "error": "ssh failed"},
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("ssh failed", html)

    def test_cluster_events_truncated_beyond_10(self):
        events = [{"type": "Warning", "reason": f"Reason{i}",
                    "message": f"msg{i}"} for i in range(15)]
        scenario = _make_scenario(cluster_events=events)
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("... and 5 more", html)

    def test_string_cluster_event(self):
        scenario = _make_scenario(cluster_events=["raw event string"])
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertIn("raw event string", html)

    def test_post_chaos_alerts(self):
        output = _minimal_chaos_output()
        output["critical_alerts"] = {
            "chaos_alerts": [{"alertname": "A1", "severity": "critical",
                              "namespace": "ns1", "alertstate": "firing"}],
            "post_chaos_alerts": [{"alertname": "A2", "severity": "warning",
                                   "namespace": "ns2", "alertstate": "pending"}],
        }
        html = _generate_html(output)
        self.assertIn("During Chaos", html)
        self.assertIn("Post Chaos", html)
        self.assertIn("A1", html)
        self.assertIn("A2", html)

    def test_string_alert(self):
        output = _minimal_chaos_output()
        output["critical_alerts"] = {
            "chaos_alerts": ["raw alert string"],
            "post_chaos_alerts": ["raw post alert"],
        }
        html = _generate_html(output)
        self.assertIn("raw alert string", html)
        self.assertIn("raw post alert", html)

    def test_xss_prevention(self):
        scenario = _make_scenario(scenario_name='<script>alert("xss")</script>')
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        html = _generate_html(output)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)


class TestBuildChaosReportHtmlFile(unittest.TestCase):

    def test_html_generated(self):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [_make_scenario(
            parameters=[{"id": "kill", "config": {"label_selector": "app=etcd",
                                                   "namespace_pattern": "^ns$"}}],
            affected_pods={
                "recovered": [{"namespace": "ns", "pod_name": "p1",
                               "total_recovery_time": 3.0,
                               "pod_rescheduling_time": 0.5,
                               "pod_readiness_time": 2.5}],
                "unrecovered": [],
            },
        )]
        output["telemetry"]["overall_resiliency_report"]["scenarios"] = {"test.yml": 100}
        output["scenario_slo_details"] = [{
            "scenario": "test.yml",
            "slo_details": [{"name": "slo1", "severity": "warning", "passed": False}],
        }]

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            html_path = f.name
        try:
            result = build_chaos_report_html(output, html_path)
            self.assertEqual(result, html_path)
            self.assertTrue(os.path.exists(html_path))
            with open(html_path, "r") as fh:
                content = fh.read()
            self.assertGreater(len(content), 100)
        finally:
            if os.path.exists(html_path):
                os.unlink(html_path)

    def test_html_with_node_recovery(self):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [_make_scenario(
            affected_nodes=[{
                "node_name": "worker-1", "node_id": "i-123",
                "stopped_time": 100.0, "running_time": 15.0,
            }],
        )]
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            html_path = f.name
        try:
            build_chaos_report_html(output, html_path)
            with open(html_path, "r") as fh:
                content = fh.read()
            self.assertIn("Node Recovery", content)
        finally:
            if os.path.exists(html_path):
                os.unlink(html_path)

    def test_html_with_vmi_recovery(self):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [_make_scenario(
            affected_vmis={
                "recovered": [{"namespace": "kv", "vmi_name": "vm1",
                               "total_recovery_time": 8.0,
                               "vmi_rescheduling_time": 1.0,
                               "vmi_readiness_time": 7.0}],
                "unrecovered": [],
            },
        )]
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            html_path = f.name
        try:
            build_chaos_report_html(output, html_path)
            with open(html_path, "r") as fh:
                content = fh.read()
            self.assertIn("VMI Recovery", content)
        finally:
            if os.path.exists(html_path):
                os.unlink(html_path)

    def test_html_with_none_recovery_times(self):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [_make_scenario(
            affected_pods={
                "recovered": [{"total_recovery_time": 5.0,
                               "pod_rescheduling_time": None,
                               "pod_readiness_time": None}],
                "unrecovered": [],
            },
            affected_vmis={
                "recovered": [{"total_recovery_time": 3.0,
                               "vmi_rescheduling_time": None,
                               "vmi_readiness_time": None}],
                "unrecovered": [],
            },
        )]
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            html_path = f.name
        try:
            build_chaos_report_html(output, html_path)
            with open(html_path, "r") as fh:
                content = fh.read()
            self.assertIn("0.00s", content)
        finally:
            if os.path.exists(html_path):
                os.unlink(html_path)

    def test_html_with_cluster_events(self):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [_make_scenario(
            cluster_events=[
                {"reason": "Pulled", "message": "image pulled", "type": "Normal"},
                "string event",
            ],
        )]
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            html_path = f.name
        try:
            build_chaos_report_html(output, html_path)
            with open(html_path, "r") as fh:
                content = fh.read()
            self.assertIn("Cluster Events", content)
        finally:
            if os.path.exists(html_path):
                os.unlink(html_path)

    def test_html_with_additional_telemetry(self):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [_make_scenario(
            additional_telemetry={"rps": 100},
        )]
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            html_path = f.name
        try:
            build_chaos_report_html(output, html_path)
            with open(html_path, "r") as fh:
                content = fh.read()
            self.assertIn("Load Test Metrics", content)
        finally:
            if os.path.exists(html_path):
                os.unlink(html_path)

    def test_html_empty_scenarios(self):
        output = _minimal_chaos_output()
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            html_path = f.name
        try:
            build_chaos_report_html(output, html_path)
            self.assertTrue(os.path.exists(html_path))
        finally:
            if os.path.exists(html_path):
                os.unlink(html_path)


if __name__ == "__main__":
    unittest.main()
