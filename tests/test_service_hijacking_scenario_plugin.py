#!/usr/bin/env python3

"""
Test suite for ServiceHijackingScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_service_hijacking_scenario_plugin.py -v

Assisted By: Claude Code
"""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid
import yaml
from krkn.rollback.config import RollbackContent
from krkn.scenario_plugins.service_hijacking.service_hijacking_scenario_plugin import (
    ServiceHijackingScenarioPlugin,
)


class TestServiceHijackingScenarioPlugin(unittest.TestCase):
    def setUp(self):
        """
        Set up test fixtures for ServiceHijackingScenarioPlugin
        """
        self.plugin = ServiceHijackingScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["service_hijacking_scenarios"])
        self.assertEqual(len(result), 1)


class TestRollbackServiceHijacking(unittest.TestCase): 
    def test_rollback_service_hijacking(self):
        """
        Test rollback functionality for ServiceHijackingScenarioPlugin
        """
        # Create rollback data that matches what the plugin expects
        rollback_data = {
            "service_name": "test-service",
            "service_namespace": "default",
            "original_selectors": {"app": "original-app"},
            "webservice_pod_name": "test-webservice",
        }
        json_str = json.dumps(rollback_data)
        encoded_data = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

        # Create RollbackContent with correct parameters
        rollback_content = RollbackContent(
            resource_identifier=encoded_data,
            namespace="default",
        )

        # Create a mock KrknTelemetryOpenshift object
        mock_lib_telemetry = MagicMock()
        mock_lib_kubernetes = MagicMock()
        mock_lib_telemetry.get_lib_kubernetes.return_value = mock_lib_kubernetes

        # Configure mock to return a successful service restoration
        mock_lib_kubernetes.replace_service_selector.return_value = {
            "metadata": {"name": "test-service"}
        }
        mock_lib_kubernetes.delete_pod.return_value = None

        # Call the rollback method
        ServiceHijackingScenarioPlugin.rollback_service_hijacking(
            rollback_content, mock_lib_telemetry
        )

        # Verify that the correct methods were called
        mock_lib_kubernetes.replace_service_selector.assert_called_once_with(
            ["app=original-app"], "test-service", "default"
        )
        mock_lib_kubernetes.delete_pod.assert_called_once_with(
            "test-webservice", "default"
        )

    @patch("krkn.scenario_plugins.service_hijacking.service_hijacking_scenario_plugin.logging")
    def test_rollback_service_hijacking_invalid_data(self, mock_logging):
        """
        Test rollback functionality with invalid rollback content logs error
        """
        # Create RollbackContent with invalid base64 data
        rollback_content = RollbackContent(
            resource_identifier="invalid_base64_data",
            namespace="default",
        )

        # Create a mock KrknTelemetryOpenshift object
        mock_lib_telemetry = MagicMock()

        # Call the rollback method - should not raise exception but log error
        ServiceHijackingScenarioPlugin.rollback_service_hijacking(
            rollback_content, mock_lib_telemetry
        )
        # Verify error was logged to inform operators of rollback failure
        mock_logging.error.assert_called_once()
        error_message = mock_logging.error.call_args[0][0]
        self.assertIn("Failed to rollback service hijacking", error_message)


