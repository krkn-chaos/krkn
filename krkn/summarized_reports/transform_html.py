from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape

from krkn.summarized_reports.transform import (
    SCENARIO_TYPE_DOCS,
    _extract_critical_alerts,
    _extract_pod_name,
    _extract_scenario_params,
    _extract_vmi_name,
    format_window,
)

_HTML_CSS = """
:root {
    --red-header: #cc0000;
    --pass-green: #1a7f37;
    --fail-red: #cf222e;
    --warn-yellow: #9a6700;
    --header-bg: #e8e8e8;
    --border-color: #cccccc;
    --text-color: #1a1a1a;
    --subtitle-color: #666666;
    --bg-color: #ffffff;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 14px; color: var(--text-color); background: var(--bg-color);
    max-width: 960px; margin: 0 auto; padding: 24px;
}
h1 { font-size: 22px; text-align: center; margin-bottom: 4px; }
.subtitle { font-size: 12px; text-align: center; color: var(--subtitle-color); margin-bottom: 24px; }
.section { margin-bottom: 24px; }
.section-header {
    font-size: 15px; font-weight: 600; color: #222;
    border-bottom: 2px solid var(--red-header);
    padding-bottom: 4px; margin-bottom: 12px; cursor: pointer;
    user-select: none;
}
.section-header::before { content: "\\25BC  "; font-size: 10px; }
.section.collapsed .section-header::before { content: "\\25B6  "; }
.section.collapsed .section-body { display: none; }
.subsection-header { font-size: 13px; font-weight: 600; color: #333; margin: 12px 0 6px; }
table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
th, td {
    border: 1px solid var(--border-color); padding: 6px 10px;
    text-align: left; vertical-align: top; font-size: 13px;
}
th { background: var(--header-bg); font-weight: 600; }
.kv-table th { width: 35%; background: var(--header-bg); }
.kv-table td { width: 65%; }
.small-table th, .small-table td { font-size: 11px; padding: 4px 6px; }
.span-header { background: var(--header-bg); font-weight: 600; text-align: left; }
.badge-pass { color: var(--pass-green); font-weight: 700; }
.badge-fail { color: var(--fail-red); font-weight: 700; }
.badge-warn { color: var(--warn-yellow); font-weight: 700; }
.recovery-detail { font-size: 11px; color: #555; }
a { color: #0969da; }
.overall-score {
    text-align: center; font-size: 20px; font-weight: 700;
    border: 2px solid var(--border-color); border-radius: 6px;
    padding: 14px; margin-top: 10px;
}
.score-green { color: var(--pass-green); }
.score-yellow { color: var(--warn-yellow); }
.score-red { color: var(--fail-red); }
.error-text { color: var(--fail-red); font-style: italic; }
.muted { color: #555; }
@media print {
    body { max-width: 100%; padding: 12px; }
    .section.collapsed .section-body { display: block !important; }
    .section-header::before { content: "" !important; }
}
"""

_HTML_JS = """
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.section-header').forEach(function(header) {
        header.addEventListener('click', function() {
            this.parentElement.classList.toggle('collapsed');
        });
    });
});
"""


def _h(text):
    return _xml_escape(str(text))


def _html_badge(text, passed):
    cls = "badge-pass" if passed else "badge-fail"
    return f'<span class="{cls}">{_h(text)}</span>'


def _html_score_class(score):
    if isinstance(score, (int, float)):
        if score >= 90:
            return "score-green"
        if score >= 70:
            return "score-yellow"
        return "score-red"
    return ""


def _html_kv_table(rows):
    if not rows:
        return ""
    parts = ['<table class="kv-table">']
    for k, v in rows:
        parts.append(f"<tr><th>{k}</th><td>{v}</td></tr>")
    parts.append("</table>")
    return "\n".join(parts)


def _html_data_table(headers, rows, small=False, span_header=None):
    cls = ' class="small-table"' if small else ""
    parts = [f"<table{cls}>"]
    if span_header:
        parts.append(
            f'<tr><td class="span-header" colspan="{len(headers)}">'
            f"{_h(span_header)}</td></tr>"
        )
    parts.append("<tr>" + "".join(f"<th>{_h(h)}</th>" for h in headers) + "</tr>")
    for row in rows:
        parts.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    parts.append("</table>")
    return "\n".join(parts)


