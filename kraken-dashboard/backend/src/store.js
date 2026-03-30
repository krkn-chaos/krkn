/**
 * In-memory store for scenarios and reports.
 * In production, replace with a real database.
 */
const { v4: uuidv4 } = require("uuid");

const scenarios = new Map();
const reports = new Map();

// generateReport must be defined before seedDemoData calls it
function generateReport(scenario) {
  return {
    id: `report-${scenario.id}`,
    scenarioId: scenario.id,
    scenarioName: scenario.name,
    generatedAt: new Date().toISOString(),
    status: scenario.status,
    duration: scenario.duration,
    resiliencyScore: scenario.resiliencyScore,
    sloResults: {
      "etcd-fsync-latency": scenario.resiliencyScore > 70,
      "api-server-availability": scenario.resiliencyScore > 50,
      "pod-restart-rate": scenario.resiliencyScore > 60,
    },
    breakdown: {
      critical_passed: scenario.resiliencyScore > 70 ? 3 : 1,
      critical_failed: scenario.resiliencyScore > 70 ? 0 : 2,
      warning_passed: scenario.resiliencyScore > 70 ? 5 : 2,
      warning_failed: scenario.resiliencyScore > 70 ? 1 : 4,
    },
    logs: scenario.logs,
  };
}

/**
 * Simulate a running scenario lifecycle with log streaming.
 * io is optional — when called at seed time there's no io yet,
 * so we skip emitting and just mutate the store.
 */
function simulateRun(id, io = null) {
  const scenario = scenarios.get(id);
  if (!scenario) return;

  const logMessages = [
    `[INFO] Initializing chaos injection for ${scenario.chaosType}`,
    `[INFO] Connecting to Kubernetes cluster`,
    `[INFO] Targeting ${scenario.target} in namespace: ${scenario.namespace}`,
    `[INFO] Applying chaos: ${scenario.chaosType}`,
    `[WARN] Monitoring SLOs during chaos window`,
    `[INFO] Chaos injection active — duration: ${scenario.duration}s`,
    `[INFO] Collecting Prometheus metrics`,
    `[INFO] Evaluating SLO thresholds`,
    `[INFO] Chaos window ending`,
    `[INFO] Restoring normal state`,
    `[INFO] Calculating resiliency score`,
  ];

  let msgIndex = 0;
  const interval = Math.max(1000, (scenario.duration * 1000) / logMessages.length);

  const logInterval = setInterval(() => {
    if (!scenarios.has(id)) { clearInterval(logInterval); return; }
    if (msgIndex < logMessages.length) {
      const msg = logMessages[msgIndex++];
      const s = scenarios.get(id);
      s.logs.push(msg);
      if (io) io.emit("scenario:log", { id, message: msg });
    }
  }, interval);

  const completionDelay = Math.min(scenario.duration * 1000, 15000);
  setTimeout(() => {
    clearInterval(logInterval);
    const s = scenarios.get(id);
    if (!s || s.status !== "Running") return;

    const score = Math.floor(Math.random() * 40) + 55; // 55–95
    const finalStatus = score >= 60 ? "Completed" : "Failed";

    s.status = finalStatus;
    s.endTime = new Date().toISOString();
    s.resiliencyScore = score;
    s.logs.push(`[INFO] Scenario ${finalStatus.toLowerCase()} — Resiliency Score: ${score}/100`);

    const report = generateReport(s);
    reports.set(report.id, report);

    if (io) {
      io.emit("scenario:updated", s);
      io.emit("scenario:log", { id, message: s.logs[s.logs.length - 1] });
      io.emit("scenario:completed", { id, status: finalStatus, score });
    }
  }, completionDelay);
}

function seedDemoData() {
  const now = Date.now();

  const completed1 = {
    id: uuidv4(),
    name: "CPU Hog - Worker Nodes",
    type: "hog_scenarios",
    chaosType: "cpu-hog",
    target: "node",
    namespace: "default",
    duration: 60,
    status: "Completed",
    startTime: new Date(now - 3600000).toISOString(),
    endTime: new Date(now - 3540000).toISOString(),
    resiliencyScore: 87,
    logs: [
      "[INFO] Starting CPU hog scenario",
      "[INFO] Targeting 2 worker nodes",
      "[INFO] CPU load set to 90%",
      "[INFO] Scenario completed successfully",
    ],
  };

  const failed1 = {
    id: uuidv4(),
    name: "Pod Network Outage - etcd",
    type: "pod_network_scenarios",
    chaosType: "pod-network-outage",
    target: "pod",
    namespace: "openshift-etcd",
    duration: 120,
    status: "Failed",
    startTime: new Date(now - 7200000).toISOString(),
    endTime: new Date(now - 7080000).toISOString(),
    resiliencyScore: 42,
    logs: [
      "[INFO] Starting pod network outage scenario",
      "[WARN] etcd leader change observed",
      "[ERROR] SLO violation: etcd fsync latency exceeded threshold",
      "[INFO] Scenario ended with failures",
    ],
  };

  // Running scenario — simulation will complete it within 15s
  const running1 = {
    id: uuidv4(),
    name: "Memory Hog - Default NS",
    type: "hog_scenarios",
    chaosType: "memory-hog",
    target: "pod",
    namespace: "default",
    duration: 90,
    status: "Running",
    startTime: new Date(now - 5000).toISOString(),
    endTime: null,
    resiliencyScore: null,
    logs: [
      "[INFO] Starting memory hog scenario",
      "[INFO] Targeting pods in default namespace",
      "[INFO] Memory pressure applied...",
    ],
  };

  [completed1, failed1].forEach((s) => {
    scenarios.set(s.id, s);
    const report = generateReport(s);
    reports.set(report.id, report);
  });

  scenarios.set(running1.id, running1);
  // Kick off simulation so the running scenario actually completes
  simulateRun(running1.id, null);
}

seedDemoData();

module.exports = { scenarios, reports, generateReport, simulateRun };
