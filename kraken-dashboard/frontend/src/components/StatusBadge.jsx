import { Loader2, CheckCircle2, XCircle } from "lucide-react";

const config = {
  Running: { cls: "badge-running", icon: <Loader2 size={11} className="animate-spin" /> },
  Completed: { cls: "badge-completed", icon: <CheckCircle2 size={11} /> },
  Failed: { cls: "badge-failed", icon: <XCircle size={11} /> },
};

export default function StatusBadge({ status }) {
  const cfg = config[status] || { cls: "badge-running", icon: null };
  return (
    <span className={`badge ${cfg.cls}`}>
      {cfg.icon}
      {status ?? "Unknown"}
    </span>
  );
}
