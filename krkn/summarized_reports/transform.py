# Copyright 2026 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.flowables import HRFlowable

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
    "vmi_outage": "https://krkn-chaos.dev/docs/scenarios/vmi-outage/",
    "managedcluster_scenarios": "https://krkn-chaos.dev/docs/scenarios/managed-cluster/",
    "storage_throttle_scenarios": "https://krkn-chaos.dev/docs/scenarios/storage-throttle/",
}

# --- ReportLab PDF constants ---
_RED_HEADER = colors.HexColor("#cc0000")
_PASS_GREEN = colors.HexColor("#1a7f37")
_FAIL_RED = colors.HexColor("#cf222e")
_WARN_YELLOW = colors.HexColor("#9a6700")
_HEADER_BG = colors.HexColor("#e8e8e8")
_BORDER_COLOR = colors.HexColor("#cccccc")
_TEXT_COLOR = colors.HexColor("#1a1a1a")

_STYLES = getSampleStyleSheet()
_STYLE_TITLE = ParagraphStyle(
    "ReportTitle", parent=_STYLES["Title"],
    fontSize=18, alignment=TA_CENTER, textColor=_TEXT_COLOR, spaceAfter=4,
)
_STYLE_SUBTITLE = ParagraphStyle(
    "ReportSubtitle", parent=_STYLES["Normal"],
    fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#666666"),
    spaceAfter=16,
)
_STYLE_H2 = ParagraphStyle(
    "SectionHeader", parent=_STYLES["Heading2"],
    fontSize=12, textColor=colors.HexColor("#222222"),
    spaceBefore=18, spaceAfter=4,
)
_STYLE_H3 = ParagraphStyle(
    "SubSectionHeader", parent=_STYLES["Heading3"],
    fontSize=10, textColor=colors.HexColor("#333333"),
    spaceBefore=12, spaceAfter=4,
)
_STYLE_CELL = ParagraphStyle(
    "CellText", parent=_STYLES["Normal"],
    fontSize=9, leading=11, textColor=_TEXT_COLOR,
)
_STYLE_CELL_BOLD = ParagraphStyle(
    "CellTextBold", parent=_STYLE_CELL, fontName="Helvetica-Bold",
)
_STYLE_CELL_SMALL = ParagraphStyle(
    "CellTextSmall", parent=_STYLES["Normal"],
    fontSize=7, leading=9, textColor=_TEXT_COLOR,
)
_STYLE_OVERALL = ParagraphStyle(
    "OverallScore", parent=_STYLES["Normal"],
    fontSize=16, alignment=TA_CENTER, fontName="Helvetica-Bold",
    borderWidth=2, borderColor=_BORDER_COLOR, borderPadding=10,
    spaceBefore=8,
)


def _p(text, style=None):
    return Paragraph(_xml_escape(str(text)), style or _STYLE_CELL)


def _section_header(title):
    return [
        Spacer(1, 10),
        Paragraph(_xml_escape(title), _STYLE_H2),
        HRFlowable(width="100%", thickness=2, color=_RED_HEADER, spaceAfter=8),
    ]


def _subsection_header(title):
    return [Paragraph(_xml_escape(title), _STYLE_H3)]


def _badge(text, passed):
    c = _PASS_GREEN if passed else _FAIL_RED
    return Paragraph(f'<font color="{c}"><b>{_xml_escape(text)}</b></font>', _STYLE_CELL)


def _score_color(score):
    if isinstance(score, (int, float)):
        if score >= 90:
            return _PASS_GREEN
        if score >= 70:
            return _WARN_YELLOW
        return _FAIL_RED
    return _TEXT_COLOR


def _make_kv_table(rows):
    if not rows:
        return []
    avail = A4[0] - 3 * cm
    data = []
    for k, v in rows:
        k_cell = _p(k, _STYLE_CELL_BOLD) if not isinstance(k, Paragraph) else k
        v_cell = _p(v) if not isinstance(v, Paragraph) else v
        data.append([k_cell, v_cell])
    t = Table(data, colWidths=[avail * 0.35, avail * 0.65])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), _HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, _BORDER_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [t, Spacer(1, 12)]