def _html_section(title, body):
    return (
        f'<div class="section">'
        f'<div class="section-header">{_h(title)}</div>'
        f'<div class="section-body">{body}</div>'
        f"</div>"
    )


def build_chaos_report_html(chaos_output: dict, output_path: str) -> str:
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
    failed_slos = total_slos - passed_slos
    per_scenario_scores = resiliency.get("scenarios", {})
    overall_score = resiliency.get("resiliency_score", "N/A")

    parts = []

    # 1. Title
    parts.append("<h1>KRKN Run Summary</h1>")
    parts.append(
        f'<div class="subtitle">Generated {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>'
    )

    # 2. Run Metadata
    meta_rows = [
        ("Run UUID", _h(telemetry.get("run_uuid", "N/A"))),
        ("Cluster Version", _h(telemetry.get("cluster_version", "N/A"))),
        ("Infrastructure", _h(telemetry.get("cloud_infrastructure", "N/A"))),
        ("Cloud Type", _h(telemetry.get("cloud_type", "N/A"))),
        ("Time Window", _h(time_window)),
        ("Total Nodes", _h(str(telemetry.get("total_node_count", "N/A")))),
    ]
    network_plugins = telemetry.get("network_plugins") or []
    if network_plugins:
        meta_rows.append(("Network Plugins", _h(", ".join(network_plugins))))
    if security_flags:
        meta_rows.append(("Security", _h(", ".join(security_flags))))
    parts.append(_html_section("Run Metadata", _html_kv_table(meta_rows)))

    # 3. Cluster Overview
    if node_infos:
        rows = []
        for ni in node_infos:
            rows.append([
                _h(ni.get("nodes_type") or "N/A"),
                _h(str(ni.get("count") or "N/A")),
                _h(ni.get("instance_type") or "N/A"),
                _h(ni.get("architecture") or "N/A"),
                _h(ni.get("kubelet_version") or "N/A"),
                _h(ni.get("os_version") or "N/A"),
            ])
        parts.append(_html_section(
            "Cluster Overview",
            _html_data_table(["Type", "Count", "Instance", "Architecture", "Kubelet", "OS"], rows),
        ))

    # 4. Targets
    targets_body = []
    for s in scenarios:
        passed = s["exit_status"] == "0"
        scenario_label = _h(s["scenario"])
        type_label = _h(s["scenario_type"])
        doc_url = SCENARIO_TYPE_DOCS.get(s["scenario_type"], "")
        if doc_url:
            type_link = f'<a href="{_h(doc_url)}" target="_blank">{type_label}</a>'
        else:
            type_link = type_label

        target_rows = [
            (f"{scenario_label} ({type_link})", _html_badge("PASS" if passed else "FAIL", passed)),
        ]
        if s["selectors"]:
            target_rows.append(("Label Selector", _h(", ".join(s["selectors"]))))
        if s["namespaces"]:
            target_rows.append(("Namespace", _h(", ".join(s["namespaces"]))))
        if s["exclude_labels"]:
            target_rows.append(("Exclude Label", _h(", ".join(s["exclude_labels"]))))
        if s["cloud_types"]:
            target_rows.append(("Cloud Type", _h(", ".join(s["cloud_types"]))))

        if s["all_pods"]:
            pod_text = "<br>".join(_h(p) for p in s["all_pods"])
            if s["pods_error"]:
                pod_text += f'<br><span class="error-text">Monitoring error: {_h(s["pods_error"])}</span>'
            target_rows.append(("Disrupted Pods", pod_text))
        elif s.get("pods_error"):
            target_rows.append(("Pod Monitoring", f'<span class="error-text">Error: {_h(s["pods_error"])}</span>'))

        if s["all_vmis"]:
            vmi_text = "<br>".join(_h(v) for v in s["all_vmis"])
            if s.get("vmis_error"):
                vmi_text += f'<br><span class="error-text">Monitoring error: {_h(s["vmis_error"])}</span>'
            target_rows.append(("Disrupted VMIs", vmi_text))
        elif s.get("vmis_error"):
            target_rows.append(("VMI Monitoring", f'<span class="error-text">Error: {_h(s["vmis_error"])}</span>'))

        if s["affected_nodes"]:
            node_lines = []
            for n in s["affected_nodes"]:
                label = _h(n["node_name"])
                if n.get("node_id"):
                    label += f" ({_h(n['node_id'])})"
                node_lines.append(label)
            target_rows.append(("Affected Nodes", "<br>".join(node_lines)))

        targets_body.append(_html_kv_table(target_rows))
    parts.append(_html_section("Targets", "\n".join(targets_body)))

    # 5. Key Metrics (pod recovery)
    metrics_body = []
    has_pods = any(s["recovered_count"] or s["unrecovered_count"] for s in scenarios)
    if has_pods:
        rows = []
        for s in scenarios:
            if not (s["recovered_count"] or s["unrecovered_count"]):
                continue
            recovery_cell = ""
            if s["total_recovery_time"] is not None:
                recovery_cell = (
                    f'{s["total_recovery_time"]:.2f}s'
                    f'<br><span class="recovery-detail">'
                    f'Rescheduling: {(s["rescheduling_time"] or 0):.2f}s<br>'
                    f'Readiness: {(s["readiness_time"] or 0):.2f}s</span>'
                )
            rows.append([
                _h(s["scenario"]),
                _h(str(s["recovered_count"])),
                _h(str(s["unrecovered_count"])),
                recovery_cell,
            ])
        metrics_body.append(_html_data_table(
            ["Scenario", "Pods Recovered", "Pods Unrecovered", "Total Recovery Time"], rows,
        ))

    # 6. VMI Recovery
    has_vmis = any(s["all_vmis"] for s in scenarios)
    if has_vmis:
        metrics_body.append('<div class="subsection-header">VMI Recovery</div>')
        rows = []
        for s in scenarios:
            if not s["all_vmis"]:
                continue
            recovery_cell = ""
            if s["vmi_total_recovery_time"] is not None:
                recovery_cell = (
                    f'{s["vmi_total_recovery_time"]:.2f}s'
                    f'<br><span class="recovery-detail">'
                    f'Rescheduling: {(s["vmi_rescheduling_time"] or 0):.2f}s<br>'
                    f'Readiness: {(s["vmi_readiness_time"] or 0):.2f}s</span>'
                )
            rows.append([
                _h(s["scenario"]),
                _h(str(s["vmi_recovered_count"])),
                _h(str(s["vmi_unrecovered_count"])),
                recovery_cell,
            ])
        metrics_body.append(_html_data_table(
            ["Scenario", "VMIs Recovered", "VMIs Unrecovered", "Total Recovery Time"], rows,
        ))

    # 7. Node Recovery
    has_nodes = any(s["affected_nodes"] for s in scenarios)
    if has_nodes:
        metrics_body.append('<div class="subsection-header">Node Recovery</div>')
        for s in scenarios:
            if not s["affected_nodes"]:
                continue
            has_id = any(n.get("node_id") for n in s["affected_nodes"])
            if has_id:
                headers = ["Node", "Instance", "Stopped", "Running", "Terminated", "Not Ready", "Ready"]
            else:
                headers = ["Node", "Stopped", "Running", "Terminated", "Not Ready", "Ready"]
            rows = []
            for n in s["affected_nodes"]:
                row = [_h(n["node_name"])]
                if has_id:
                    row.append(_h(n.get("node_id", "")))
                for key in ["stopped_time", "running_time", "terminating_time", "not_ready_time", "ready_time"]:
                    val = n.get(key)
                    row.append(f"{val:.2f}s" if val is not None else "")
                rows.append(row)
            metrics_body.append(_html_data_table(
                headers, rows, small=True, span_header=s["scenario"],
            ))

    # 8. Load Test Metrics
    has_additional = any(s.get("additional_telemetry") for s in scenarios)
    if has_additional:
        metrics_body.append('<div class="subsection-header">Load Test Metrics</div>')
        for s in scenarios:
            if not s.get("additional_telemetry"):
                continue
            metrics_body.append(f'<div class="subsection-header">{_h(s["scenario"])}</div>')
            kv_rows = [(_h(k), _h(str(v))) for k, v in s["additional_telemetry"].items()]
            metrics_body.append(_html_kv_table(kv_rows))

    # 9. Cluster Events
    has_events = any(s["cluster_events"] for s in scenarios)
    if has_events:
        metrics_body.append('<div class="subsection-header">Cluster Events</div>')
        for s in scenarios:
            if not s["cluster_events"]:
                continue
            events = s["cluster_events"][:10]
            rows = []
            for e in events:
                obj_ref = ""
                if e.get("involved_object_kind"):
                    obj_ref = f'{_h(e["involved_object_kind"])}/{_h(e.get("involved_object_name", ""))}'
                type_cell = _h(e.get("type", ""))
                if e.get("type") == "Warning":
                    type_cell = '<span class="badge-warn"><b>Warning</b></span>'
                rows.append([
                    type_cell,
                    _h(e.get("reason", "")),
                    obj_ref,
                    _h(e.get("message", "")),
                    _h(e.get("namespace", "")),
                ])
            metrics_body.append(_html_data_table(
                ["Type", "Reason", "Object", "Message", "Namespace"],
                rows,
                span_header=f'{s["scenario"]} ({len(s["cluster_events"])} events)',
            ))
            if len(s["cluster_events"]) > 10:
                metrics_body.append(f'<p class="muted">... and {len(s["cluster_events"]) - 10} more</p>')

    if metrics_body:
        parts.append(_html_section("Key Metrics", "\n".join(metrics_body)))

    # 10. Health Checks
    if health_checks:
        rows = []
        for check in health_checks:
            if isinstance(check, dict):
                url = check.get("url") or check.get("name") or check.get("check_name", "")
                status_code = str(check.get("status_code", ""))
                duration = ""
                if check.get("duration") is not None and check.get("duration") != "":
                    duration = f"{float(check['duration']):.2f}s"
                passed = check.get("status") or check.get("passed")
                rows.append([
                    _h(url), _h(status_code), duration,
                    _html_badge("PASS" if passed else "FAIL", bool(passed)),
                ])
            else:
                rows.append([_h(str(check)), "", "", ""])
        parts.append(_html_section(
            "Health Checks",
            _html_data_table(["URL / Endpoint", "Status Code", "Duration", "Result"], rows),
        ))

    # 11. KubeVirt Health Checks (Pre-Chaos)
    if virt_checks:
        rows = []
        for check in virt_checks:
            if isinstance(check, dict):
                passed = not (check.get("status") is not None and not check.get("status"))
                rows.append([
                    _h(check.get("vm_name") or check.get("vmi_name") or check.get("name", "")),
                    _h(check.get("namespace", "")),
                    _h(check.get("node_name", "")),
                    _h(check.get("ip_address", "")),
                    f"{float(check['duration']):.2f}s" if check.get("duration") not in (None, "") else "",
                    _html_badge("PASS" if passed else "FAIL", passed),
                ])
            else:
                rows.append([_h(str(check)), "", "", "", "", ""])
        parts.append(_html_section(
            "KubeVirt Health Checks (Pre-Chaos)",
            _html_data_table(["VM Name", "Namespace", "Node", "IP Address", "Duration", "Result"], rows),
        ))

    # 12. KubeVirt Health Checks (Post-Chaos)
    if post_virt_checks:
        rows = []
        for check in post_virt_checks:
            if isinstance(check, dict):
                passed = not (check.get("status") is not None and not check.get("status"))
                new_ip = ""
                if check.get("new_ip_address") and check.get("new_ip_address") != check.get("ip_address"):
                    new_ip = _h(check["new_ip_address"])
                rows.append([
                    _h(check.get("vm_name") or check.get("vmi_name") or check.get("name", "")),
                    _h(check.get("namespace", "")),
                    _h(check.get("node_name", "")),
                    _h(check.get("ip_address", "")),
                    new_ip,
                    f"{float(check['duration']):.2f}s" if check.get("duration") not in (None, "") else "",
                    _html_badge("PASS" if passed else "FAIL", passed),
                ])
            else:
                rows.append([_h(str(check)), "", "", "", "", "", ""])
        parts.append(_html_section(
            "KubeVirt Health Checks (Post-Chaos)",
            _html_data_table(
                ["VM Name", "Namespace", "Node", "IP Address", "New IP", "Duration", "Result"], rows,
            ),
        ))

    # 13. Alerts & SLOs
    alerts_body = []
    failed_slo_val = _h(str(failed_slos)) if failed_slos == 0 else f'<span class="badge-fail"><b>{failed_slos}</b></span>'
    alert_val = "None" if total_alert_count == 0 else f'<span class="badge-fail"><b>{total_alert_count}</b></span>'
    alerts_body.append(_html_kv_table([
        ("SLOs Evaluated", _h(str(total_slos))),
        ("SLOs Passed", _h(f"{passed_slos} / {total_slos}")),
        ("SLOs Failed", failed_slo_val),
        ("Critical Alerts", alert_val),
    ]))

    def _build_html_alert_table(title, alerts):
        if not alerts:
            return
        alerts_body.append(f'<div class="subsection-header">{_h(title)}</div>')
        rows = []
        for alert in alerts:
            if isinstance(alert, dict):
                rows.append([
                    _h(alert.get("alertname", "N/A")),
                    _h(alert.get("severity", "N/A")),
                    _h(alert.get("namespace", "N/A")),
                    _h(alert.get("alertstate", "N/A")),
                ])
            else:
                rows.append([_h(str(alert)), "", "", ""])
        alerts_body.append(_html_data_table(["Alert Name", "Severity", "Namespace", "State"], rows))

    _build_html_alert_table("Critical Alerts (During Chaos)", chaos_alerts)
    _build_html_alert_table("Critical Alerts (Post Chaos)", post_chaos_alerts)

    # 14. Error Logs
    if error_logs:
        alerts_body.append(f'<div class="subsection-header">Error Logs ({len(error_logs)})</div>')
        rows = []
        for log_entry in error_logs[:20]:
            if isinstance(log_entry, dict):
                rows.append([
                    _h(log_entry.get("timestamp", "-")),
                    _h((log_entry.get("message") or str(log_entry))[:300]),
                ])
            else:
                rows.append(["-", _h(str(log_entry)[:300])])
        alerts_body.append(_html_data_table(["Timestamp", "Message"], rows))
        if len(error_logs) > 20:
            alerts_body.append(f'<p class="muted">... and {len(error_logs) - 20} more</p>')

    parts.append(_html_section("Alerts & SLOs", "\n".join(alerts_body)))

    # 15. Failed SLOs
    if scenario_slo_details:
        failed_entries = []
        for entry in scenario_slo_details:
            failed = [s for s in entry.get("slo_details", []) if not s["passed"]]
            if failed:
                failed_entries.append({"scenario": entry["scenario"], "slo_details": failed})
        if failed_entries:
            slo_body = []
            for entry in failed_entries:
                slo_body.append(f'<div class="subsection-header">{_h(entry["scenario"])}</div>')
                rows = []
                for slo in entry["slo_details"]:
                    rows.append([_h(slo["name"]), _h(slo.get("severity", "unknown")), _html_badge("FAIL", False)])
                slo_body.append(_html_data_table(["SLO", "Severity", "Status"], rows))
            parts.append(_html_section("Failed SLOs", "\n".join(slo_body)))

    # 16. Resiliency Score
    score_body = []
    if per_scenario_scores:
        rows = []
        for name, score in per_scenario_scores.items():
            cls = _html_score_class(score)
            rows.append([
                _h(name),
                f'<span class="{cls}"><b>{_h(str(score))} / 100</b></span>',
            ])
        score_body.append(_html_data_table(["Scenario", "Score"], rows))

    cls = _html_score_class(overall_score)
    score_body.append(f'<div class="overall-score {cls}">Overall: {_h(str(overall_score))} / 100</div>')
    parts.append(_html_section("Resiliency Score", "\n".join(score_body)))

    html = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>KRKN Run Summary</title>\n"
        f"<style>{_HTML_CSS}</style>\n"
        "</head>\n<body>\n"
        + "\n".join(parts)
        + f"\n<script>{_HTML_JS}</script>\n"
        "</body>\n</html>"
    )

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return output_path