class TestServiceHijackingRun(unittest.TestCase):
    """Tests for the run method of ServiceHijackingScenarioPlugin"""

    def setUp(self):
        """Set up test fixtures - create temporary directory"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up temporary directory after test"""
        self.temp_dir.cleanup()

    def _create_scenario_file(self, config=None):
        """Helper to create a temporary scenario YAML file"""
        default_config = {
            "service_name": "nginx-service",
            "service_namespace": "default",
            "service_target_port": "http-web-svc",
            "image": "quay.io/krkn-chaos/krkn-service-hijacking:v0.1.3",
            "chaos_duration": 1,  # Use short duration for tests
            "privileged": True,
            "plan": [
                {
                    "resource": "/test",
                    "steps": {
                        "GET": [
                            {
                                "duration": 1,
                                "status": 200,
                                "mime_type": "application/json",
                                "payload": '{"status": "ok"}',
                            }
                        ]
                    },
                }
            ],
        }
        if config:
            default_config.update(config)

        scenario_file = self.tmp_path / "test_scenario.yaml"
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

    def test_run_successful(self):
        """Test successful execution of the run method"""
        scenario_file = self._create_scenario_file()
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        # Configure mocks for successful execution
        mock_lib_kubernetes.service_exists.return_value = True
        mock_webservice = MagicMock()
        mock_webservice.pod_name = "hijacker-pod"
        mock_webservice.selector = "app=hijacker"
        mock_lib_kubernetes.deploy_service_hijacking.return_value = mock_webservice
        mock_lib_kubernetes.replace_service_selector.return_value = {
            "metadata": {"name": "nginx-service"},
            "spec": {"selector": {"app": "nginx"}},
        }

        plugin = ServiceHijackingScenarioPlugin()

        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            krkn_config={},
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        self.assertEqual(result, 0)  
        mock_lib_kubernetes.service_exists.assert_called_once_with(  
            "nginx-service", "default"  
        )  
        mock_lib_kubernetes.deploy_service_hijacking.assert_called_once()  
        self.assertEqual(mock_lib_kubernetes.replace_service_selector.call_count, 2)  
        mock_lib_kubernetes.undeploy_service_hijacking.assert_called_once_with(
            mock_webservice
        )

    def test_run_service_not_found(self):
        """Test run method when service does not exist"""
        scenario_file = self._create_scenario_file()
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        # Service does not exist
        mock_lib_kubernetes.service_exists.return_value = False

        plugin = ServiceHijackingScenarioPlugin()

        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            krkn_config={},
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        assert result == 1
        mock_lib_kubernetes.service_exists.assert_called_once_with(
            "nginx-service", "default"
        )
        mock_lib_kubernetes.deploy_service_hijacking.assert_not_called()

    def test_run_patch_service_failed(self):
        """Test run method when patching the service fails"""
        scenario_file = self._create_scenario_file()
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        mock_lib_kubernetes.service_exists.return_value = True
        mock_webservice = MagicMock()
        mock_webservice.pod_name = "hijacker-pod"
        mock_webservice.selector = "app=hijacker"
        mock_lib_kubernetes.deploy_service_hijacking.return_value = mock_webservice
        # Patching returns None (failure)
        mock_lib_kubernetes.replace_service_selector.return_value = None

        plugin = ServiceHijackingScenarioPlugin()

        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            krkn_config={},
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        assert result == 1
        mock_lib_kubernetes.replace_service_selector.assert_called_once()

    def test_run_restore_service_failed(self):
        """Test run method when restoring the service fails"""
        scenario_file = self._create_scenario_file()
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        mock_lib_kubernetes.service_exists.return_value = True
        mock_webservice = MagicMock()
        mock_webservice.pod_name = "hijacker-pod"
        mock_webservice.selector = "app=hijacker"
        mock_lib_kubernetes.deploy_service_hijacking.return_value = mock_webservice
        # First call (patch) succeeds, second call (restore) fails
        mock_lib_kubernetes.replace_service_selector.side_effect = [
            {"metadata": {"name": "nginx-service"}, "spec": {"selector": {"app": "nginx"}}},
            None,  # Restore fails
        ]

        plugin = ServiceHijackingScenarioPlugin()

        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            krkn_config={},
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        assert result == 1
        assert mock_lib_kubernetes.replace_service_selector.call_count == 2

    def test_run_with_numeric_port(self):
        """Test run method with numeric target port"""
        scenario_file = self._create_scenario_file(
            {"service_target_port": 8080}
        )
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        mock_lib_kubernetes.service_exists.return_value = True
        mock_webservice = MagicMock()
        mock_webservice.pod_name = "hijacker-pod"
        mock_webservice.selector = "app=hijacker"
        mock_lib_kubernetes.deploy_service_hijacking.return_value = mock_webservice
        mock_lib_kubernetes.replace_service_selector.return_value = {
            "metadata": {"name": "nginx-service"},
            "spec": {"selector": {"app": "nginx"}},
        }

        plugin = ServiceHijackingScenarioPlugin()

        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            krkn_config={},
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        assert result == 0
        # Verify port_number was passed instead of port_name
        call_kwargs = mock_lib_kubernetes.deploy_service_hijacking.call_args
        assert call_kwargs[1]["port_number"] == 8080

    def test_run_with_named_port(self):
        """Test run method with named target port"""
        scenario_file = self._create_scenario_file(
            {"service_target_port": "http-web-svc"}
        )
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        mock_lib_kubernetes.service_exists.return_value = True
        mock_webservice = MagicMock()
        mock_webservice.pod_name = "hijacker-pod"
        mock_webservice.selector = "app=hijacker"
        mock_lib_kubernetes.deploy_service_hijacking.return_value = mock_webservice
        mock_lib_kubernetes.replace_service_selector.return_value = {
            "metadata": {"name": "nginx-service"},
            "spec": {"selector": {"app": "nginx"}},
        }

        plugin = ServiceHijackingScenarioPlugin()

        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            krkn_config={},
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        assert result == 0
        # Verify port_name was passed instead of port_number
        call_kwargs = mock_lib_kubernetes.deploy_service_hijacking.call_args
        assert call_kwargs[1]["port_name"] == "http-web-svc"

    def test_run_exception_handling(self):
        """Test run method handles exceptions gracefully"""
        scenario_file = self._create_scenario_file()
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        mock_lib_kubernetes.service_exists.return_value = True
        mock_lib_kubernetes.deploy_service_hijacking.side_effect = Exception(
            "Deployment failed"
        )

        plugin = ServiceHijackingScenarioPlugin()

        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            krkn_config={},
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        assert result == 1

    def test_run_unprivileged_mode(self):
        """Test run method with privileged set to False"""
        scenario_file = self._create_scenario_file({"privileged": False})
        mock_lib_telemetry, mock_lib_kubernetes, mock_scenario_telemetry = (
            self._create_mocks()
        )

        mock_lib_kubernetes.service_exists.return_value = True
        mock_webservice = MagicMock()
        mock_webservice.pod_name = "hijacker-pod"
        mock_webservice.selector = "app=hijacker"
        mock_lib_kubernetes.deploy_service_hijacking.return_value = mock_webservice
        mock_lib_kubernetes.replace_service_selector.return_value = {
            "metadata": {"name": "nginx-service"},
            "spec": {"selector": {"app": "nginx"}},
        }

        plugin = ServiceHijackingScenarioPlugin()

        result = plugin.run(
            run_uuid=str(uuid.uuid4()),
            scenario=scenario_file,
            krkn_config={},
            lib_telemetry=mock_lib_telemetry,
            scenario_telemetry=mock_scenario_telemetry,
        )

        assert result == 0
        call_kwargs = mock_lib_kubernetes.deploy_service_hijacking.call_args
        assert call_kwargs[1]["privileged"] is False


if __name__ == "__main__":
    unittest.main()