def _make_data_table(headers, rows, col_widths=None, small=False, span_header=None):
    cell_style = _STYLE_CELL_SMALL if small else _STYLE_CELL

    def _cell(val):
        if isinstance(val, Paragraph):
            return val
        return _p(str(val), cell_style)

    data = []
    if span_header:
        data.append([_p(span_header, _STYLE_CELL_BOLD)])
    data.append([_p(h, _STYLE_CELL_BOLD if not small else cell_style) for h in headers])
    for row in rows:
        data.append([_cell(v) for v in row])

    repeat = 2 if span_header else 1
    t = Table(data, colWidths=col_widths, repeatRows=repeat)

    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.5, _BORDER_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5 if not small else 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5 if not small else 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 8 if not small else 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8 if not small else 4),
    ]
    header_row = 0
    if span_header:
        cmds.append(("SPAN", (0, 0), (-1, 0)))
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG))
        header_row = 1
    cmds.append(("BACKGROUND", (0, header_row), (-1, header_row), _HEADER_BG))
    t.setStyle(TableStyle(cmds))
    return [t, Spacer(1, 12)]


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
                f"  {ni.get('nodes_type') or 'N/A':<8} "
                f"{'N/A' if ni.get('count') is None else ni.get('count'):<6} "
                f"{ni.get('instance_type') or 'N/A':<14} "
                f"{ni.get('architecture') or 'N/A':<7} "
                f"{ni.get('kubelet_version') or 'N/A':<10} "
                f"{ni.get('os_version') or 'N/A'}"
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

    avail = A4[0] - 3 * cm
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    f = []

    # 1. Title
    f.append(Paragraph("KRKN Run Summary", _STYLE_TITLE))
    f.append(Paragraph(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        _STYLE_SUBTITLE,
    ))

    # 2. Run Metadata
    f.extend(_section_header("Run Metadata"))
    meta_rows = [
        ("Run UUID", telemetry.get("run_uuid", "N/A")),
        ("Cluster Version", telemetry.get("cluster_version", "N/A")),
        ("Infrastructure", telemetry.get("cloud_infrastructure", "N/A")),
        ("Cloud Type", telemetry.get("cloud_type", "N/A")),
        ("Time Window", time_window),
        ("Total Nodes", str(telemetry.get("total_node_count", "N/A"))),
    ]
    network_plugins = telemetry.get("network_plugins") or []
    if network_plugins:
        meta_rows.append(("Network Plugins", ", ".join(network_plugins)))
    if security_flags:
        meta_rows.append(("Security", ", ".join(security_flags)))
    f.extend(_make_kv_table(meta_rows))

    # 3. Cluster Overview
    if node_infos:
        f.extend(_section_header("Cluster Overview"))
        rows = []
        for ni in node_infos:
            rows.append([
                ni.get("nodes_type", "N/A"),
                str(ni.get("count", "N/A")),
                ni.get("instance_type", "N/A"),
                ni.get("architecture", "N/A"),
                ni.get("kubelet_version", "N/A"),
                ni.get("os_version", "N/A"),
            ])
        f.extend(_make_data_table(
            ["Type", "Count", "Instance", "Architecture", "Kubelet", "OS"], rows,
        ))

    # 4. Targets
    f.extend(_section_header("Targets"))
    for s in scenarios:
        passed = s["exit_status"] == "0"
        scenario_label = _xml_escape(s["scenario"])
        type_label = _xml_escape(s["scenario_type"])
        doc_url = SCENARIO_TYPE_DOCS.get(s["scenario_type"], "")
        if doc_url:
            type_link = f'<a href="{_xml_escape(doc_url)}" color="blue"><u>{type_label}</u></a>'
        else:
            type_link = type_label

        target_rows = [
            (Paragraph(f"{scenario_label} ({type_link})", _STYLE_CELL),
             _badge("PASS" if passed else "FAIL", passed)),
        ]
        if s["selectors"]:
            target_rows.append(("Label Selector", ", ".join(s["selectors"])))
        if s["namespaces"]:
            target_rows.append(("Namespace", ", ".join(s["namespaces"])))
        if s["exclude_labels"]:
            target_rows.append(("Exclude Label", ", ".join(s["exclude_labels"])))
        if s["cloud_types"]:
            target_rows.append(("Cloud Type", ", ".join(s["cloud_types"])))

        if s["all_pods"]:
            pod_text = "<br/>".join(_xml_escape(p) for p in s["all_pods"])
            if s["pods_error"]:
                pod_text += f'<br/><i><font color="{_FAIL_RED}">Monitoring error: {_xml_escape(s["pods_error"])}</font></i>'
            target_rows.append(("Disrupted Pods", Paragraph(pod_text, _STYLE_CELL)))
        elif s.get("pods_error"):
            target_rows.append(("Pod Monitoring",
                Paragraph(f'<font color="{_FAIL_RED}">Error: {_xml_escape(s["pods_error"])}</font>', _STYLE_CELL)))

        if s["all_vmis"]:
            vmi_text = "<br/>".join(_xml_escape(v) for v in s["all_vmis"])
            if s.get("vmis_error"):
                vmi_text += f'<br/><i><font color="{_FAIL_RED}">Monitoring error: {_xml_escape(s["vmis_error"])}</font></i>'
            target_rows.append(("Disrupted VMIs", Paragraph(vmi_text, _STYLE_CELL)))
        elif s.get("vmis_error"):
            target_rows.append(("VMI Monitoring",
                Paragraph(f'<font color="{_FAIL_RED}">Error: {_xml_escape(s["vmis_error"])}</font>', _STYLE_CELL)))

        if s["affected_nodes"]:
            node_lines = []
            for n in s["affected_nodes"]:
                label = n["node_name"]
                if n.get("node_id"):
                    label += f" ({n['node_id']})"
                node_lines.append(_xml_escape(label))
            target_rows.append(("Affected Nodes", Paragraph("<br/>".join(node_lines), _STYLE_CELL)))

        f.extend(_make_kv_table(target_rows))

    # 5. Key Metrics (pod recovery)
    has_pods = any(s["recovered_count"] or s["unrecovered_count"] for s in scenarios)
    if has_pods:
        f.extend(_section_header("Key Metrics"))
        rows = []
        for s in scenarios:
            if not (s["recovered_count"] or s["unrecovered_count"]):
                continue
            recovery_cell = ""
            if s["total_recovery_time"] is not None:
                rt = f'{s["total_recovery_time"]:.2f}s'
                rt += f'<br/><font size="7" color="#555555">Rescheduling: {(s["rescheduling_time"] or 0):.2f}s<br/>Readiness: {(s["readiness_time"] or 0):.2f}s</font>'
                recovery_cell = Paragraph(rt, _STYLE_CELL)
            rows.append([
                s["scenario"],
                str(s["recovered_count"]),
                str(s["unrecovered_count"]),
                recovery_cell or "",
            ])
        f.extend(_make_data_table(
            ["Scenario", "Pods Recovered", "Pods Unrecovered", "Total Recovery Time"],
            rows,
        ))

    # 6. VMI Recovery
    has_vmis = any(s["all_vmis"] for s in scenarios)
    if has_vmis:
        f.extend(_subsection_header("VMI Recovery"))
        rows = []
        for s in scenarios:
            if not s["all_vmis"]:
                continue
            recovery_cell = ""
            if s["vmi_total_recovery_time"] is not None:
                rt = f'{s["vmi_total_recovery_time"]:.2f}s'
                rt += f'<br/><font size="7" color="#555555">Rescheduling: {(s["vmi_rescheduling_time"] or 0):.2f}s<br/>Readiness: {(s["vmi_readiness_time"] or 0):.2f}s</font>'
                recovery_cell = Paragraph(rt, _STYLE_CELL)
            rows.append([
                s["scenario"],
                str(s["vmi_recovered_count"]),
                str(s["vmi_unrecovered_count"]),
                recovery_cell or "",
            ])
        f.extend(_make_data_table(
            ["Scenario", "VMIs Recovered", "VMIs Unrecovered", "Total Recovery Time"],
            rows,
        ))

    # 7. Node Recovery
    has_nodes = any(s["affected_nodes"] for s in scenarios)
    if has_nodes:
        f.extend(_subsection_header("Node Recovery"))
        for s in scenarios:
            if not s["affected_nodes"]:
                continue
            has_id = any(n.get("node_id") for n in s["affected_nodes"])
            if has_id:
                headers = ["Node", "Instance", "Stopped", "Running", "Terminated", "Not Ready", "Ready"]
                cw = [avail * 0.26, avail * 0.15, avail * 0.10, avail * 0.10, avail * 0.13, avail * 0.13, avail * 0.13]
            else:
                headers = ["Node", "Stopped", "Running", "Terminated", "Not Ready", "Ready"]
                cw = [avail * 0.40, avail * 0.12, avail * 0.12, avail * 0.12, avail * 0.12, avail * 0.12]
            rows = []
            for n in s["affected_nodes"]:
                row = [n["node_name"]]
                if has_id:
                    row.append(n.get("node_id", ""))
                for key in ["stopped_time", "running_time", "terminating_time", "not_ready_time", "ready_time"]:
                    val = n.get(key)
                    row.append(f"{val:.2f}s" if val is not None else "")
                rows.append(row)
            f.extend(_make_data_table(headers, rows, col_widths=cw, small=True, span_header=s["scenario"]))

    # 8. Load Test Metrics
    has_additional = any(s.get("additional_telemetry") for s in scenarios)
    if has_additional:
        f.extend(_subsection_header("Load Test Metrics"))
        for s in scenarios:
            if not s.get("additional_telemetry"):
                continue
            rows = [(k, str(v)) for k, v in s["additional_telemetry"].items()]
            f.extend(_subsection_header(s["scenario"]))
            f.extend(_make_kv_table(rows))

    # 9. Cluster Events
    has_events = any(s["cluster_events"] for s in scenarios)
    if has_events:
        f.extend(_subsection_header("Cluster Events"))
        for s in scenarios:
            if not s["cluster_events"]:
                continue
            events = s["cluster_events"][:10]
            rows = []
            for e in events:
                obj_ref = ""
                if e.get("involved_object_kind"):
                    obj_ref = f'{e["involved_object_kind"]}/{e.get("involved_object_name", "")}'
                type_cell = e.get("type", "")
                if type_cell == "Warning":
                    type_cell = Paragraph(f'<font color="{_WARN_YELLOW}"><b>Warning</b></font>', _STYLE_CELL)
                rows.append([
                    type_cell,
                    e.get("reason", ""),
                    obj_ref,
                    e.get("message", ""),
                    e.get("namespace", ""),
                ])
            f.extend(_make_data_table(
                ["Type", "Reason", "Object", "Message", "Namespace"],
                rows,
                span_header=f'{s["scenario"]} ({len(s["cluster_events"])} events)',
            ))
            if len(s["cluster_events"]) > 10:
                f.append(_p(f"... and {len(s['cluster_events']) - 10} more"))

    # 10. Health Checks
    if health_checks:
        f.extend(_section_header("Health Checks"))
        rows = []
        for check in health_checks:
            if isinstance(check, dict):
                url = check.get("url") or check.get("name") or check.get("check_name", "")
                status_code = str(check.get("status_code", ""))
                duration = ""
                if check.get("duration") is not None and check.get("duration") != "":
                    duration = f"{float(check['duration']):.2f}s"
                passed = check.get("status") or check.get("passed")
                rows.append([url, status_code, duration, _badge("PASS" if passed else "FAIL", bool(passed))])
            else:
                rows.append([str(check), "", "", ""])
        f.extend(_make_data_table(
            ["URL / Endpoint", "Status Code", "Duration", "Result"], rows,
        ))

    # 11. KubeVirt Health Checks (Pre-Chaos)
    if virt_checks:
        f.extend(_section_header("KubeVirt Health Checks (Pre-Chaos)"))
        rows = []
        for check in virt_checks:
            if isinstance(check, dict):
                passed = not (check.get("status") is not None and not check.get("status"))
                rows.append([
                    check.get("vm_name") or check.get("vmi_name") or check.get("name", ""),
                    check.get("namespace", ""),
                    check.get("node_name", ""),
                    check.get("ip_address", ""),
                    f"{float(check['duration']):.2f}s" if check.get("duration") not in (None, "") else "",
                    _badge("PASS" if passed else "FAIL", passed),
                ])
            else:
                rows.append([str(check), "", "", "", "", ""])
        f.extend(_make_data_table(
            ["VM Name", "Namespace", "Node", "IP Address", "Duration", "Result"], rows,
        ))

    # 12. KubeVirt Health Checks (Post-Chaos)
    if post_virt_checks:
        f.extend(_section_header("KubeVirt Health Checks (Post-Chaos)"))
        rows = []
        for check in post_virt_checks:
            if isinstance(check, dict):
                passed = not (check.get("status") is not None and not check.get("status"))
                new_ip = ""
                if check.get("new_ip_address") and check.get("new_ip_address") != check.get("ip_address"):
                    new_ip = check["new_ip_address"]
                rows.append([
                    check.get("vm_name") or check.get("vmi_name") or check.get("name", ""),
                    check.get("namespace", ""),
                    check.get("node_name", ""),
                    check.get("ip_address", ""),
                    new_ip,
                    f"{float(check['duration']):.2f}s" if check.get("duration") not in (None, "") else "",
                    _badge("PASS" if passed else "FAIL", passed),
                ])
            else:
                rows.append([str(check), "", "", "", "", "", ""])
        f.extend(_make_data_table(
            ["VM Name", "Namespace", "Node", "IP Address", "New IP", "Duration", "Result"], rows,
        ))

    # 13. Alerts & SLOs
    f.extend(_section_header("Alerts & SLOs"))
    failed_slo_val = _p(str(failed_slos)) if failed_slos == 0 else Paragraph(
        f'<font color="{_FAIL_RED}"><b>{failed_slos}</b></font>', _STYLE_CELL)
    alert_val = _p("None") if total_alert_count == 0 else Paragraph(
        f'<font color="{_FAIL_RED}"><b>{total_alert_count}</b></font>', _STYLE_CELL)
    f.extend(_make_kv_table([
        ("SLOs Evaluated", str(total_slos)),
        ("SLOs Passed", f"{passed_slos} / {total_slos}"),
        ("SLOs Failed", failed_slo_val),
        ("Critical Alerts", alert_val),
    ]))

    def _build_alert_table(title, alerts):
        if not alerts:
            return
        f.extend(_subsection_header(title))
        rows = []
        for alert in alerts:
            if isinstance(alert, dict):
                rows.append([
                    alert.get("alertname", "N/A"),
                    alert.get("severity", "N/A"),
                    alert.get("namespace", "N/A"),
                    alert.get("alertstate", "N/A"),
                ])
            else:
                rows.append([str(alert), "", "", ""])
        f.extend(_make_data_table(["Alert Name", "Severity", "Namespace", "State"], rows))

    _build_alert_table("Critical Alerts (During Chaos)", chaos_alerts)
    _build_alert_table("Critical Alerts (Post Chaos)", post_chaos_alerts)

    # 14. Error Logs
    if error_logs:
        f.extend(_subsection_header(f"Error Logs ({len(error_logs)})"))
        rows = []
        for log_entry in error_logs[:20]:
            if isinstance(log_entry, dict):
                rows.append([
                    log_entry.get("timestamp", "-"),
                    (log_entry.get("message") or str(log_entry))[:300],
                ])
            else:
                rows.append(["-", str(log_entry)[:300]])
        f.extend(_make_data_table(
            ["Timestamp", "Message"], rows,
            col_widths=[avail * 0.25, avail * 0.75],
        ))
        if len(error_logs) > 20:
            f.append(_p(f"... and {len(error_logs) - 20} more"))

    # 15. Failed SLOs
    if scenario_slo_details:
        failed_entries = []
        for entry in scenario_slo_details:
            failed = [s for s in entry.get("slo_details", []) if not s["passed"]]
            if failed:
                failed_entries.append({"scenario": entry["scenario"], "slo_details": failed})
        if failed_entries:
            f.extend(_section_header("Failed SLOs"))
            for entry in failed_entries:
                f.extend(_subsection_header(entry["scenario"]))
                rows = []
                for slo in entry["slo_details"]:
                    rows.append([slo["name"], slo.get("severity", "unknown"), _badge("FAIL", False)])
                f.extend(_make_data_table(["SLO", "Severity", "Status"], rows))

    # 16. Resiliency Score
    f.extend(_section_header("Resiliency Score"))
    if per_scenario_scores:
        rows = []
        for name, score in per_scenario_scores.items():
            c = _score_color(score)
            rows.append([
                name,
                Paragraph(f'<font color="{c}"><b>{score} / 100</b></font>', _STYLE_CELL),
            ])
        f.extend(_make_data_table(["Scenario", "Score"], rows))

    c = _score_color(overall_score)
    overall_style = ParagraphStyle(
        "OverallScoreBox", parent=_STYLE_OVERALL,
        textColor=c,
    )
    f.append(Paragraph(f"Overall: {_xml_escape(str(overall_score))} / 100", overall_style))

    doc.build(f)
    return output_path
