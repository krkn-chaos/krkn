const express = require("express");
const router = express.Router();
const reportController = require("../controllers/reportController");

router.get("/", reportController.listReports);
router.get("/:id", reportController.getReport);
router.get("/:id/download/json", reportController.downloadJson);
router.get("/:id/download/html", reportController.downloadHtml);

module.exports = router;
