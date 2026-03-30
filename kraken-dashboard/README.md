# Kraken Chaos Engineering Dashboard

A production-ready Web UI for creating, monitoring, and reviewing chaos scenarios with the [Kraken](https://github.com/krkn-chaos/krkn) chaos engineering tool.

Closes [#1167](https://github.com/krkn-chaos/krkn/issues/1167) — Build Web UI for creating, monitoring, and reviewing chaos scenarios.

## Tech Stack

- **Frontend**: React 18 + Vite, Tailwind CSS, Recharts, Socket.io-client
- **Backend**: Node.js + Express, Socket.io
- **Real-time**: WebSocket (Socket.io) for live log streaming and status updates

## Project Structure

```
kraken-dashboard/
├── backend/
│   └── src/
│       ├── index.js              # Express + Socket.io server
│       ├── store.js              # In-memory store (replace with DB in prod)
│       ├── routes/
│       │   ├── scenarios.js
│       │   └── reports.js
│       ├── controllers/
│       │   ├── scenarioController.js
│       │   └── reportController.js
│       └── websocket/
│           └── socketHandler.js
└── frontend/
    └── src/
        ├── App.jsx
        ├── pages/
        │   ├── Dashboard.jsx       # Live stats + score trend chart
        │   ├── CreateScenario.jsx  # Basic form + Advanced YAML editor
        │   ├── History.jsx         # Searchable/filterable experiment table
        │   ├── ScenarioDetail.jsx  # Live log streaming + resiliency gauge
        │   ├── Reports.jsx         # Report list + JSON/HTML download
        │   └── ReportDetail.jsx    # SLO results + breakdown chart + gauge
        ├── components/
        │   ├── Layout.jsx          # Sidebar + nav + WebSocket status
        │   ├── StatusBadge.jsx
        │   ├── LogPanel.jsx        # Live log streaming panel
        │   ├── ResiliencyGauge.jsx # Radial score gauge (Recharts)
        │   └── ScenarioCard.jsx
        └── services/
            ├── api.js              # REST API client
            └── socket.js           # Socket.io client
```

## Quick Start

### Prerequisites

- Node.js 18+
- npm

### 1. Backend

```bash
# Linux / macOS
cd kraken-dashboard/backend
cp .env.example .env
npm install
npm run dev

# Windows
cd kraken-dashboard\backend
copy .env.example .env
npm install
npm run dev
```

Backend runs on `http://localhost:4000`

### 2. Frontend

```bash
# Linux / macOS
cd kraken-dashboard/frontend
cp .env.example .env
npm install
npm run dev

# Windows
cd kraken-dashboard\frontend
copy .env.example .env
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`

Open your browser at **http://localhost:5173** — demo data is pre-loaded.

## Environment Variables

**Backend** (`backend/.env`):
```
PORT=4000
FRONTEND_URL=http://localhost:5173
KRAKEN_API_URL=http://localhost:8081
NODE_ENV=development
```

**Frontend** (`frontend/.env`):
```
VITE_API_URL=/api
VITE_SOCKET_URL=http://localhost:4000
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/scenarios` | List all scenarios |
| POST | `/api/scenarios` | Create & launch scenario |
| GET | `/api/scenarios/:id` | Get scenario details |
| DELETE | `/api/scenarios/:id` | Delete scenario |
| GET | `/api/reports` | List all reports |
| GET | `/api/reports/:id` | Get report details |
| GET | `/api/reports/:id/download/json` | Download report as JSON |
| GET | `/api/reports/:id/download/html` | Download report as HTML |

## WebSocket Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `scenario:created` | Server → Client | New scenario launched |
| `scenario:updated` | Server → Client | Scenario status changed |
| `scenario:log` | Server → Client | New log line streamed |
| `scenario:completed` | Server → Client | Scenario finished with score |
| `subscribe:logs` | Client → Server | Request log history for a scenario |
| `scenario:logs:history` | Server → Client | Full log history response |

## Acceptance Criteria (Issue #1167)

- ✅ Users can create a scenario via UI (basic form + advanced YAML editor)
- ✅ Users can monitor live execution status (WebSocket real-time updates)
- ✅ Users can view experiment history and reports (filterable table + report detail)
- ✅ Resiliency score visualization (radial gauge + bar chart trend)
- ✅ Report download in JSON and HTML format
- ✅ Works with existing Kraken backend (configurable via `KRAKEN_API_URL`)

## Production Notes

- Replace `store.js` in-memory store with PostgreSQL or MongoDB
- Add authentication (JWT or OAuth) before deploying publicly
- Set `KRAKEN_API_URL` to point to your actual Kraken instance
- Use nginx to serve the built frontend and proxy `/api` to the backend
- Build frontend for production: `npm run build` inside `frontend/`
