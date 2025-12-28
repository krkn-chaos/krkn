#!/usr/bin/env python3

"""
Test suite for SynFloodScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_syn_flood_scenario_plugin.py -v

Assisted By: Claude Code
"""

import base64
import json
import unittest
import uuid
from unittest.mock import MagicMock

from krkn.rollback.config import RollbackContent
from krkn.scenario_plugins.syn_flood.syn_flood_scenario_plugin import SynFloodScenarioPlugin


class TestSynFloodScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for SynFloodScenarioPlugin
        """
        self.plugin = SynFloodScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["syn_flood_scenarios"])
        self.assertEqual(len(result), 1)

    def test_check_key_value(self):
        """
        Test check_key_value method
        """
        test_dict = {
            "valid_key": "value",
            "empty_key": "",
            "none_key": None,
            "zero_key": 0,
            "false_key": False,
        }

        self.assertTrue(self.plugin.check_key_value(test_dict, "valid_key"))
        self.assertFalse(self.plugin.check_key_value(test_dict, "empty_key"))
        self.assertFalse(self.plugin.check_key_value(test_dict, "none_key"))
        self.assertFalse(self.plugin.check_key_value(test_dict, "missing_key"))
        # 0 and False are valid values
        self.assertTrue(self.plugin.check_key_value(test_dict, "zero_key"))
        self.assertTrue(self.plugin.check_key_value(test_dict, "false_key"))


class TestIsNodeAffinityCorrect(unittest.TestCase):
    """Tests for is_node_affinity_correct method"""

    def setUp(self):
        self.plugin = SynFloodScenarioPlugin()

    def test_valid_node_affinity(self):
        """Test valid node affinity configuration"""
        valid_affinity = {
            "node-role.kubernetes.io/worker": [""],
        }
        self.assertTrue(self.plugin.is_node_affinity_correct(valid_affinity))

    def test_valid_node_affinity_multiple_labels(self):
        """Test valid node affinity with multiple labels"""
        valid_affinity = {
            "node-role.kubernetes.io/worker": ["value1", "value2"],
            "topology.kubernetes.io/zone": ["us-east-1a"],
        }
        self.assertTrue(self.plugin.is_node_affinity_correct(valid_affinity))

    def test_empty_dict_is_valid(self):
        """Test empty dict is valid for node affinity"""
        self.assertTrue(self.plugin.is_node_affinity_correct({}))

    def test_invalid_not_a_dict(self):
        """Test non-dict input is invalid"""
        self.assertFalse(self.plugin.is_node_affinity_correct("not a dict"))
        self.assertFalse(self.plugin.is_node_affinity_correct(["list"]))
        self.assertFalse(self.plugin.is_node_affinity_correct(123))
        self.assertFalse(self.plugin.is_node_affinity_correct(None))

    def test_invalid_non_string_key(self):
        """Test non-string keys are invalid"""
        invalid_affinity = {
            123: ["value"],
        }
        self.assertFalse(self.plugin.is_node_affinity_correct(invalid_affinity))

    def test_invalid_non_list_value(self):
        """Test non-list values are invalid"""
        invalid_affinity = {
            "node-role.kubernetes.io/worker": "not a list",
        }
        self.assertFalse(self.plugin.is_node_affinity_correct(invalid_affinity))


class TestParseConfig(unittest.TestCase):
    """Tests for parse_config method"""

    def setUp(self):
        self.plugin = SynFloodScenarioPlugin()

    def _create_scenario_file(self, tmp_path, config=None):
        """Helper to create a temporary scenario YAML file"""
        import yaml

        default_config = {
            "packet-size": 120,
            "window-size": 64,
            "duration": 10,
            "namespace": "default",
            "target-service": "elasticsearch",
            "target-port": 9200,
            "target-service-label": "",
            "number-of-pods": 2,
            "image": "quay.io/krkn-chaos/krkn-syn-flood:v1.0.0",
            "attacker-nodes": {"node-role.kubernetes.io/worker": [""]},
        }
        if config:
            default_config.update(config)

        scenario_file = tmp_path / "test_scenario.yaml"
        with open(scenario_file, "w") as f:
            yaml.dump(default_config, f)
        return str(scenario_file)

    def test_parse_config_valid(self, tmp_path=None):
        """Test parsing valid configuration"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(Path(tmp_dir))
            config = self.plugin.parse_config(scenario_file)

            assert config["packet-size"] == 120
            assert config["window-size"] == 64
            assert config["duration"] == 10
            assert config["namespace"] == "default"
            assert config["target-service"] == "elasticsearch"
            assert config["target-port"] == 9200
            assert config["number-of-pods"] == 2

    def test_parse_config_file_not_found(self):
        """Test parsing non-existent file raises exception"""
        with self.assertRaises(Exception) as context:
            self.plugin.parse_config("/nonexistent/path/scenario.yaml")
        self.assertIn("failed to load scenario file", str(context.exception))

    def test_parse_config_missing_required_params(self):
        """Test parsing config with missing required parameters"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Missing packet-size and window-size
            scenario_file = self._create_scenario_file(
                Path(tmp_dir),
                {"packet-size": "", "window-size": None},
            )
            with self.assertRaises(Exception) as context:
                self.plugin.parse_config(scenario_file)
            self.assertIn("packet-size", str(context.exception))
            self.assertIn("window-size", str(context.exception))

    def test_parse_config_both_target_service_and_label(self):
        """Test parsing config with both target-service and target-service-label set"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(
                Path(tmp_dir),
                {
                    "target-service": "elasticsearch",
                    "target-service-label": "app=elasticsearch",
                },
            )
            with self.assertRaises(Exception) as context:
                self.plugin.parse_config(scenario_file)
            self.assertIn(
                "you cannot select both target-service and target-service-label",
                str(context.exception),
            )

    def test_parse_config_neither_target_service_nor_label(self):
        """Test parsing config with neither target-service nor target-service-label set"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(
                Path(tmp_dir),
                {"target-service": "", "target-service-label": ""},
            )
            with self.assertRaises(Exception) as context:
                self.plugin.parse_config(scenario_file)
            self.assertIn(
                "you have either to set a target service or a label",
                str(context.exception),
            )

    def test_parse_config_invalid_attacker_nodes(self):
        """Test parsing config with invalid attacker-nodes format"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(
                Path(tmp_dir),
                {"attacker-nodes": "invalid"},
            )
            with self.assertRaises(Exception) as context:
                self.plugin.parse_config(scenario_file)
            self.assertIn("attacker-nodes format is not correct", str(context.exception))

    def test_parse_config_with_label_selector(self):
        """Test parsing config with target-service-label instead of target-service"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(
                Path(tmp_dir),
                {"target-service": "", "target-service-label": "app=elasticsearch"},
            )
            config = self.plugin.parse_config(scenario_file)
            assert config["target-service-label"] == "app=elasticsearch"
            assert config["target-service"] == ""


class TestSynFloodRun(unittest.TestCase):
    """Tests for the run method of SynFloodScenarioPlugin"""

    def _create_scenario_file(self, tmp_path, config=None):
        """Helper to create a temporary scenario YAML file"""
        import yaml
        from pathlib import Path

        default_config = {
            "packet-size": 120,
            "window-size": 64,
            "duration": 1,
            "namespace": "default",
            "target-service": "elasticsearch",
            "target-port": 9200,
            "target-service-label": "",
            "number-of-pods": 1,
            "image": "quay.io/krkn-chaos/krkn-syn-flood:v1.0.0",
            "attacker-nodes": {"node-role.kubernetes.io/worker": [""]},
        }
        if config:
            default_config.update(config)

        scenario_file = Path(tmp_path) / "test_scenario.yaml"
        with open(scenario_file, "w") as f:
            yaml.dump(default_config, f)
        return str(scenario_file)

    def _create_mocks(self):
        """Helper to create mock objects for testing"""
        mock_lib_telemetry = MagicMock()
        mock_lib_kubernetes = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_lib_kubernetes
        mock_scenario_telemetry = MagicMock()
        return mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry

    def test_run_successful_with_target_service(self):
        """Test successful execution with target-service"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(tmp_dir)
            mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
                self._create_mocks()
            )

            mock_lib_kubernetes.service_exists.return_value = True
            # Pod finishes immediately
            mock_lib_kubernetes.is_pod_running.return_value = False

            plugin = SynFloodScenarioPlugin()

            result = plugin.run(
                run_uuid=str(uuid.uuid4()),
                scenario=scenario_file,
                krkn_config={},
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 0)
            mock_lib_kubernetes.service_exists.assert_called_once_with(
                "elasticsearch", "default"
            )
            mock_lib_kubernetes.deploy_syn_flood.assert_called_once()

    def test_run_successful_with_label_selector(self):
        """Test successful execution with target-service-label"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(
                tmp_dir,
                {"target-service": "", "target-service-label": "app=elasticsearch"},
            )
            mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
                self._create_mocks()
            )

            mock_lib_kubernetes.select_service_by_label.return_value = [
                "elasticsearch-1",
                "elasticsearch-2",
            ]
            mock_lib_kubernetes.service_exists.return_value = True
            mock_lib_kubernetes.is_pod_running.return_value = False

            plugin = SynFloodScenarioPlugin()

            result = plugin.run(
                run_uuid=str(uuid.uuid4()),
                scenario=scenario_file,
                krkn_config={},
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 0)
            mock_lib_kubernetes.select_service_by_label.assert_called_once_with(
                "default", "app=elasticsearch"
            )
            # Should deploy pods for each service found
            self.assertEqual(mock_lib_kubernetes.deploy_syn_flood.call_count, 2)

    def test_run_service_not_found(self):
        """Test run method when service does not exist"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(tmp_dir)
            mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
                self._create_mocks()
            )

            mock_lib_kubernetes.service_exists.return_value = False

            plugin = SynFloodScenarioPlugin()

            result = plugin.run(
                run_uuid=str(uuid.uuid4()),
                scenario=scenario_file,
                krkn_config={},
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 1)
            mock_lib_kubernetes.deploy_syn_flood.assert_not_called()

    def test_run_multiple_pods(self):
        """Test run method with multiple attacker pods"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(tmp_dir, {"number-of-pods": 3})
            mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
                self._create_mocks()
            )

            mock_lib_kubernetes.service_exists.return_value = True
            mock_lib_kubernetes.is_pod_running.return_value = False

            plugin = SynFloodScenarioPlugin()

            result = plugin.run(
                run_uuid=str(uuid.uuid4()),
                scenario=scenario_file,
                krkn_config={},
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 0)
            self.assertEqual(mock_lib_kubernetes.deploy_syn_flood.call_count, 3)

    def test_run_exception_handling(self):
        """Test run method handles exceptions gracefully"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(tmp_dir)
            mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
                self._create_mocks()
            )

            mock_lib_kubernetes.service_exists.return_value = True
            mock_lib_kubernetes.deploy_syn_flood.side_effect = Exception("Deployment failed")

            plugin = SynFloodScenarioPlugin()

            result = plugin.run(
                run_uuid=str(uuid.uuid4()),
                scenario=scenario_file,
                krkn_config={},
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 1)

    def test_run_waits_for_pods_to_finish(self):
        """Test run method waits for pods to finish"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            scenario_file = self._create_scenario_file(tmp_dir)
            mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
                self._create_mocks()
            )

            mock_lib_kubernetes.service_exists.return_value = True
            # Pod runs for a few iterations then finishes
            mock_lib_kubernetes.is_pod_running.side_effect = [True, True, False]

            plugin = SynFloodScenarioPlugin()

            result = plugin.run(
                run_uuid=str(uuid.uuid4()),
                scenario=scenario_file,
                krkn_config={},
                lib_telemetry=mock_lib_telemetry,
                scenario_telemetry=mock_scenario_telemetry,
            )

            self.assertEqual(result, 0)
            # Should have checked pod status multiple times
            self.assertGreaterEqual(mock_lib_kubernetes.is_pod_running.call_count, 1)


class TestRollbackSynFloodPods(unittest.TestCase):    
    """Tests for rollback_syn_flood_pods static method"""
    def test_rollback_syn_flood_pods_successful(self):
        """Test successful rollback of syn flood pods"""
        pod_names = ["syn-flood-abc123", "syn-flood-def456"]
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

        SynFloodScenarioPlugin.rollback_syn_flood_pods(
            rollback_content, mock_lib_telemetry
        )

        assert mock_lib_kubernetes.delete_pod.call_count == 2
        mock_lib_kubernetes.delete_pod.assert_any_call("syn-flood-abc123", "default")
        mock_lib_kubernetes.delete_pod.assert_any_call("syn-flood-def456", "default")

    def test_rollback_syn_flood_pods_empty_list(self):
        """Test rollback with empty pod list"""
        pod_names = []
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

        SynFloodScenarioPlugin.rollback_syn_flood_pods(
            rollback_content, mock_lib_telemetry
        )

        mock_lib_kubernetes.delete_pod.assert_not_called()

    def test_rollback_syn_flood_pods_invalid_data(self):
        """Test rollback with invalid encoded data handles error gracefully"""
        rollback_content = RollbackContent(
            resource_identifier="invalid_base64_data",
            namespace="default",
        )

        mock_lib_telemetry = MagicMock()
        mock_lib_kubernetes = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_lib_kubernetes

        # Should not raise exception, just log error
        with self.assertLogs(level='ERROR') as log_context:
            SynFloodScenarioPlugin.rollback_syn_flood_pods(
                rollback_content, mock_lib_telemetry
            )
        
        # Verify error was logged
        self.assertTrue(any('error' in log.lower() for log in log_context.output))
        
        # Verify delete_pod was not called due to invalid data
        mock_lib_kubernetes.delete_pod.assert_not_called()


if __name__ == "__main__":
    unittest.main()
