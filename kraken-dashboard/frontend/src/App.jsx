import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import CreateScenario from "./pages/CreateScenario";
import History from "./pages/History";
import ScenarioDetail from "./pages/ScenarioDetail";
import Reports from "./pages/Reports";
import ReportDetail from "./pages/ReportDetail";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="create" element={<CreateScenario />} />
        <Route path="history" element={<History />} />
        <Route path="scenarios/:id" element={<ScenarioDetail />} />
        <Route path="reports" element={<Reports />} />
        <Route path="reports/:id" element={<ReportDetail />} />
      </Route>
    </Routes>
  );
}
