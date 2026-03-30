require("dotenv").config();
const express = require("express");
const http = require("http");
const cors = require("cors");
const { Server } = require("socket.io");
const scenarioRoutes = require("./routes/scenarios");
const reportRoutes = require("./routes/reports");
const { initWebSocket } = require("./websocket/socketHandler");

const app = express();
const server = http.createServer(app);

const ALLOWED_ORIGINS = (process.env.FRONTEND_URL || "http://localhost:5173")
  .split(",")
  .map((o) => o.trim());

const io = new Server(server, {
  cors: {
    origin: ALLOWED_ORIGINS,
    methods: ["GET", "POST"],
  },
});

app.use(cors({ origin: ALLOWED_ORIGINS }));
app.use(express.json({ limit: "100kb" }));

// Attach io to req so routes can emit events
app.use((req, _res, next) => {
  req.io = io;
  next();
});

app.use("/api/scenarios", scenarioRoutes);
app.use("/api/reports", reportRoutes);

app.get("/api/health", (_req, res) => res.json({ status: "ok" }));

initWebSocket(io);

const PORT = process.env.PORT || 4000;
server.listen(PORT, () => {
  console.log(`Kraken Dashboard backend running on port ${PORT}`);
});
