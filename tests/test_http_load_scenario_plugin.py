#!/usr/bin/env python3

"""
Test suite for HttpLoadScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_http_load_scenario_plugin.py -v
"""

import base64
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from krkn.rollback.config import RollbackContent
from krkn.scenario_plugins.http_load.http_load_scenario_plugin import HttpLoadScenarioPlugin


class TestHttpLoadScenarioPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = HttpLoadScenarioPlugin()

    def test_get_scenario_types(self):
        """Test get_scenario_types returns correct scenario type"""
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["http_load_scenarios"])
        self.assertEqual(len(result), 1)


class TestValidateConfig(unittest.TestCase):

    def setUp(self):
        self.plugin = HttpLoadScenarioPlugin()

    def test_valid_config_single_endpoint(self):
        config = {
            "targets": {
                "endpoints": [
                    {"url": "https://example.com/api", "method": "GET"}
                ]
            },
            "rate": "50/1s",
            "duration": "30s"
        }
        self.assertTrue(self.plugin._validate_config(config))

    def test_valid_config_multiple_endpoints(self):
        config = {
            "targets": {
                "endpoints": [
                    {"url": "https://example.com/health", "method": "GET"},
                    {"url": "https://example.com/api", "method": "POST",
                     "headers": {"Content-Type": "application/json"},
                     "body": '{"key":"value"}'}
                ]
            }
        }
        self.assertTrue(self.plugin._validate_config(config))

    def test_missing_targets(self):
        config = {"rate": "50/1s", "duration": "30s"}
        self.assertFalse(self.plugin._validate_config(config))

    def test_missing_endpoints(self):
        config = {"targets": {}}
        self.assertFalse(self.plugin._validate_config(config))

    def test_empty_endpoints_list(self):
        config = {"targets": {"endpoints": []}}
        self.assertFalse(self.plugin._validate_config(config))

    def test_endpoint_missing_url(self):
        config = {
            "targets": {
                "endpoints": [{"method": "GET"}]
            }
        }
        self.assertFalse(self.plugin._validate_config(config))

    def test_endpoint_missing_method(self):
        config = {
            "targets": {
                "endpoints": [{"url": "https://example.com"}]
            }
        }
        self.assertFalse(self.plugin._validate_config(config))

    def test_invalid_endpoint_not_dict(self):
        config = {
            "targets": {
                "endpoints": ["https://example.com"]
            }
        }
        self.assertFalse(self.plugin._validate_config(config))


class TestBuildVegetaJsonTargets(unittest.TestCase):

    def setUp(self):
        self.plugin = HttpLoadScenarioPlugin()

    def test_single_get_endpoint(self):
        endpoints = [{"url": "https://example.com/api", "method": "GET"}]
        result = self.plugin._build_vegeta_json_targets(endpoints)

        parsed = json.loads(result)
        self.assertEqual(parsed["method"], "GET")
        self.assertEqual(parsed["url"], "https://example.com/api")

    def test_endpoint_with_headers(self):
        endpoints = [{
            "url": "https://example.com/api",
            "method": "GET",
            "headers": {"Authorization": "Bearer token123", "X-Custom": "value"}
        }]
        result = self.plugin._build_vegeta_json_targets(endpoints)

        parsed = json.loads(result)
        self.assertIn("header", parsed)
        self.assertEqual(parsed["header"]["Authorization"], ["Bearer token123"])
        self.assertEqual(parsed["header"]["X-Custom"], ["value"])

    def test_endpoint_with_body(self):
        endpoints = [{
            "url": "https://example.com/api",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": '{"key":"value"}'
        }]
        result = self.plugin._build_vegeta_json_targets(endpoints)

        parsed = json.loads(result)
        self.assertIn("body", parsed)
        decoded_body = base64.b64decode(parsed["body"]).decode()
        self.assertEqual(decoded_body, '{"key":"value"}')

    def test_multiple_endpoints_newline_delimited(self):
        endpoints = [
            {"url": "https://example.com/health", "method": "GET"},
            {"url": "https://example.com/api", "method": "POST"}
        ]
        result = self.plugin._build_vegeta_json_targets(endpoints)

        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 2)

        target1 = json.loads(lines[0])
        target2 = json.loads(lines[1])
        self.assertEqual(target1["method"], "GET")
        self.assertEqual(target2["method"], "POST")


