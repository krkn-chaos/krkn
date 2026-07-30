import logging
import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

SCENARIO_TYPE_DOCS = {
    "pod_disruption_scenarios": "https://krkn-chaos.dev/docs/scenarios/pod-disruption/",
    "container_scenarios": "https://krkn-chaos.dev/docs/scenarios/container-scenarios/",
    "node_scenarios": "https://krkn-chaos.dev/docs/scenarios/node-scenarios/",
    "hog_scenarios": "https://krkn-chaos.dev/docs/scenarios/hog-scenarios/",
    "zone_outages_scenarios": "https://krkn-chaos.dev/docs/scenarios/zone-outages/",
    "application_outages_scenarios": "https://krkn-chaos.dev/docs/scenarios/application-outages/",
    "pod_network_scenarios": "https://krkn-chaos.dev/docs/scenarios/pod-network-scenarios/",
    "time_scenarios": "https://krkn-chaos.dev/docs/scenarios/time-scenarios/",
    "cluster_shut_down_scenarios": "https://krkn-chaos.dev/docs/scenarios/cluster-shut-down/",
    "pvc_scenarios": "https://krkn-chaos.dev/docs/scenarios/pvc-scenarios/",
    "network_chaos_scenarios": "https://krkn-chaos.dev/docs/scenarios/network-chaos/",
    "network_chaos_ng_scenarios": "https://krkn-chaos.dev/docs/scenarios/network-chaos/",
    "service_disruption_scenarios": "https://krkn-chaos.dev/docs/scenarios/service-disruption/",
    "service_hijacking_scenarios": "https://krkn-chaos.dev/docs/scenarios/service-hijacking/",
    "syn_flood_scenarios": "https://krkn-chaos.dev/docs/scenarios/syn-flood/",
    "http_load_scenarios": "https://krkn-chaos.dev/docs/scenarios/http-load/",
    "kubevirt_vm_outage": "https://krkn-chaos.dev/docs/scenarios/kubevirt-vm-outage/",
    "managedcluster_scenarios": "https://krkn-chaos.dev/docs/scenarios/managed-cluster/",
    "storage_throttle_scenarios": "https://krkn-chaos.dev/docs/scenarios/storage-throttle/",
}


def format_ts(unix_ts):
    return datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M:%S")


def format_window(start_ts, end_ts):
    start_dt = datetime.fromtimestamp(start_ts)
    end_dt = datetime.fromtimestamp(end_ts)
    if start_dt.date() == end_dt.date():
        return f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} – {end_dt.strftime('%H:%M:%S')}"
    return f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} – {end_dt.strftime('%Y-%m-%d %H:%M:%S')}"


def _extract_scenario_params(raw_params):
    """Extract label_selectors, namespaces, and exclude_labels from all parameter shapes.

    Walks the entire parameter tree recursively so it works regardless of
    how deeply the keys are nested (pod_disruption, container, node, hog,
    kubevirt, network_chaos, time_scenarios, application_outage, pvc, etc.).
    """
    selectors = []
    namespaces = []
    exclude_labels = []
    cloud_types = []

    def _walk(obj):
        if isinstance(obj, dict):
            ls = obj.get("label_selector")
            if ls and isinstance(ls, str):
                selectors.append(ls)
            ns = obj.get("node-selector")
            if ns and isinstance(ns, str):
                selectors.append(ns)
            nls = obj.get("node_label_selector")
            if nls and isinstance(nls, str):
                selectors.append(nls)
            for ns_key in ("namespace_pattern", "namespace", "service_namespace"):
                nsp = obj.get(ns_key)
                if nsp and isinstance(nsp, str):
                    namespaces.append(nsp)
                    break
            el = obj.get("exclude_label")
            if el and isinstance(el, str):
                exclude_labels.append(el)
            ct = obj.get("cloud_type")
            if ct and isinstance(ct, str):
                cloud_types.append(ct)
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    _walk(item)

    _walk(raw_params)

    # deduplicate while preserving order
    seen = set()
    selectors = [s for s in selectors if not (s in seen or seen.add(s))]
    seen = set()
    namespaces = [n for n in namespaces if not (n in seen or seen.add(n))]
    seen = set()
    exclude_labels = [e for e in exclude_labels if not (e in seen or seen.add(e))]
    seen = set()
    cloud_types = [c for c in cloud_types if not (c in seen or seen.add(c))]

    return selectors, namespaces, exclude_labels, cloud_types


