#!/usr/bin/env python3

"""
Test suite for krkn.summarized_reports.transform module

Usage:
    python -m coverage run -a -m unittest tests/test_summarized_reports.py -v

Assisted By: Claude Code
"""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from krkn.summarized_reports.transform import (
    build_chaos_report,
    build_chaos_report_pdf,
    format_ts,
    format_window,
    _extract_scenario_params,
    _extract_pod_name,
    _extract_vmi_name,
    _extract_critical_alerts,
)


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


class TestFormatTs(unittest.TestCase):

    def test_formats_unix_timestamp(self):
        result = format_ts(1700000000)
        self.assertIn("2023", result)
        self.assertIn(":", result)


class TestFormatWindow(unittest.TestCase):

    def test_same_day_omits_date_on_end(self):
        result = format_window(1000000, 1000060)
        parts = result.split(" – ")
        self.assertEqual(len(parts), 2)
        self.assertIn("-", parts[0])
        self.assertNotIn("-", parts[1])

    def test_different_days_shows_full_dates(self):
        result = format_window(1000000, 1000000 + 86400 * 2)
        parts = result.split(" – ")
        self.assertIn("-", parts[0])
        self.assertIn("-", parts[1])


class TestExtractScenarioParams(unittest.TestCase):

    def test_empty_params(self):
        selectors, ns, exclude, cloud = _extract_scenario_params({})
        self.assertEqual(selectors, [])
        self.assertEqual(ns, [])
        self.assertEqual(exclude, [])
        self.assertEqual(cloud, [])

    def test_flat_label_selector(self):
        params = {"label_selector": "app=etcd"}
        selectors, _, _, _ = _extract_scenario_params(params)
        self.assertEqual(selectors, ["app=etcd"])

    def test_node_selector_hyphenated_key(self):
        params = {"node-selector": "node-role.kubernetes.io/worker"}
        selectors, _, _, _ = _extract_scenario_params(params)
        self.assertEqual(selectors, ["node-role.kubernetes.io/worker"])

    def test_node_label_selector(self):
        params = {"node_label_selector": "node-role.kubernetes.io/worker"}
        selectors, _, _, _ = _extract_scenario_params(params)
        self.assertEqual(selectors, ["node-role.kubernetes.io/worker"])

    def test_namespace_pattern_priority(self):
        params = {"namespace_pattern": "^openshift-etcd$", "namespace": "openshift-etcd"}
        _, ns, _, _ = _extract_scenario_params(params)
        self.assertEqual(ns, ["^openshift-etcd$"])

    def test_namespace_fallback(self):
        params = {"namespace": "default"}
        _, ns, _, _ = _extract_scenario_params(params)
        self.assertEqual(ns, ["default"])

    def test_service_namespace(self):
        params = {"service_namespace": "openshift-console"}
        _, ns, _, _ = _extract_scenario_params(params)
        self.assertEqual(ns, ["openshift-console"])

    def test_exclude_label(self):
        params = {"exclude_label": "component=downloads"}
        _, _, exclude, _ = _extract_scenario_params(params)
        self.assertEqual(exclude, ["component=downloads"])

    def test_empty_exclude_label_ignored(self):
        params = {"exclude_label": ""}
        _, _, exclude, _ = _extract_scenario_params(params)
        self.assertEqual(exclude, [])

    def test_cloud_type(self):
        params = {"cloud_type": "aws"}
        _, _, _, cloud = _extract_scenario_params(params)
        self.assertEqual(cloud, ["aws"])

    def test_nested_pod_disruption_format(self):
        params = [{"id": "kill-pods", "config": {
            "namespace_pattern": "^openshift-etcd$",
            "label_selector": "k8s-app=etcd",
            "exclude_label": "app=etcd-backup",
            "node_label_selector": "node-role.kubernetes.io/worker",
        }}]
        selectors, ns, exclude, _ = _extract_scenario_params(params)
        self.assertIn("k8s-app=etcd", selectors)
        self.assertIn("node-role.kubernetes.io/worker", selectors)
        self.assertEqual(ns, ["^openshift-etcd$"])
        self.assertEqual(exclude, ["app=etcd-backup"])

    def test_node_scenario_format(self):
        params = {"node_scenarios": [{"actions": [
            {"node-selector": "node-role.kubernetes.io/worker", "cloud_type": "aws"}
        ]}]}
        selectors, _, _, cloud = _extract_scenario_params(params)
        self.assertIn("node-role.kubernetes.io/worker", selectors)
        self.assertIn("aws", cloud)

    def test_deduplicates_selectors(self):
        params = [
            {"config": {"label_selector": "app=etcd"}},
            {"config": {"label_selector": "app=etcd"}},
        ]
        selectors, _, _, _ = _extract_scenario_params(params)
        self.assertEqual(selectors, ["app=etcd"])

    def test_non_string_label_selector_ignored(self):
        params = {"label_selector": 123}
        selectors, _, _, _ = _extract_scenario_params(params)
        self.assertEqual(selectors, [])

    def test_none_params(self):
        selectors, ns, exclude, cloud = _extract_scenario_params(None)
        self.assertEqual(selectors, [])