class TestParseDurationToSeconds(unittest.TestCase):

    def setUp(self):
        self.plugin = HttpLoadScenarioPlugin()

    def test_seconds(self):
        self.assertEqual(self.plugin._parse_duration_to_seconds("30s"), 30)

    def test_minutes(self):
        self.assertEqual(self.plugin._parse_duration_to_seconds("5m"), 300)

    def test_hours(self):
        self.assertEqual(self.plugin._parse_duration_to_seconds("1h"), 3600)

    def test_invalid_format_defaults_to_30(self):
        self.assertEqual(self.plugin._parse_duration_to_seconds("invalid"), 30)

    def test_integer_input(self):
        self.assertEqual(self.plugin._parse_duration_to_seconds(30), 30)


class TestAggregateMetrics(unittest.TestCase):

    def setUp(self):
        self.plugin = HttpLoadScenarioPlugin()

    def test_single_pod_metrics(self):
        metrics_list = [{
            "requests": 1000,
            "rate": 50.0,
            "throughput": 49.5,
            "success": 0.99,
            "latencies": {"mean": 50000000, "50th": 45000000, "95th": 80000000,
                          "99th": 100000000, "max": 150000000, "min": 1000000},
            "status_codes": {"200": 990, "500": 10},
            "bytes_in": {"total": 1024000},
            "bytes_out": {"total": 512000},
            "errors": ["connection refused"]
        }]
        result = self.plugin._aggregate_metrics(metrics_list)

        self.assertEqual(result["requests"], 1000)
        self.assertEqual(result["pod_count"], 1)
        self.assertAlmostEqual(result["success"], 0.99)

    def test_multiple_pod_metrics(self):
        metrics_list = [
            {"requests": 500, "rate": 25.0, "throughput": 24.5,
             "success": 1.0, "latencies": {"mean": 40000000},
             "status_codes": {"200": 500}, "bytes_in": {"total": 512000},
             "bytes_out": {"total": 256000}, "errors": []},
            {"requests": 500, "rate": 25.0, "throughput": 24.5,
             "success": 0.98, "latencies": {"mean": 60000000},
             "status_codes": {"200": 490, "500": 10}, "bytes_in": {"total": 512000},
             "bytes_out": {"total": 256000}, "errors": ["timeout"]}
        ]
        result = self.plugin._aggregate_metrics(metrics_list)

        self.assertEqual(result["requests"], 1000)
        self.assertEqual(result["rate"], 50.0)
        self.assertEqual(result["pod_count"], 2)
        self.assertEqual(result["status_codes"]["200"], 990)
        self.assertEqual(result["status_codes"]["500"], 10)

    def test_empty_metrics_list(self):
        self.assertEqual(self.plugin._aggregate_metrics([]), {})


class TestParseMetricsFromLogs(unittest.TestCase):

    def setUp(self):
        self.plugin = HttpLoadScenarioPlugin()

    def test_valid_json_report(self):
        logs = (
            "=== Krkn HTTP Load Scenario ===\n"
            "RATE: 50/1s\n"
            "=== JSON Report ===\n"
            '{"requests":1000,"latencies":{"mean":50000000},"success":0.99}\n'
            "Attack completed successfully\n"
        )
        result = self.plugin._parse_metrics_from_logs(logs)

        self.assertIsNotNone(result)
        self.assertEqual(result["requests"], 1000)

    def test_no_json_in_logs(self):
        logs = "=== Krkn HTTP Load Scenario ===\nno json here\n"
        result = self.plugin._parse_metrics_from_logs(logs)
        self.assertIsNone(result)