def _extract_pod_name(pod):
    if isinstance(pod, dict):
        ns = pod.get("namespace", "")
        name = pod.get("pod_name", str(pod))
        return f"{ns}/{name}" if ns else name
    return str(pod)


def _extract_vmi_name(vmi):
    if isinstance(vmi, dict):
        ns = vmi.get("namespace", "")
        name = vmi.get("vmi_name", str(vmi))
        return f"{ns}/{name}" if ns else name
    return str(vmi)


def _extract_critical_alerts(critical_alerts_raw):
    if isinstance(critical_alerts_raw, dict):
        chaos = critical_alerts_raw.get("chaos_alerts", [])
        post = critical_alerts_raw.get("post_chaos_alerts", [])
        return chaos, post
    if isinstance(critical_alerts_raw, list):
        return critical_alerts_raw, []
    return [], []


def build_chaos_report(chaos_output: dict) -> str:
    telemetry = chaos_output.get("telemetry", {})
    scenarios = telemetry.get("scenarios", [])
    job_status = telemetry.get("job_status", True)

    lines = []
    lines.append("=" * 80)
    lines.append("KRKN RUN SUMMARY")
    lines.append("=" * 80)

    # --- Run Metadata ---
    lines.append("Run UUID : " + str(telemetry.get("run_uuid", "N/A")))
    lines.append("Status   : " + ("PASS" if job_status else "FAIL"))
    lines.append(
        "Cluster  : "
        + str(telemetry.get("cluster_version", "N/A"))
        + " ("
        + str(telemetry.get("cloud_infrastructure", "N/A"))
        + ", "
        + str(telemetry.get("cloud_type", "N/A"))
        + ")"
    )

    starts = [s["start_timestamp"] for s in scenarios if s.get("start_timestamp")]
    ends = [s["end_timestamp"] for s in scenarios if s.get("end_timestamp")]
    if starts and ends:
        lines.append("Window   : " + format_window(min(starts), max(ends)))
    else:
        lines.append("Window   : N/A")
    lines.append("Nodes    : " + str(telemetry.get("total_node_count", "N/A")))
    network = telemetry.get("network_plugins") or []
    if network:
        lines.append("Network  : " + ", ".join(network))
    security_flags = []
    if telemetry.get("fips_enabled"):
        security_flags.append("FIPS")
    if telemetry.get("etcd_encryption_enabled"):
        security_flags.append("etcd encryption")
    if telemetry.get("ipsec_enabled"):
        security_flags.append("IPSec")
    if security_flags:
        lines.append("Security : " + ", ".join(security_flags))

    # --- Cluster Overview ---
    node_infos = telemetry.get("node_summary_infos") or []
    if node_infos:
        lines.append("CLUSTER OVERVIEW")
        lines.append(f"  {'Type':<8} {'Count':<6} {'Instance':<14} {'Arch':<7} {'Kubelet':<10} OS")
        for ni in node_infos:
            lines.append(
                f"  {ni.get('nodes_type', 'N/A'):<8} "
                f"{ni.get('count', 'N/A'):<6} "
                f"{ni.get('instance_type', 'N/A'):<14} "
                f"{ni.get('architecture', 'N/A'):<7} "
                f"{ni.get('kubelet_version', 'N/A'):<10} "
                f"{ni.get('os_version', 'N/A')}"
            )

    # --- Targets ---
    lines.append("TARGETS")
    for i, s in enumerate(scenarios, 1):
        lines.append(f"  [{i}] Scenario  : " + str(s.get("scenario", "N/A")) + " (" + str(s.get("scenario_type", "N/A")) + ")")
        selectors, ns_list, exclude_labels, cloud_types = _extract_scenario_params(s.get("parameters", {}))
        if selectors:
            lines.append("  Label Selector : " + ", ".join(selectors))
        if ns_list:
            lines.append("  Namespace      : " + ", ".join(ns_list))
        if exclude_labels:
            lines.append("  Exclude Label  : " + ", ".join(exclude_labels))
        if cloud_types:
            lines.append("  Cloud Type     : " + ", ".join(cloud_types))

        recovered = s.get("affected_pods", {}).get("recovered", [])
        unrecovered = s.get("affected_pods", {}).get("unrecovered", [])
        pods_error = s.get("affected_pods", {}).get("error")
        if unrecovered or recovered:
            lines.append("  Pods Disrupted :")
            for pod in unrecovered + recovered:
                lines.append("    - " + _extract_pod_name(pod))
        if pods_error:
            lines.append(f"  Pod Monitoring Error: {pods_error}")

        vmi_recovered = s.get("affected_vmis", {}).get("recovered", [])
        vmi_unrecovered = s.get("affected_vmis", {}).get("unrecovered", [])
        vmis_error = s.get("affected_vmis", {}).get("error")
        if vmi_recovered or vmi_unrecovered:
            lines.append("  VMIs Disrupted :")
            for vmi in vmi_unrecovered + vmi_recovered:
                lines.append("    - " + _extract_vmi_name(vmi))
        if vmis_error:
            lines.append(f"  VMI Monitoring Error: {vmis_error}")

        affected_nodes = s.get("affected_nodes", [])
        if affected_nodes:
            lines.append("  Nodes Affected :")
            for node in affected_nodes:
                if isinstance(node, dict):
                    node_id = node.get("node_id", "")
                    label = node.get("node_name", str(node))
                    if node_id:
                        label += f" ({node_id})"
                    lines.append("    - " + label)
                else:
                    lines.append("    - " + str(node))

    # --- Key Metrics ---
    lines.append("KEY METRICS")
    for i, s in enumerate(scenarios, 1):
        lines.append(f"  [{i}] Scenario: " + str(s.get("scenario", "N/A")))

        exit_status = str(s.get("exit_status", "1"))
        status = "PASS (0)" if exit_status == "0" else "FAIL (1)"
        lines.append("    Exit Status           : " + status)

        recovered = s.get("affected_pods", {}).get("recovered", [])
        unrecovered = s.get("affected_pods", {}).get("unrecovered", [])
        if recovered or unrecovered:
            lines.append("    Pods Recovered        : " + str(len(recovered)))
            lines.append("    Pods Unrecovered      : " + str(len(unrecovered)))

        pod_recovery_times = [
            p.get("total_recovery_time")
            for p in recovered
            if isinstance(p, dict) and p.get("total_recovery_time") is not None
        ]
        if pod_recovery_times:
            total = max(pod_recovery_times)
            reschedule_times = [p.get("pod_rescheduling_time") or 0 for p in recovered if isinstance(p, dict)]
            readiness_times = [p.get("pod_readiness_time") or 0 for p in recovered if isinstance(p, dict)]
            lines.append(f"    Total Recovery Time   : {total:.2f}s")
            lines.append(f"      ├─ Rescheduling Time: {max(reschedule_times):.2f}s")
            lines.append(f"      └─ Readiness Time   : {max(readiness_times):.2f}s")

        vmi_recovered = s.get("affected_vmis", {}).get("recovered", [])
        vmi_unrecovered = s.get("affected_vmis", {}).get("unrecovered", [])
        if vmi_recovered or vmi_unrecovered:
            lines.append("    VMIs Recovered        : " + str(len(vmi_recovered)))
            lines.append("    VMIs Unrecovered      : " + str(len(vmi_unrecovered)))
            vmi_recovery_times = [
                v.get("total_recovery_time")
                for v in vmi_recovered
                if isinstance(v, dict) and v.get("total_recovery_time") is not None
            ]
            if vmi_recovery_times:
                total = max(vmi_recovery_times)
                reschedule_times = [v.get("vmi_rescheduling_time") or 0 for v in vmi_recovered if isinstance(v, dict)]
                readiness_times = [v.get("vmi_readiness_time") or 0 for v in vmi_recovered if isinstance(v, dict)]
                lines.append(f"    VMI Recovery Time     : {total:.2f}s")
                lines.append(f"      ├─ Rescheduling Time: {max(reschedule_times):.2f}s")
                lines.append(f"      └─ Readiness Time   : {max(readiness_times):.2f}s")

        affected_nodes = s.get("affected_nodes", [])
        if affected_nodes:
            lines.append(f"    Nodes Affected        : {len(affected_nodes)}")
            for node in affected_nodes:
                if not isinstance(node, dict):
                    continue
                node_label = node.get("node_name", "N/A")
                node_id = node.get("node_id", "")
                if node_id:
                    node_label += f" ({node_id})"
                lines.append(f"      Node: {node_label}")
                timings = []
                for key, label in [
                    ("stopped_time", "Stopped Time"),
                    ("running_time", "Running Time"),
                    ("terminating_time", "Terminating Time"),
                    ("not_ready_time", "Not Ready Time"),
                    ("ready_time", "Ready Time"),
                ]:
                    val = node.get(key)
                    if val is not None and val > 0:
                        timings.append((label, val))
                for i, (label, val) in enumerate(timings):
                    connector = "└─" if i == len(timings) - 1 else "├─"
                    lines.append(f"        {connector} {label:<17}: {val:.2f}s")

        # Additional telemetry (HTTP load test / Vegeta metrics)
        additional = s.get("additional_telemetry")
        if additional and isinstance(additional, dict):
            lines.append("    Load Test Metrics:")
            for metric_key, metric_val in additional.items():
                lines.append(f"      {metric_key}: {metric_val}")

        cluster_events = s.get("cluster_events") or []
        if cluster_events:
            lines.append(f"    Cluster Events        : {len(cluster_events)}")
            for event in cluster_events[:10]:
                if isinstance(event, dict):
                    etype = event.get("type", "")
                    reason = event.get("reason", "N/A")
                    msg = event.get("message", "N/A")
                    obj_kind = event.get("involved_object_kind", "")
                    obj_name = event.get("involved_object_name", "")
                    ns = event.get("namespace", "")
                    prefix = f"[{etype}] " if etype else ""
                    obj_ref = f" ({obj_kind}/{obj_name})" if obj_kind else ""
                    ns_ref = f" in {ns}" if ns else ""
                    lines.append(f"      - {prefix}{reason}: {msg}{obj_ref}{ns_ref}")
                else:
                    lines.append(f"      - {event}")
            if len(cluster_events) > 10:
                lines.append(f"      ... and {len(cluster_events) - 10} more")

    # --- Health Checks ---
    health_checks = telemetry.get("health_checks")
    if health_checks:
        lines.append("HEALTH CHECKS")
        for check in health_checks:
            if isinstance(check, dict):
                url = check.get("url", "")
                status_code = check.get("status_code", "")
                duration = check.get("duration")
                passed = check.get("status") or check.get("passed")
                status_str = "PASS" if passed else "FAIL"
                detail = url or check.get("name") or check.get("check_name", "N/A")
                extra = []
                if status_code:
                    extra.append(f"HTTP {status_code}")
                if duration is not None and duration != "":
                    extra.append(f"{float(duration):.2f}s")
                suffix = f" ({', '.join(extra)})" if extra else ""
                lines.append(f"  {status_str:<6} {detail}{suffix}")
            else:
                lines.append(f"  {check}")

    # --- KubeVirt Health Checks ---
    virt_checks = telemetry.get("virt_checks")
    if virt_checks:
        lines.append("KUBEVIRT HEALTH CHECKS (pre-chaos)")
        for check in virt_checks:
            if isinstance(check, dict):
                vm = check.get("vm_name") or check.get("vmi_name") or check.get("name", "N/A")
                ns = check.get("namespace", "")
                node = check.get("node_name", "")
                ip = check.get("ip_address", "")
                passed = check.get("status", True)
                duration = check.get("duration")
                status_str = "PASS" if passed else "FAIL"
                label = f"{ns}/{vm}" if ns else vm
                extra = []
                if ip:
                    extra.append(ip)
                if node:
                    extra.append(f"on {node}")
                if duration is not None and duration != "":
                    extra.append(f"{float(duration):.2f}s")
                suffix = f" ({', '.join(extra)})" if extra else ""
                lines.append(f"  {status_str:<6} {label}{suffix}")
            else:
                lines.append(f"  {check}")

    post_virt_checks = telemetry.get("post_virt_checks")
    if post_virt_checks:
        lines.append("KUBEVIRT HEALTH CHECKS (post-chaos)")
        for check in post_virt_checks:
            if isinstance(check, dict):
                vm = check.get("vm_name") or check.get("vmi_name") or check.get("name", "N/A")
                ns = check.get("namespace", "")
                node = check.get("node_name", "")
                ip = check.get("ip_address", "")
                new_ip = check.get("new_ip_address", "")
                passed = check.get("status", True)
                duration = check.get("duration")
                status_str = "PASS" if passed else "FAIL"
                label = f"{ns}/{vm}" if ns else vm
                extra = []
                if ip:
                    ip_str = ip
                    if new_ip and new_ip != ip:
                        ip_str += f" → {new_ip}"
                    extra.append(ip_str)
                if node:
                    extra.append(f"on {node}")
                if duration is not None and duration != "":
                    extra.append(f"{float(duration):.2f}s")
                suffix = f" ({', '.join(extra)})" if extra else ""
                lines.append(f"  {status_str:<6} {label}{suffix}")
            else:
                lines.append(f"  {check}")

    # --- Alerts & SLOs ---

    scenario_slo_details = chaos_output.get("scenario_slo_details", [])
    resiliency = telemetry.get("overall_resiliency_report", {})
    total_slos = resiliency.get("total_slos", 0)
    passed_slos = resiliency.get("passed_slos", 0)
    failed_slos = total_slos - passed_slos
    critical_alerts_raw = chaos_output.get("critical_alerts") or {}
    chaos_alerts, post_chaos_alerts = _extract_critical_alerts(critical_alerts_raw)
    error_logs = telemetry.get("error_logs") or []

    lines.append("ALERTS & SLOs")
    lines.append("  SLOs Evaluated  : " + str(total_slos))
    lines.append(f"  SLOs Passed     : {passed_slos} / {total_slos}")
    lines.append("  SLOs Failed     : " + str(failed_slos))

    total_alert_count = len(chaos_alerts) + len(post_chaos_alerts)
    lines.append("  Critical Alerts : " + (str(total_alert_count) if total_alert_count else "None"))
    if chaos_alerts:
        lines.append("    During Chaos:")
        for alert in chaos_alerts:
            if isinstance(alert, dict):
                lines.append(
                    f"      - {alert.get('alertname', 'N/A')} "
                    f"[{alert.get('severity', 'N/A')}] "
                    f"ns={alert.get('namespace', 'N/A')} "
                    f"state={alert.get('alertstate', 'N/A')}"
                )
            else:
                lines.append(f"      - {alert}")
    if post_chaos_alerts:
        lines.append("    Post Chaos:")
        for alert in post_chaos_alerts:
            if isinstance(alert, dict):
                lines.append(
                    f"      - {alert.get('alertname', 'N/A')} "
                    f"[{alert.get('severity', 'N/A')}] "
                    f"ns={alert.get('namespace', 'N/A')} "
                    f"state={alert.get('alertstate', 'N/A')}"
                )
            else:
                lines.append(f"      - {alert}")

    if error_logs:
        lines.append(f"  Error Logs      : {len(error_logs)}")
        for log_entry in error_logs[:20]:
            if isinstance(log_entry, dict):
                ts = log_entry.get("timestamp", "")
                msg = log_entry.get("message", str(log_entry))
                lines.append(f"    [{ts}] {msg}" if ts else f"    {msg}")
            else:
                lines.append(f"    {log_entry}")
        if len(error_logs) > 20:
            lines.append(f"    ... and {len(error_logs) - 20} more")

    # --- Failed SLOs ---
    if scenario_slo_details:
        has_failures = any(
            not s["passed"]
            for entry in scenario_slo_details
            for s in entry.get("slo_details", [])
        )
        if has_failures:
            lines.append("FAILED SLOs (per scenario)")
            for entry in scenario_slo_details:
                failed = [s for s in entry.get("slo_details", []) if not s["passed"]]
                if not failed:
                    continue
                lines.append(f"  Scenario: {entry['scenario']}")
                for slo in failed:
                    lines.append(f"    FAIL  [{slo.get('severity', 'unknown'):<8}]  {slo['name']}")

    # --- Resiliency Score ---
    lines.append("RESILIENCY SCORE")
    per_scenario_scores = resiliency.get("scenarios", {})
    for scenario_name, score in per_scenario_scores.items():
        lines.append(f"  {scenario_name:<28} : {score} / 100")

    overall_score = resiliency.get("resiliency_score", "N/A")
    emoji = ""
    if isinstance(overall_score, (int, float)):
        emoji = "  ✅" if overall_score >= 90 else ("  ⚠️" if overall_score >= 70 else "  ❌")
    lines.append(f"  Overall Score                : {overall_score} / 100{emoji}")
    lines.append("=" * 80)

    return "\n".join(lines)