class TestExtractPodName(unittest.TestCase):

    def test_dict_with_namespace(self):
        pod = {"namespace": "openshift-etcd", "pod_name": "etcd-0"}
        self.assertEqual(_extract_pod_name(pod), "openshift-etcd/etcd-0")

    def test_dict_without_namespace(self):
        pod = {"pod_name": "etcd-0"}
        self.assertEqual(_extract_pod_name(pod), "etcd-0")

    def test_string_pod(self):
        self.assertEqual(_extract_pod_name("my-pod"), "my-pod")


class TestExtractVmiName(unittest.TestCase):

    def test_dict_with_namespace(self):
        vmi = {"namespace": "kubevirt", "vmi_name": "test-vm"}
        self.assertEqual(_extract_vmi_name(vmi), "kubevirt/test-vm")

    def test_string_vmi(self):
        self.assertEqual(_extract_vmi_name("my-vmi"), "my-vmi")


class TestExtractCriticalAlerts(unittest.TestCase):

    def test_dict_format(self):
        raw = {"chaos_alerts": [{"alertname": "a1"}], "post_chaos_alerts": [{"alertname": "a2"}]}
        chaos, post = _extract_critical_alerts(raw)
        self.assertEqual(len(chaos), 1)
        self.assertEqual(len(post), 1)

    def test_list_format(self):
        raw = [{"alertname": "a1"}]
        chaos, post = _extract_critical_alerts(raw)
        self.assertEqual(len(chaos), 1)
        self.assertEqual(post, [])

    def test_empty_dict(self):
        chaos, post = _extract_critical_alerts({})
        self.assertEqual(chaos, [])
        self.assertEqual(post, [])

    def test_none_input(self):
        chaos, post = _extract_critical_alerts(None)
        self.assertEqual(chaos, [])
        self.assertEqual(post, [])


class TestBuildChaosReportStructure(unittest.TestCase):

    def test_contains_all_sections(self):
        output = _minimal_chaos_output()
        report = build_chaos_report(output)
        self.assertIn("KRKN RUN SUMMARY", report)
        self.assertIn("Run UUID", report)
        self.assertIn("TARGETS", report)
        self.assertIn("KEY METRICS", report)
        self.assertIn("ALERTS & SLOs", report)
        self.assertIn("RESILIENCY SCORE", report)

    def test_run_metadata(self):
        output = _minimal_chaos_output()
        report = build_chaos_report(output)
        self.assertIn("test-uuid-1234", report)
        self.assertIn("4.22.0", report)
        self.assertIn("AWS", report)
        self.assertIn("OVNKubernetes", report)

    def test_empty_scenarios(self):
        output = _minimal_chaos_output()
        report = build_chaos_report(output)
        self.assertIn("TARGETS", report)
        self.assertIn("KEY METRICS", report)

    def test_missing_telemetry_key(self):
        report = build_chaos_report({})
        self.assertIn("KRKN RUN SUMMARY", report)
        self.assertIn("N/A", report)


