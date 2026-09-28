import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from krkn.prometheus import client


class TestMetricsQueryRouting(unittest.TestCase):
    def setUp(self):
        self.prom_cli = MagicMock()
        self.elastic = MagicMock()
        self.telemetry_json = json.dumps({"scenarios": [], "health_checks": [], "virt_checks": []})

    def _write_profile(self, metrics):
        profile = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        profile.write(json.dumps({"metrics": metrics}))
        profile.close()
        return profile.name

    def test_range_query(self):
        path = self._write_profile([{"query": "up", "metricName": "target_up"}])
        try:
            self.prom_cli.process_prom_query_in_range.return_value = []
            client.metrics(self.prom_cli, self.elastic, "run", 1000, 1060, path, "metrics", self.telemetry_json)
            self.prom_cli.process_prom_query_in_range.assert_called_once()
            self.prom_cli.process_query.assert_not_called()
        finally:
            os.unlink(path)

    def test_instant_query(self):
        path = self._write_profile([{"query": "up", "metricName": "target_up", "instant": True}])
        try:
            self.prom_cli.process_query.return_value = []
            client.metrics(self.prom_cli, self.elastic, "run", 1000, 1060, path, "metrics", self.telemetry_json)
            self.prom_cli.process_query.assert_called_once()
            self.prom_cli.process_prom_query_in_range.assert_not_called()
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
