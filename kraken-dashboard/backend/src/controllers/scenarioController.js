const { v4: uuidv4 } = require("uuid");
const { scenarios, reports, generateReport, simulateRun } = require("../store");

exports.listScenarios = (_req, res) => {
  const list = Array.from(scenarios.values()).sort(
    (a, b) => new Date(b.startTime) - new Date(a.startTime)
  );
  res.json(list);
};

exports.getScenario = (req, res) => {
  const scenario = scenarios.get(req.params.id);
  if (!scenario) return res.status(404).json({ error: "Scenario not found" });
  res.json(scenario);
};

exports.createScenario = (req, res) => {
  const { name, type, chaosType, target, namespace, duration, yamlConfig } = req.body;

  if (!name || !type || !chaosType) {
    return res.status(400).json({ error: "name, type, and chaosType are required" });
  }

  // Trim string inputs
  const trimmedName = String(name).trim();
  const trimmedNamespace = String(namespace || "default").trim();

  if (!trimmedName) {
    return res.status(400).json({ error: "name cannot be blank" });
  }

  const id = uuidv4();
  const scenario = {
    id,
    name: trimmedName,
    type: String(type).trim(),
    chaosType: String(chaosType).trim(),
    target: String(target || "pod").trim(),
    namespace: trimmedNamespace,
    duration: parseInt(duration, 10) || 60,
    yamlConfig: yamlConfig || null,
    status: "Running",
    startTime: new Date().toISOString(),
    endTime: null,
    resiliencyScore: null,
    logs: [
      `[INFO] Scenario "${trimmedName}" created`,
      `[INFO] Chaos type: ${chaosType}`,
      `[INFO] Target: ${target || "pod"} in namespace: ${trimmedNamespace}`,
      `[INFO] Duration: ${duration || 60}s`,
    ],
  };

  scenarios.set(id, scenario);

  req.io.emit("scenario:created", scenario);
  req.io.emit("scenario:log", { id, message: `[INFO] Scenario "${trimmedName}" started` });

  // Use shared simulateRun with io so clients get live events
  simulateRun(id, req.io);

  res.status(201).json(scenario);
};

exports.deleteScenario = (req, res) => {
  if (!scenarios.has(req.params.id)) {
    return res.status(404).json({ error: "Scenario not found" });
  }
  scenarios.delete(req.params.id);
  res.json({ message: "Deleted" });
};