class TestHttpLoadRun(unittest.TestCase):

    def _create_scenario_file(self, tmp_dir, config=None):
        default_config = [{
            "http_load_scenario": {
                "targets": {
                    "endpoints": [
                        {"url": "https://example.com/api", "method": "GET"}
                    ]
                },
                "rate": "50/1s",
                "duration": "10s",
                "namespace": "default",
                "number-of-pods": 1,
                "image": "quay.io/krkn-chaos/krkn-http-load:latest"
            }
        }]
        if config:
            default_config[0]["http_load_scenario"].update(config)

        scenario_file = Path(tmp_dir) / "test_scenario.yaml"
        with open(scenario_file, "w") as f:
            yaml.dump(default_config, f)
        return str(scenario_file)

    def _create_mocks(self):
        mock_lib_telemetry = MagicMock()
        mock_lib_kubernetes = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_lib_kubernetes
        mock_scenario_telemetry = MagicMock()
        return mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry

    def test_run_successful(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(tmp_dir)
            mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
                self._create_mocks()
            )

            mock_lib_kubernetes.is_pod_running.return_value = False
            mock_lib_kubernetes.get_pod_log.return_value = (
                '{"requests":100,"latencies":{"mean":50000000},"success":1.0,'
                '"rate":50.0,"throughput":49.5,"status_codes":{"200":100},'
                '"bytes_in":{"total":1024},"bytes_out":{"total":512},"errors":[]}'
            )

            plugin = HttpLoadScenarioPlugin()
            result = plugin.run(
                run_uuid=str(uuid.uuid4()),
                scenario=scenario_file,
                krkn_config={},
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 0)
            mock_lib_kubernetes.deploy_http_load.assert_called_once()

    def test_run_multiple_pods(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(tmp_dir, {"number-of-pods": 3})
            mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
                self._create_mocks()
            )

            mock_lib_kubernetes.is_pod_running.return_value = False
            mock_lib_kubernetes.get_pod_log.return_value = (
                '{"requests":100,"latencies":{"mean":50000000},"success":1.0,'
                '"rate":50.0,"throughput":49.5,"status_codes":{"200":100},'
                '"bytes_in":{"total":1024},"bytes_out":{"total":512},"errors":[]}'
            )

            plugin = HttpLoadScenarioPlugin()
            result = plugin.run(
                run_uuid=str(uuid.uuid4()),
                scenario=scenario_file,
                krkn_config={},
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 0)
            self.assertEqual(mock_lib_kubernetes.deploy_http_load.call_count, 3)

    def test_run_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = Path(tmp_dir) / "bad_scenario.yaml"
            with open(scenario_file, "w") as f:
                yaml.dump([{"http_load_scenario": {"invalid": "config"}}], f)

            mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
                self._create_mocks()
            )

            plugin = HttpLoadScenarioPlugin()
            result = plugin.run(
                run_uuid=str(uuid.uuid4()),
                scenario=str(scenario_file),
                krkn_config={},
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 1)
            mock_lib_kubernetes.deploy_http_load.assert_not_called()

    def test_run_deploy_exception(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(tmp_dir)
            mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
                self._create_mocks()
            )

            mock_lib_kubernetes.deploy_http_load.side_effect = Exception("Deploy failed")

            plugin = HttpLoadScenarioPlugin()
            result = plugin.run(
                run_uuid=str(uuid.uuid4()),
                scenario=scenario_file,
                krkn_config={},
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 1)


class TestRollbackHttpLoadPods(unittest.TestCase):

    def test_rollback_successful(self):
        pod_names = ["http-load-abc123", "http-load-def456"]
        encoded_data = base64.b64encode(
            json.dumps(pod_names).encode("utf-8")
        ).decode("utf-8")

        rollback_content = RollbackContent(
            resource_identifier=encoded_data,
            namespace="default",
        )

        mock_lib_telemetry = MagicMock()
        mock_lib_kubernetes = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_lib_kubernetes

        HttpLoadScenarioPlugin.rollback_http_load_pods(
            rollback_content, mock_lib_telemetry
        )

        self.assertEqual(mock_lib_kubernetes.delete_pod.call_count, 2)
        mock_lib_kubernetes.delete_pod.assert_any_call("http-load-abc123", "default")
        mock_lib_kubernetes.delete_pod.assert_any_call("http-load-def456", "default")

    def test_rollback_empty_list(self):
        encoded_data = base64.b64encode(
            json.dumps([]).encode("utf-8")
        ).decode("utf-8")

        rollback_content = RollbackContent(
            resource_identifier=encoded_data,
            namespace="default",
        )

        mock_lib_telemetry = MagicMock()
        mock_lib_kubernetes = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_lib_kubernetes

        HttpLoadScenarioPlugin.rollback_http_load_pods(
            rollback_content, mock_lib_telemetry
        )

        mock_lib_kubernetes.delete_pod.assert_not_called()

    def test_rollback_invalid_data(self):
        rollback_content = RollbackContent(
            resource_identifier="invalid_base64_data",
            namespace="default",
        )

        mock_lib_telemetry = MagicMock()
        mock_lib_kubernetes = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_lib_kubernetes

        with self.assertLogs(level='ERROR') as log_context:
            HttpLoadScenarioPlugin.rollback_http_load_pods(
                rollback_content, mock_lib_telemetry
            )

        self.assertTrue(any('error' in log.lower() for log in log_context.output))
        mock_lib_kubernetes.delete_pod.assert_not_called()


if __name__ == "__main__":
    unittest.main()
