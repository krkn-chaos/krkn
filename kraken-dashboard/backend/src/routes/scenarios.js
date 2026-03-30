const express = require("express");
const router = express.Router();
const scenarioController = require("../controllers/scenarioController");

router.get("/", scenarioController.listScenarios);
router.get("/:id", scenarioController.getScenario);
router.post("/", scenarioController.createScenario);
router.delete("/:id", scenarioController.deleteScenario);

module.exports = router;
