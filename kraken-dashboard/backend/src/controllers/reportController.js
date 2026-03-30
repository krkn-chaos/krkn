const { reports } = require("../store");

// Escape HTML special chars to prevent XSS in generated report
function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

exports.listReports = (_req, res) => {
  const list = Array.from(reports.values()).sort(
    (a, b) => new Date(b.generatedAt) - new Date(a.generatedAt)
  );
  res.json(list);
};

exports.getReport = (req, res) => {
  const report = reports.get(req.params.id);
  if (!report) return res.status(404).json({ error: "Report not found" });
  res.json(report);
};

exports.downloadJson = (req, res) => {
  const report = reports.get(req.params.id);
  if (!report) return res.status(404).json({ error: "Report not found" });
  // Sanitize id for use in filename — only allow alphanumeric, dash, underscore
  const safeId = req.params.id.replace(/[^a-zA-Z0-9\-_]/g, "_");
  res.setHeader("Content-Disposition", `attachment; filename="report-${safeId}.json"`);
  res.setHeader("Content-Type", "application/json");
  res.send(JSON.stringify(report, null, 2));
};

exports.downloadHtml = (req, res) => {
  const report = reports.get(req.params.id);
  if (!report) return res.status(404).json({ error: "Report not found" });

  const sloRows = Object.entries(report.sloResults || {})
    .map(([name, passed]) => `
      <tr>
        <td>${esc(name)}</td>
        <td class="${passed ? "pass" : "fail"}">${passed ? "✅ PASS" : "❌ FAIL"}</td>
      </tr>`)
    .join("");

  const logLines = (report.logs || []).map((l) => `<div class="log-line">${esc(l)}</div>`).join("");

  const scoreColor = report.resiliencyScore >= 70 ? "#22c55e" : report.resiliencyScore >= 50 ? "#f59e0b" : "#ef4444";

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Kraken Report — ${esc(report.scenarioName)}</title>
  <style>
    body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 2rem; }
    h1 { color: #f97316; } h2 { color: #94a3b8; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }
    .card { background: #1e293b; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }
    .score { font-size: 3rem; font-weight: bold; color: ${scoreColor}; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #334155; }
    th { color: #94a3b8; font-size: 0.85rem; text-transform: uppercase; }
    .pass { color: #22c55e; } .fail { color: #ef4444; }
    .log-line { font-family: monospace; font-size: 0.85rem; padding: 0.2rem 0; color: #94a3b8; }
    .badge { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; }
    .badge-completed { background: #14532d; color: #22c55e; }
    .badge-failed { background: #450a0a; color: #ef4444; }
  </style>
</head>
<body>
  <h1>🌪 Kraken Chaos Report</h1>
  <div class="card">
    <h2>Summary</h2>
    <p><strong>Scenario:</strong> ${esc(report.scenarioName)}</p>
    <p><strong>Status:</strong> <span class="badge badge-${esc(report.status.toLowerCase())}">${esc(report.status)}</span></p>
    <p><strong>Generated:</strong> ${esc(new Date(report.generatedAt).toLocaleString())}</p>
    <p><strong>Duration:</strong> ${esc(report.duration)}s</p>
    <p><strong>Resiliency Score:</strong> <span class="score">${report.resiliencyScore ?? "N/A"}</span><span style="color:#94a3b8">/100</span></p>
  </div>
  <div class="card">
    <h2>SLO Results</h2>
    <table><thead><tr><th>SLO Name</th><th>Result</th></tr></thead>
    <tbody>${sloRows}</tbody></table>
  </div>
  <div class="card">
    <h2>Score Breakdown</h2>
    <table><thead><tr><th>Category</th><th>Passed</th><th>Failed</th></tr></thead>
    <tbody>
      <tr><td>Critical</td><td class="pass">${report.breakdown?.critical_passed ?? 0}</td><td class="fail">${report.breakdown?.critical_failed ?? 0}</td></tr>
      <tr><td>Warning</td><td class="pass">${report.breakdown?.warning_passed ?? 0}</td><td class="fail">${report.breakdown?.warning_failed ?? 0}</td></tr>
    </tbody></table>
  </div>
  <div class="card">
    <h2>Logs</h2>
    ${logLines}
  </div>
</body>
</html>`;

  const safeId = req.params.id.replace(/[^a-zA-Z0-9\-_]/g, "_");
  res.setHeader("Content-Disposition", `attachment; filename="report-${safeId}.html"`);
  res.setHeader("Content-Type", "text/html");
  res.send(html);
};
