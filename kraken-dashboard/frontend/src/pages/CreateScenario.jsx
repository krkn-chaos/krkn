import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "react-hot-toast";
import { Sliders, Code2, Send, Info } from "lucide-react";
import { api } from "../services/api";

const CHAOS_TYPES = {
  hog_scenarios: ["cpu-hog", "memory-hog", "io-hog"],
  pod_network_scenarios: ["pod-network-outage", "network-latency", "packet-loss"],
  pod_disruption_scenarios: ["pod-delete", "pod-kill"],
  node_scenarios: ["node-stop", "node-reboot", "node-terminate"],
  application_outages_scenarios: ["app-outage"],
  service_disruption_scenarios: ["service-disruption"],
  zone_outages_scenarios: ["zone-outage"],
  time_scenarios: ["time-skew"],
  network_chaos_scenarios: ["network-chaos"],
  syn_flood_scenarios: ["syn-flood"],
  service_hijacking_scenarios: ["service-hijacking"],
};

const DEFAULT_YAML = `# Kraken scenario configuration
duration: 60
namespace: default
target: pod
# node-selector: "node-role.kubernetes.io/worker="
# number-of-nodes: 2
`;

function generateYaml(form) {
  return `# Auto-generated Kraken scenario
name: "${form.name}"
chaos_type: ${form.chaosType}
target: ${form.target}
namespace: ${form.namespace}
duration: ${form.duration}
`;
}

export default function CreateScenario() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("basic"); // basic | advanced
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    name: "",
    type: "hog_scenarios",
    chaosType: "cpu-hog",
    target: "pod",
    namespace: "default",
    duration: 60,
  });
  const [yaml, setYaml] = useState(DEFAULT_YAML);

  const availableChaosTypes = CHAOS_TYPES[form.type] || [];

  function handleTypeChange(e) {
    const type = e.target.value;
    const firstChaos = CHAOS_TYPES[type]?.[0] || "";
    setForm((f) => ({ ...f, type, chaosType: firstChaos }));
  }

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((f) => {
      const updated = { ...f, [name]: value };
      if (mode === "advanced") setYaml(generateYaml(updated));
      return updated;
    });
  }

  function switchMode(m) {
    setMode(m);
    if (m === "advanced") setYaml(generateYaml(form));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.name.trim()) return toast.error("Scenario name is required");
    if (!form.namespace.trim()) return toast.error("Namespace is required");

    setLoading(true);
    try {
      const payload = {
        ...form,
        duration: parseInt(form.duration, 10) || 60,
        ...(mode === "advanced" ? { yamlConfig: yaml } : {}),
      };
      const scenario = await api.createScenario(payload);
      toast.success("Scenario launched!");
      navigate(`/scenarios/${scenario.id}`);
    } catch (err) {
      toast.error(err.message || "Failed to create scenario");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">New Chaos Scenario</h1>
        <p className="text-slate-500 text-sm mt-1">Configure and launch a chaos experiment</p>
      </div>

      {/* Mode toggle */}
      <div className="flex gap-2 p-1 bg-surface-800 border border-surface-700 rounded-xl w-fit">
        {[
          { id: "basic", icon: Sliders, label: "Basic" },
          { id: "advanced", icon: Code2, label: "Advanced (YAML)" },
        ].map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            onClick={() => switchMode(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              mode === id
                ? "bg-brand-500 text-white shadow"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Basic fields — always visible */}
        <div className="card space-y-4">
          <div>
            <label className="label">Scenario Name *</label>
            <input
              name="name"
              value={form.name}
              onChange={handleChange}
              placeholder="e.g. CPU Hog — Production Workers"
              className="input"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Scenario Type</label>
              <select name="type" value={form.type} onChange={handleTypeChange} className="input">
                {Object.keys(CHAOS_TYPES).map((t) => (
                  <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Chaos Type</label>
              <select name="chaosType" value={form.chaosType} onChange={handleChange} className="input">
                {availableChaosTypes.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Target</label>
              <select name="target" value={form.target} onChange={handleChange} className="input">
                <option value="pod">Pod</option>
                <option value="node">Node</option>
                <option value="namespace">Namespace</option>
                <option value="service">Service</option>
              </select>
            </div>
            <div>
              <label className="label">Namespace</label>
              <input
                name="namespace"
                value={form.namespace}
                onChange={handleChange}
                placeholder="default"
                className="input"
              />
            </div>
          </div>

          <div>
            <label className="label">Duration (seconds)</label>
            <input
              type="number"
              name="duration"
              value={form.duration}
              onChange={handleChange}
              min={10}
              max={3600}
              className="input"
            />
            <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
              <Info size={11} /> Demo mode: scenario completes in max 15s regardless of duration
            </p>
          </div>
        </div>

        {/* YAML editor for advanced mode */}
        {mode === "advanced" && (
          <div className="card">
            <label className="label mb-2">YAML Configuration</label>
            <textarea
              value={yaml}
              onChange={(e) => setYaml(e.target.value)}
              className="input font-mono text-xs resize-none"
              rows={14}
              spellCheck={false}
            />
          </div>
        )}

        <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2 py-3">
          {loading ? (
            <span className="animate-spin">⟳</span>
          ) : (
            <Send size={16} />
          )}
          {loading ? "Launching..." : "Launch Scenario"}
        </button>
      </form>
    </div>
  );
}
