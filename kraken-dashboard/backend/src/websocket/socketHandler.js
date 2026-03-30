const { scenarios } = require("../store");

function initWebSocket(io) {
  io.on("connection", (socket) => {
    console.log(`[ws] Client connected: ${socket.id}`);

    // Client subscribes to live logs for a specific scenario
    socket.on("subscribe:logs", (scenarioId) => {
      if (typeof scenarioId !== "string") return;
      const scenario = scenarios.get(scenarioId);
      if (scenario) {
        socket.emit("scenario:logs:history", {
          id: scenarioId,
          logs: scenario.logs,
        });
      }
    });

    socket.on("disconnect", (reason) => {
      console.log(`[ws] Client disconnected: ${socket.id} (${reason})`);
    });
  });
}

module.exports = { initWebSocket };