def build_chaos_report_pdf(chaos_output: dict, output_path: str) -> str:
    from weasyprint import HTML
    logging.getLogger("weasyprint").setLevel(logging.WARNING)

    telemetry = chaos_output.get("telemetry", {})
    scenarios_raw = telemetry.get("scenarios", [])

    starts = [s["start_timestamp"] for s in scenarios_raw if s.get("start_timestamp")]
    ends = [s["end_timestamp"] for s in scenarios_raw if s.get("end_timestamp")]
    time_window = format_window(min(starts), max(ends)) if starts and ends else "N/A"

    scenarios = []
    for s in scenarios_raw:
        selectors, ns_list, exclude_labels, cloud_types = _extract_scenario_params(s.get("parameters", {}))

        recovered = s.get("affected_pods", {}).get("recovered", [])
        unrecovered = s.get("affected_pods", {}).get("unrecovered", [])
        all_pods = [_extract_pod_name(p) for p in unrecovered + recovered]
        pods_error = s.get("affected_pods", {}).get("error")

        pod_recovery_times = [
            p.get("total_recovery_time")
            for p in recovered
            if isinstance(p, dict) and p.get("total_recovery_time") is not None
        ]
        if pod_recovery_times:
            total_recovery = max(pod_recovery_times)
            reschedule = max(p.get("pod_rescheduling_time") or 0 for p in recovered if isinstance(p, dict))
            readiness = max(p.get("pod_readiness_time") or 0 for p in recovered if isinstance(p, dict))
        else:
            total_recovery = None
            reschedule = None
            readiness = None

        vmi_recovered = s.get("affected_vmis", {}).get("recovered", [])
        vmi_unrecovered = s.get("affected_vmis", {}).get("unrecovered", [])
        all_vmis = [_extract_vmi_name(v) for v in vmi_unrecovered + vmi_recovered]
        vmis_error = s.get("affected_vmis", {}).get("error")

        vmi_recovery_times = [
            v.get("total_recovery_time")
            for v in vmi_recovered
            if isinstance(v, dict) and v.get("total_recovery_time") is not None
        ]
        if vmi_recovery_times:
            vmi_total_recovery = max(vmi_recovery_times)
            vmi_reschedule = max(v.get("vmi_rescheduling_time") or 0 for v in vmi_recovered if isinstance(v, dict))
            vmi_readiness = max(v.get("vmi_readiness_time") or 0 for v in vmi_recovered if isinstance(v, dict))
        else:
            vmi_total_recovery = None
            vmi_reschedule = None
            vmi_readiness = None

        affected_nodes = s.get("affected_nodes", [])
        node_list = []
        for node in affected_nodes:
            if isinstance(node, dict):
                node_list.append({
                    "node_name": node.get("node_name", "N/A"),
                    "node_id": node.get("node_id", ""),
                    "stopped_time": node.get("stopped_time"),
                    "running_time": node.get("running_time"),
                    "terminating_time": node.get("terminating_time"),
                    "not_ready_time": node.get("not_ready_time"),
                    "ready_time": node.get("ready_time"),
                })

        # Cluster events with full detail
        raw_events = s.get("cluster_events") or []
        cluster_events = []
        for event in raw_events:
            if isinstance(event, dict):
                cluster_events.append({
                    "reason": event.get("reason", "N/A"),
                    "message": event.get("message", "N/A"),
                    "type": event.get("type", ""),
                    "namespace": event.get("namespace", ""),
                    "source_component": event.get("source_component", ""),
                    "involved_object_kind": event.get("involved_object_kind", ""),
                    "involved_object_name": event.get("involved_object_name", ""),
                    "creation": event.get("creation", ""),
                })
            else:
                cluster_events.append({"reason": "Event", "message": str(event)})

        # Additional telemetry (HTTP load test metrics)
        additional_telemetry = s.get("additional_telemetry")

        scenarios.append({
            "scenario": s.get("scenario", "N/A"),
            "scenario_type": s.get("scenario_type", "N/A"),
            "selectors": selectors,
            "namespaces": ns_list,
            "exclude_labels": exclude_labels,
            "cloud_types": cloud_types,
            "all_pods": all_pods,
            "pods_error": pods_error,
            "exit_status": str(s.get("exit_status", "1")),
            "recovered_count": len(recovered),
            "unrecovered_count": len(unrecovered),
            "total_recovery_time": total_recovery,
            "rescheduling_time": reschedule,
            "readiness_time": readiness,
            "all_vmis": all_vmis,
            "vmis_error": vmis_error,
            "vmi_recovered_count": len(vmi_recovered),
            "vmi_unrecovered_count": len(vmi_unrecovered),
            "vmi_total_recovery_time": vmi_total_recovery,
            "vmi_rescheduling_time": vmi_reschedule,
            "vmi_readiness_time": vmi_readiness,
            "affected_nodes": node_list,
            "cluster_events": cluster_events,
            "additional_telemetry": additional_telemetry,
        })

    resiliency = telemetry.get("overall_resiliency_report", {})
    total_slos = resiliency.get("total_slos", 0)
    passed_slos = resiliency.get("passed_slos", 0)

    critical_alerts_raw = chaos_output.get("critical_alerts") or {}
    chaos_alerts, post_chaos_alerts = _extract_critical_alerts(critical_alerts_raw)
    total_alert_count = len(chaos_alerts) + len(post_chaos_alerts)

    error_logs = telemetry.get("error_logs") or []

    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    template = env.get_template("report.html")

    scenario_slo_details = chaos_output.get("scenario_slo_details", [])

    security_flags = []
    if telemetry.get("fips_enabled"):
        security_flags.append("FIPS")
    if telemetry.get("etcd_encryption_enabled"):
        security_flags.append("etcd encryption")
    if telemetry.get("ipsec_enabled"):
        security_flags.append("IPSec")

    node_infos = telemetry.get("node_summary_infos") or []
    health_checks = telemetry.get("health_checks")
    virt_checks = telemetry.get("virt_checks")
    post_virt_checks = telemetry.get("post_virt_checks")

    SCENARIO_TYPE_DOCS = {
        "hog_scenarios": "https://krkn-chaos.dev/docs/scenarios/hog-scenarios/", 
        "application_outages_scenarios": "https://krkn-chaos.dev/docs/scenarios/application-outages/", 
        "container_scenarios": "https://krkn-chaos.dev/docs/scenarios/container-scenarios/", 
        "pod_network_scenarios": "https://krkn-chaos.dev/docs/scenarios/pod-network-scenario/", 
        "pod_disruption_scenarios": "https://krkn-chaos.dev/docs/scenarios/service-disruption-scenarios/", 
        "node_scenarios": "https://krkn-chaos.dev/docs/scenarios/node-scenarios/", 
        "time_scenarios": "https://krkn-chaos.dev/docs/scenarios/time-scenarios/", 
        "cluster_shut_down_scenarios": "https://krkn-chaos.dev/docs/scenarios/power-outage-scenarios/", 
        "service_disruption_scenarios": "https://krkn-chaos.dev/docs/scenarios/service-disruption-scenarios/", 
        "zone_outages_scenarios": "https://krkn-chaos.dev/docs/scenarios/zone-outage-scenarios/", 
        "pvc_scenarios": "https://krkn-chaos.dev/docs/scenarios/pvc-scenario/", 
        "storage_throttle_scenarios": "https://krkn-chaos.dev/docs/scenarios/storage-throttle-scenario/", 
        "network_chaos_scenarios": "https://krkn-chaos.dev/docs/scenarios/network-chaos-scenario/", 
        "service_hijacking_scenarios": "https://krkn-chaos.dev/docs/scenarios/service-hijacking-scenario/", 
        "syn_flood_scenarios": "https://krkn-chaos.dev/docs/scenarios/syn-flood-scenario/", 
        "network_chaos_ng_scenarios": "https://krkn-chaos.dev/docs/scenarios/network-chaos-ng-scenarios/", 
        "kubevirt_vm_outage": "https://krkn-chaos.dev/docs/scenarios/kubevirt-vm-outage-scenario/",
        "http_load_scenarios": "https://krkn-chaos.dev/docs/scenarios/http-load-scenario/"
    }

    html_content = template.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        run_uuid=telemetry.get("run_uuid", "N/A"),
        cluster_version=telemetry.get("cluster_version", "N/A"),
        cloud_infrastructure=telemetry.get("cloud_infrastructure", "N/A"),
        cloud_type=telemetry.get("cloud_type", "N/A"),
        time_window=time_window,
        total_node_count=telemetry.get("total_node_count", "N/A"),
        network_plugins=telemetry.get("network_plugins") or [],
        security_flags=security_flags,
        node_summary_infos=node_infos,
        health_checks=health_checks,
        virt_checks=virt_checks,
        post_virt_checks=post_virt_checks,
        scenarios=scenarios,
        total_slos=total_slos,
        passed_slos=passed_slos,
        failed_slos=total_slos - passed_slos,
        scenario_slo_details=scenario_slo_details,
        critical_alert_count=total_alert_count,
        chaos_alerts=chaos_alerts,
        post_chaos_alerts=post_chaos_alerts,
        error_logs=error_logs,
        per_scenario_scores=resiliency.get("scenarios", {}),
        overall_score=resiliency.get("resiliency_score", "N/A"),
        scenario_type_docs=SCENARIO_TYPE_DOCS
    )

    HTML(string=html_content).write_pdf(output_path)
    return output_path