class TestBuildChaosReportExitStatusOnly(unittest.TestCase):
    """Scenarios like hog_scenarios that only have exit status, no pod/node recovery."""

    def test_pass(self):
        scenario = _make_scenario(scenario_name="cpu-hog.yml", scenario_type="hog_scenarios", exit_status=0)
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertIn("PASS (0)", report)
        self.assertNotIn("Pods Recovered", report)
        self.assertNotIn("Nodes Affected", report)

    def test_fail(self):
        scenario = _make_scenario(exit_status=1)
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertIn("FAIL (1)", report)


class TestBuildChaosReportPodRecovery(unittest.TestCase):

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
        report = build_chaos_report(output)
        self.assertIn("Pods Recovered        : 1", report)
        self.assertIn("Pods Unrecovered      : 0", report)
        self.assertIn("Total Recovery Time", report)
        self.assertIn("Rescheduling Time", report)
        self.assertIn("Readiness Time", report)

    def test_pod_listed_in_targets(self):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [self._pod_scenario()]
        report = build_chaos_report(output)
        self.assertIn("openshift-etcd/etcd-0", report)
        self.assertIn("k8s-app=etcd", report)
        self.assertIn("^openshift-etcd$", report)

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
        report = build_chaos_report(output)
        self.assertIn("Rescheduling Time: 0.00s", report)
        self.assertIn("Readiness Time   : 0.00s", report)

    def test_unrecovered_pods(self):
        scenario = _make_scenario(
            affected_pods={
                "recovered": [],
                "unrecovered": [{"namespace": "ns", "pod_name": "dead-pod"}],
            },
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertIn("Pods Recovered        : 0", report)
        self.assertIn("Pods Unrecovered      : 1", report)
        self.assertNotIn("Total Recovery Time", report)


class TestBuildChaosReportNodeRecovery(unittest.TestCase):

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
        report = build_chaos_report(output)
        self.assertIn("Nodes Affected        : 1", report)
        self.assertIn("ip-10-0-1-1.compute.internal (i-abc123)", report)
        self.assertIn("Stopped Time", report)
        self.assertIn("138.50s", report)
        self.assertIn("Running Time", report)
        self.assertIn("Cloud Type     : aws", report)

    def test_node_without_id(self):
        scenario = _make_scenario(
            affected_nodes=[{"node_name": "worker-1", "node_id": "", "stopped_time": 10.0}],
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertIn("worker-1", report)
        self.assertNotIn("()", report)


class TestBuildChaosReportVMIRecovery(unittest.TestCase):

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
        report = build_chaos_report(output)
        self.assertIn("VMIs Recovered        : 1", report)
        self.assertIn("VMI Recovery Time", report)
        self.assertIn("kubevirt/test-vm", report)

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
        report = build_chaos_report(output)
        self.assertIn("Rescheduling Time: 0.00s", report)


class TestBuildChaosReportLoadTestMetrics(unittest.TestCase):

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
        report = build_chaos_report(output)
        self.assertIn("Load Test Metrics", report)
        self.assertIn("requests_per_sec", report)
        self.assertIn("150.5", report)


class TestBuildChaosReportSLOs(unittest.TestCase):

    def test_slo_counts(self):
        output = _minimal_chaos_output()
        output["telemetry"]["overall_resiliency_report"] = {
            "total_slos": 27,
            "passed_slos": 13,
            "resiliency_score": 93,
            "scenarios": {"etcd.yml": 100},
        }
        report = build_chaos_report(output)
        self.assertIn("SLOs Evaluated  : 27", report)
        self.assertIn("SLOs Passed     : 13 / 27", report)
        self.assertIn("SLOs Failed     : 14", report)

    def test_failed_slos_listed(self):
        output = _minimal_chaos_output()
        output["scenario_slo_details"] = [{
            "scenario": "etcd.yml",
            "slo_details": [
                {"name": "etcd latency too high", "severity": "warning", "passed": False},
                {"name": "api latency ok", "severity": "warning", "passed": True},
            ],
        }]
        report = build_chaos_report(output)
        self.assertIn("FAILED SLOs (per scenario)", report)
        self.assertIn("etcd latency too high", report)
        self.assertNotIn("api latency ok", report)

    def test_no_failed_slos_section_when_all_pass(self):
        output = _minimal_chaos_output()
        output["scenario_slo_details"] = [{
            "scenario": "etcd.yml",
            "slo_details": [
                {"name": "check1", "severity": "warning", "passed": True},
            ],
        }]
        report = build_chaos_report(output)
        self.assertNotIn("FAILED SLOs", report)


class TestBuildChaosReportResiliencyScore(unittest.TestCase):

    def test_high_score_checkmark(self):
        output = _minimal_chaos_output()
        output["telemetry"]["overall_resiliency_report"]["resiliency_score"] = 95
        report = build_chaos_report(output)
        self.assertIn("95 / 100", report)

    def test_per_scenario_scores(self):
        output = _minimal_chaos_output()
        output["telemetry"]["overall_resiliency_report"]["scenarios"] = {
            "etcd.yml": 100,
            "node.yml": 75,
        }
        report = build_chaos_report(output)
        self.assertIn("etcd.yml", report)
        self.assertIn("100 / 100", report)
        self.assertIn("node.yml", report)
        self.assertIn("75 / 100", report)


class TestBuildChaosReportAlerts(unittest.TestCase):

    def test_critical_alerts_displayed(self):
        output = _minimal_chaos_output()
        output["critical_alerts"] = {
            "chaos_alerts": [{"alertname": "EtcdDown", "severity": "critical",
                              "namespace": "openshift-etcd", "alertstate": "firing"}],
            "post_chaos_alerts": [],
        }
        report = build_chaos_report(output)
        self.assertIn("Critical Alerts : 1", report)
        self.assertIn("EtcdDown", report)

    def test_no_alerts(self):
        output = _minimal_chaos_output()
        report = build_chaos_report(output)
        self.assertIn("Critical Alerts : None", report)


class TestBuildChaosReportErrorLogs(unittest.TestCase):

    def test_error_logs_displayed(self):
        output = _minimal_chaos_output()
        output["telemetry"]["error_logs"] = [
            {"timestamp": "2026-07-27T10:00:00Z", "message": "Pod creation failed"},
        ]
        report = build_chaos_report(output)
        self.assertIn("Error Logs      : 1", report)
        self.assertIn("Pod creation failed", report)

    def test_error_logs_truncated_at_20(self):
        output = _minimal_chaos_output()
        output["telemetry"]["error_logs"] = [
            {"timestamp": f"ts-{i}", "message": f"error {i}"} for i in range(25)
        ]
        report = build_chaos_report(output)
        self.assertIn("... and 5 more", report)

    def test_string_error_logs(self):
        output = _minimal_chaos_output()
        output["telemetry"]["error_logs"] = ["raw error string"]
        report = build_chaos_report(output)
        self.assertIn("raw error string", report)


class TestBuildChaosReportSecurityFlags(unittest.TestCase):

    def test_fips_shown(self):
        output = _minimal_chaos_output()
        output["telemetry"]["fips_enabled"] = True
        report = build_chaos_report(output)
        self.assertIn("Security : FIPS", report)

    def test_no_security_when_all_false(self):
        output = _minimal_chaos_output()
        output["telemetry"]["fips_enabled"] = False
        report = build_chaos_report(output)
        self.assertNotIn("Security", report)


class TestBuildChaosReportClusterOverview(unittest.TestCase):

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
        report = build_chaos_report(output)
        self.assertIn("CLUSTER OVERVIEW", report)
        self.assertIn("worker", report)
        self.assertIn("m6i.xlarge", report)

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
        report = build_chaos_report(output)
        self.assertIn("CLUSTER OVERVIEW", report)
        overview_start = report.index("CLUSTER OVERVIEW")
        overview_section = report[overview_start:overview_start + 200]
        self.assertIn("N/A", overview_section)
        self.assertNotIn("None", overview_section)

    def test_no_overview_when_empty(self):
        output = _minimal_chaos_output()
        output["telemetry"]["node_summary_infos"] = []
        report = build_chaos_report(output)
        self.assertNotIn("CLUSTER OVERVIEW", report)


class TestBuildChaosReportClusterEvents(unittest.TestCase):

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
        report = build_chaos_report(output)
        self.assertIn("Cluster Events", report)
        self.assertIn("BackOff", report)

    def test_no_events_section_when_empty(self):
        scenario = _make_scenario(cluster_events=[])
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertNotIn("Cluster Events", report)


class TestBuildChaosReportMultipleScenarios(unittest.TestCase):

    def test_scenarios_numbered(self):
        s1 = _make_scenario(scenario_name="etcd.yml")
        s2 = _make_scenario(scenario_name="cpu-hog.yml")
        s3 = _make_scenario(scenario_name="node.yml")
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [s1, s2, s3]
        report = build_chaos_report(output)
        self.assertIn("[1] Scenario", report)
        self.assertIn("[2] Scenario", report)
        self.assertIn("[3] Scenario", report)


class TestBuildChaosReportHealthChecks(unittest.TestCase):

    def test_health_checks_shown(self):
        output = _minimal_chaos_output()
        output["telemetry"]["health_checks"] = [
            {"url": "https://api.cluster.local:6443", "status_code": 200,
             "status": True, "duration": 0.12},
        ]
        report = build_chaos_report(output)
        self.assertIn("HEALTH CHECKS", report)
        self.assertIn("PASS", report)
        self.assertIn("api.cluster.local", report)

    def test_no_health_checks_when_null(self):
        output = _minimal_chaos_output()
        output["telemetry"]["health_checks"] = None
        report = build_chaos_report(output)
        self.assertNotIn("HEALTH CHECKS", report)

    def test_string_health_check(self):
        output = _minimal_chaos_output()
        output["telemetry"]["health_checks"] = ["raw check string"]
        report = build_chaos_report(output)
        self.assertIn("raw check string", report)


class TestBuildChaosReportKubevirtChecks(unittest.TestCase):

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
        report = build_chaos_report(output)
        self.assertIn("KUBEVIRT HEALTH CHECKS (during-chaos)", report)
        self.assertIn("kubevirt/test-vm", report)
        self.assertIn("10.0.0.5", report)

    def test_post_virt_checks_shown(self):
        output = _minimal_chaos_output()
        output["telemetry"]["virt_checks"] = [{
            "vmi_name": "test-vmi",
            "namespace": "kubevirt",
            "node_name": "worker-2",
            "ip_address": "10.0.0.6",
            "new_ip_address": "10.0.0.7",
            "status": True,
            "duration": 2.5,
            "phase": "post",
        }]
        report = build_chaos_report(output)
        self.assertIn("KUBEVIRT HEALTH CHECKS (post-chaos)", report)
        self.assertIn("10.0.0.6", report)
        self.assertIn("10.0.0.7", report)

    def test_string_virt_check(self):
        output = _minimal_chaos_output()
        output["telemetry"]["virt_checks"] = ["raw virt check"]
        report = build_chaos_report(output)
        self.assertIn("raw virt check", report)

    def test_post_virt_string_check(self):
        output = _minimal_chaos_output()
        output["telemetry"]["virt_checks"] = [{"phase": "post", "vm_name": "raw post check"}]
        report = build_chaos_report(output)
        self.assertIn("raw post check", report)


class TestBuildChaosReportEdgeCases(unittest.TestCase):

    def test_security_flags_etcd_and_ipsec(self):
        output = _minimal_chaos_output()
        output["telemetry"]["etcd_encryption_enabled"] = True
        output["telemetry"]["ipsec_enabled"] = True
        report = build_chaos_report(output)
        self.assertIn("etcd encryption", report)
        self.assertIn("IPSec", report)

    def test_exclude_label_in_targets(self):
        scenario = _make_scenario(
            parameters=[{"id": "kill", "config": {
                "label_selector": "app=etcd",
                "exclude_label": "component=backup",
            }}],
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertIn("Exclude Label  : component=backup", report)

    def test_pod_monitoring_error(self):
        scenario = _make_scenario(
            affected_pods={"recovered": [], "unrecovered": [], "error": "timeout reached"},
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertIn("Pod Monitoring Error: timeout reached", report)

    def test_vmi_monitoring_error(self):
        scenario = _make_scenario(
            affected_vmis={"recovered": [], "unrecovered": [], "error": "ssh failed"},
        )
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertIn("VMI Monitoring Error: ssh failed", report)

    def test_string_node_in_affected_nodes(self):
        scenario = _make_scenario(affected_nodes=["node-as-string"])
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertIn("node-as-string", report)

    def test_cluster_events_truncated_beyond_10(self):
        events = [{"type": "Warning", "reason": f"Reason{i}",
                    "message": f"msg{i}"} for i in range(15)]
        scenario = _make_scenario(cluster_events=events)
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertIn("... and 5 more", report)

    def test_string_cluster_event(self):
        scenario = _make_scenario(cluster_events=["raw event string"])
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [scenario]
        report = build_chaos_report(output)
        self.assertIn("raw event string", report)

    def test_post_chaos_alerts(self):
        output = _minimal_chaos_output()
        output["critical_alerts"] = {
            "chaos_alerts": [{"alertname": "A1", "severity": "critical",
                              "namespace": "ns1", "alertstate": "firing"}],
            "post_chaos_alerts": [{"alertname": "A2", "severity": "warning",
                                   "namespace": "ns2", "alertstate": "pending"}],
        }
        report = build_chaos_report(output)
        self.assertIn("During Chaos:", report)
        self.assertIn("Post Chaos:", report)
        self.assertIn("A1", report)
        self.assertIn("A2", report)
        self.assertIn("Critical Alerts : 2", report)

    def test_string_alert(self):
        output = _minimal_chaos_output()
        output["critical_alerts"] = {
            "chaos_alerts": ["raw alert string"],
            "post_chaos_alerts": ["raw post alert"],
        }
        report = build_chaos_report(output)
        self.assertIn("raw alert string", report)
        self.assertIn("raw post alert", report)


class TestBuildChaosReportPdf(unittest.TestCase):

    @patch("reportlab.platypus.SimpleDocTemplate.build")
    def test_pdf_generated(self, mock_build):
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

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name
        try:
            result = build_chaos_report_pdf(output, pdf_path)
            self.assertEqual(result, pdf_path)
            mock_build.assert_called_once()
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @patch("reportlab.platypus.SimpleDocTemplate.build")
    def test_pdf_with_node_recovery(self, mock_build):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [_make_scenario(
            affected_nodes=[{
                "node_name": "worker-1", "node_id": "i-123",
                "stopped_time": 100.0, "running_time": 15.0,
            }],
        )]
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name
        try:
            build_chaos_report_pdf(output, pdf_path)
            mock_build.assert_called_once()
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @patch("reportlab.platypus.SimpleDocTemplate.build")
    def test_pdf_with_vmi_recovery(self, mock_build):
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
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name
        try:
            build_chaos_report_pdf(output, pdf_path)
            mock_build.assert_called_once()
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @patch("reportlab.platypus.SimpleDocTemplate.build")
    def test_pdf_with_none_recovery_times(self, mock_build):
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
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name
        try:
            build_chaos_report_pdf(output, pdf_path)
            mock_build.assert_called_once()
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @patch("reportlab.platypus.SimpleDocTemplate.build")
    def test_pdf_with_cluster_events(self, mock_build):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [_make_scenario(
            cluster_events=[
                {"reason": "Pulled", "message": "image pulled", "type": "Normal"},
                "string event",
            ],
        )]
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name
        try:
            build_chaos_report_pdf(output, pdf_path)
            mock_build.assert_called_once()
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @patch("reportlab.platypus.SimpleDocTemplate.build")
    def test_pdf_with_additional_telemetry(self, mock_build):
        output = _minimal_chaos_output()
        output["telemetry"]["scenarios"] = [_make_scenario(
            additional_telemetry={"rps": 100},
        )]
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name
        try:
            build_chaos_report_pdf(output, pdf_path)
            mock_build.assert_called_once()
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @patch("reportlab.platypus.SimpleDocTemplate.build")
    def test_pdf_empty_scenarios(self, mock_build):
        output = _minimal_chaos_output()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name
        try:
            build_chaos_report_pdf(output, pdf_path)
            mock_build.assert_called_once()
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)


if __name__ == "__main__":
    unittest.main()
