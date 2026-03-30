const BASE_URL = import.meta.env.VITE_API_URL || "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || "Request failed");
  }
  return res.json();
}

export const api = {
  // Scenarios
  getScenarios: () => request("/scenarios"),
  getScenario: (id) => request(`/scenarios/${id}`),
  createScenario: (data) =>
    request("/scenarios", { method: "POST", body: JSON.stringify(data) }),
  deleteScenario: (id) => request(`/scenarios/${id}`, { method: "DELETE" }),

  // Reports
  getReports: () => request("/reports"),
  getReport: (id) => request(`/reports/${id}`),
  // Download URLs — BASE_URL works via Vite proxy in dev and direct in prod
  downloadReportJson: (id) => `${BASE_URL}/reports/${id}/download/json`,
  downloadReportHtml: (id) => `${BASE_URL}/reports/${id}/download/html`,

  // Health
  health: () => request("/health"),
};
