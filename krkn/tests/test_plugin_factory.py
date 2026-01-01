import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.scenario_plugin_factory import ScenarioPluginFactory
from krkn.scenario_plugins.native.plugins import PluginStep, Plugins, PLUGINS
from krkn.tests.test_classes.correct_scenario_plugin import (
    CorrectScenarioPlugin,
)
import yaml



class TestPluginFactory(unittest.TestCase):

    def test_plugin_factory(self):
        factory = ScenarioPluginFactory("krkn.tests.test_classes")
        self.assertEqual(len(factory.loaded_plugins), 5)
        self.assertEqual(len(factory.failed_plugins), 4)
        self.assertIs(
            factory.loaded_plugins["correct_scenarios"].__base__,
            AbstractScenarioPlugin,
        )
        self.assertTrue(
            isinstance(
                factory.loaded_plugins["correct_scenarios"](), CorrectScenarioPlugin
            )
        )
        # soLid
        self.assertTrue(
            isinstance(
                factory.loaded_plugins["correct_scenarios"](), AbstractScenarioPlugin
            )
        )

        self.assertTrue(
            "krkn.tests.test_classes.snake_case_mismatch_scenario_plugin"
            in [p[0] for p in factory.failed_plugins]
        )
        self.assertTrue(
            "krkn.tests.test_classes.wrong_classname_scenario_plugin"
            in [p[0] for p in factory.failed_plugins]
        )
        self.assertTrue(
            "krkn.tests.test_classes.wrong_module"
            in [p[0] for p in factory.failed_plugins]
        )

    def test_plugin_factory_naming_convention(self):
        factory = ScenarioPluginFactory()
        correct_module_name = "krkn.scenario_plugins.example.correct_scenario_plugin"
        correct_class_name = "CorrectScenarioPlugin"
        correct_class_name_no_match = "NoMatchScenarioPlugin"
        wrong_module_name = "krkn.scenario_plugins.example.correct_plugin"
        wrong_class_name = "WrongScenario"
        wrong_folder_name_plugin = (
            "krkn.scenario_plugins.example_plugin.example_plugin_scenario_plugin"
        )
        wrong_folder_name_plugin_class_name = "ExamplePluginScenarioPlugin"
        wrong_folder_name_scenario = (
            "krkn.scenario_plugins.example_scenario.example_scenario_scenario_plugin"
        )
        wrong_folder_name_scenario_class_name = "ExampleScenarioScenarioPlugin"

        result, message = factory.is_naming_convention_correct(
            correct_module_name, correct_class_name
        )
        self.assertTrue(result)
        self.assertIsNone(message)

        result, message = factory.is_naming_convention_correct(
            wrong_module_name, correct_class_name
        )
        self.assertFalse(result)
        self.assertEqual(
            message,
            "scenario plugin module file names must end with `_scenario_plugin` suffix",
        )

        result, message = factory.is_naming_convention_correct(
            correct_module_name, wrong_class_name
        )
        self.assertFalse(result)
        self.assertEqual(
            message,
            "scenario plugin class name must start with a capital letter, "
            "end with `ScenarioPlugin`, and cannot be just `ScenarioPlugin`.",
        )

        result, message = factory.is_naming_convention_correct(
            correct_module_name, correct_class_name_no_match
        )
        self.assertFalse(result)
        self.assertEqual(
            message,
            "module file name must in snake case must match class name in capital camel case "
            "e.g. `example_scenario_plugin` -> `ExampleScenarioPlugin`",
        )

        result, message = factory.is_naming_convention_correct(
            wrong_folder_name_plugin, wrong_folder_name_plugin_class_name
        )
        self.assertFalse(result)
        self.assertEqual(
            message, "scenario plugin folder cannot contain `scenario` or `plugin` word"
        )

        result, message = factory.is_naming_convention_correct(
            wrong_folder_name_scenario, wrong_folder_name_scenario_class_name
        )
        self.assertFalse(result)
        self.assertEqual(
            message, "scenario plugin folder cannot contain `scenario` or `plugin` word"
        )


class TestPluginStep(unittest.TestCase):
    """Test cases for PluginStep class"""

    def setUp(self):
        """Set up test fixtures"""
        # Create a mock schema
        self.mock_schema = Mock()
        self.mock_schema.id = "test_step"

        # Create mock output
        mock_output = Mock()
        mock_output.serialize = Mock(return_value={"status": "success", "message": "test"})
        self.mock_schema.outputs = {
            "success": mock_output,
            "error": mock_output
        }

        self.plugin_step = PluginStep(
            schema=self.mock_schema,
            error_output_ids=["error"]
        )

    def test_render_output(self):
        """Test render_output method"""
        output_id = "success"
        output_data = {"status": "success", "message": "test output"}

        result = self.plugin_step.render_output(output_id, output_data)

        # Verify it returns a JSON string
        self.assertIsInstance(result, str)

        # Verify it can be parsed as JSON
        parsed = json.loads(result)
        self.assertEqual(parsed["output_id"], output_id)
        self.assertIn("output_data", parsed)


class TestPlugins(unittest.TestCase):
    """Test cases for Plugins class"""

    def setUp(self):
        """Set up test fixtures"""
        # Create mock steps with proper id attribute
        self.mock_step1 = Mock()
        self.mock_step1.id = "step1"

        self.mock_step2 = Mock()
        self.mock_step2.id = "step2"

        self.plugin_step1 = PluginStep(schema=self.mock_step1, error_output_ids=["error"])
        self.plugin_step2 = PluginStep(schema=self.mock_step2, error_output_ids=["error"])

    def test_init_with_valid_steps(self):
        """Test Plugins initialization with valid steps"""
        plugins = Plugins([self.plugin_step1, self.plugin_step2])

        self.assertEqual(len(plugins.steps_by_id), 2)
        self.assertIn("step1", plugins.steps_by_id)
        self.assertIn("step2", plugins.steps_by_id)

    def test_init_with_duplicate_step_ids(self):
        """Test Plugins initialization with duplicate step IDs raises exception"""
        # Create two steps with the same ID
        duplicate_step = PluginStep(schema=self.mock_step1, error_output_ids=["error"])

        with self.assertRaises(Exception) as context:
            Plugins([self.plugin_step1, duplicate_step])

        self.assertIn("Duplicate step ID", str(context.exception))

    def test_unserialize_scenario(self):
        """Test unserialize_scenario method"""
        # Create a temporary YAML file
        test_data = [
            {"id": "test_step", "config": {"param": "value"}}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_file = f.name

        try:
            plugins = Plugins([self.plugin_step1])
            result = plugins.unserialize_scenario(temp_file)

            self.assertIsInstance(result, list)
        finally:
            Path(temp_file).unlink()

    def test_run_with_invalid_scenario_not_list(self):
        """Test run method with scenario that is not a list"""
        # Create a temporary YAML file with dict instead of list
        test_data = {"id": "test_step", "config": {"param": "value"}}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_file = f.name

        try:
            plugins = Plugins([self.plugin_step1])

            with self.assertRaises(Exception) as context:
                plugins.run(temp_file, "/path/to/kubeconfig", "/path/to/kraken_config", "test-uuid")

            self.assertIn("expected list", str(context.exception))
        finally:
            Path(temp_file).unlink()

    def test_run_with_invalid_entry_not_dict(self):
        """Test run method with entry that is not a dict"""
        # Create a temporary YAML file with list of strings instead of dicts
        test_data = ["invalid", "entries"]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_file = f.name

        try:
            plugins = Plugins([self.plugin_step1])

            with self.assertRaises(Exception) as context:
                plugins.run(temp_file, "/path/to/kubeconfig", "/path/to/kraken_config", "test-uuid")

            self.assertIn("expected a list of dict's", str(context.exception))
        finally:
            Path(temp_file).unlink()

    def test_run_with_missing_id_field(self):
        """Test run method with missing 'id' field"""
        # Create a temporary YAML file with missing id
        test_data = [
            {"config": {"param": "value"}}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_file = f.name

        try:
            plugins = Plugins([self.plugin_step1])

            with self.assertRaises(Exception) as context:
                plugins.run(temp_file, "/path/to/kubeconfig", "/path/to/kraken_config", "test-uuid")

            self.assertIn("missing 'id' field", str(context.exception))
        finally:
            Path(temp_file).unlink()

    def test_run_with_missing_config_field(self):
        """Test run method with missing 'config' field"""
        # Create a temporary YAML file with missing config
        test_data = [
            {"id": "step1"}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_file = f.name

        try:
            plugins = Plugins([self.plugin_step1])

            with self.assertRaises(Exception) as context:
                plugins.run(temp_file, "/path/to/kubeconfig", "/path/to/kraken_config", "test-uuid")

            self.assertIn("missing 'config' field", str(context.exception))
        finally:
            Path(temp_file).unlink()

    def test_run_with_invalid_step_id(self):
        """Test run method with invalid step ID"""
        # Create a proper mock schema with string ID
        mock_schema = Mock()
        mock_schema.id = "valid_step"
        plugin_step = PluginStep(schema=mock_schema, error_output_ids=["error"])

        # Create a temporary YAML file with unknown step ID
        test_data = [
            {"id": "unknown_step", "config": {"param": "value"}}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_file = f.name

        try:
            plugins = Plugins([plugin_step])

            with self.assertRaises(Exception) as context:
                plugins.run(temp_file, "/path/to/kubeconfig", "/path/to/kraken_config", "test-uuid")

            self.assertIn("Invalid step", str(context.exception))
            self.assertIn("expected one of", str(context.exception))
        finally:
            Path(temp_file).unlink()

    @patch('krkn.scenario_plugins.native.plugins.logging')
    def test_run_with_valid_scenario(self, mock_logging):
        """Test run method with valid scenario"""
        # Create mock schema with all necessary attributes
        mock_schema = Mock()
        mock_schema.id = "test_step"

        # Mock input schema
        mock_input = Mock()
        mock_input.properties = {}
        mock_input.unserialize = Mock(return_value=Mock(spec=[]))
        mock_schema.input = mock_input

        # Mock output
        mock_output = Mock()
        mock_output.serialize = Mock(return_value={"status": "success"})
        mock_schema.outputs = {"success": mock_output}

        # Mock schema call
        mock_schema.return_value = ("success", {"status": "success"})

        plugin_step = PluginStep(schema=mock_schema, error_output_ids=["error"])

        # Create a temporary YAML file
        test_data = [
            {"id": "test_step", "config": {"param": "value"}}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_file = f.name

        try:
            plugins = Plugins([plugin_step])
            plugins.run(temp_file, "/path/to/kubeconfig", "/path/to/kraken_config", "test-uuid")

            # Verify schema was called
            mock_schema.assert_called_once()
        finally:
            Path(temp_file).unlink()

    @patch('krkn.scenario_plugins.native.plugins.logging')
    def test_run_with_error_output(self, mock_logging):
        """Test run method when step returns error output"""
        # Create mock schema with error output
        mock_schema = Mock()
        mock_schema.id = "test_step"

        # Mock input schema
        mock_input = Mock()
        mock_input.properties = {}
        mock_input.unserialize = Mock(return_value=Mock(spec=[]))
        mock_schema.input = mock_input

        # Mock output
        mock_output = Mock()
        mock_output.serialize = Mock(return_value={"error": "test error"})
        mock_schema.outputs = {"error": mock_output}

        # Mock schema call to return error
        mock_schema.return_value = ("error", {"error": "test error"})

        plugin_step = PluginStep(schema=mock_schema, error_output_ids=["error"])

        # Create a temporary YAML file
        test_data = [
            {"id": "test_step", "config": {"param": "value"}}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_file = f.name

        try:
            plugins = Plugins([plugin_step])

            with self.assertRaises(Exception) as context:
                plugins.run(temp_file, "/path/to/kubeconfig", "/path/to/kraken_config", "test-uuid")

            self.assertIn("failed", str(context.exception))
        finally:
            Path(temp_file).unlink()

    @patch('krkn.scenario_plugins.native.plugins.logging')
    def test_run_with_kubeconfig_path_injection(self, mock_logging):
        """Test run method injects kubeconfig_path when property exists"""
        # Create mock schema with kubeconfig_path in input properties
        mock_schema = Mock()
        mock_schema.id = "test_step"

        # Mock input schema with kubeconfig_path property
        mock_input_instance = Mock()
        mock_input = Mock()
        mock_input.properties = {"kubeconfig_path": Mock()}
        mock_input.unserialize = Mock(return_value=mock_input_instance)
        mock_schema.input = mock_input

        # Mock output
        mock_output = Mock()
        mock_output.serialize = Mock(return_value={"status": "success"})
        mock_schema.outputs = {"success": mock_output}

        # Mock schema call
        mock_schema.return_value = ("success", {"status": "success"})

        plugin_step = PluginStep(schema=mock_schema, error_output_ids=["error"])

        # Create a temporary YAML file
        test_data = [
            {"id": "test_step", "config": {"param": "value"}}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_file = f.name

        try:
            plugins = Plugins([plugin_step])
            plugins.run(temp_file, "/custom/kubeconfig", "/path/to/kraken_config", "test-uuid")

            # Verify kubeconfig_path was set
            self.assertEqual(mock_input_instance.kubeconfig_path, "/custom/kubeconfig")
        finally:
            Path(temp_file).unlink()

    @patch('krkn.scenario_plugins.native.plugins.logging')
    def test_run_with_kraken_config_injection(self, mock_logging):
        """Test run method injects kraken_config when property exists"""
        # Create mock schema with kraken_config in input properties
        mock_schema = Mock()
        mock_schema.id = "test_step"

        # Mock input schema with kraken_config property
        mock_input_instance = Mock()
        mock_input = Mock()
        mock_input.properties = {"kraken_config": Mock()}
        mock_input.unserialize = Mock(return_value=mock_input_instance)
        mock_schema.input = mock_input

        # Mock output
        mock_output = Mock()
        mock_output.serialize = Mock(return_value={"status": "success"})
        mock_schema.outputs = {"success": mock_output}

        # Mock schema call
        mock_schema.return_value = ("success", {"status": "success"})

        plugin_step = PluginStep(schema=mock_schema, error_output_ids=["error"])

        # Create a temporary YAML file
        test_data = [
            {"id": "test_step", "config": {"param": "value"}}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_file = f.name

        try:
            plugins = Plugins([plugin_step])
            plugins.run(temp_file, "/path/to/kubeconfig", "/custom/kraken.yaml", "test-uuid")

            # Verify kraken_config was set
            self.assertEqual(mock_input_instance.kraken_config, "/custom/kraken.yaml")
        finally:
            Path(temp_file).unlink()

    def test_json_schema(self):
        """Test json_schema method"""
        # Create mock schema with jsonschema support
        mock_schema = Mock()
        mock_schema.id = "test_step"

        plugin_step = PluginStep(schema=mock_schema, error_output_ids=["error"])

        with patch('krkn.scenario_plugins.native.plugins.jsonschema') as mock_jsonschema:
            # Mock the step_input function
            mock_jsonschema.step_input.return_value = {
                "$id": "http://example.com",
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "Test Schema",
                "description": "Test description",
                "type": "object",
                "properties": {"param": {"type": "string"}}
            }

            plugins = Plugins([plugin_step])
            result = plugins.json_schema()

            # Verify it returns a JSON string
            self.assertIsInstance(result, str)

            # Parse and verify structure
            parsed = json.loads(result)
            self.assertEqual(parsed["$id"], "https://github.com/redhat-chaos/krkn/")
            self.assertEqual(parsed["type"], "array")
            self.assertEqual(parsed["minContains"], 1)
            self.assertIn("items", parsed)
            self.assertIn("oneOf", parsed["items"])

            # Verify step is included
            self.assertEqual(len(parsed["items"]["oneOf"]), 1)
            step_schema = parsed["items"]["oneOf"][0]
            self.assertEqual(step_schema["properties"]["id"]["const"], "test_step")


class TestPLUGINSConstant(unittest.TestCase):
    """Test cases for the PLUGINS constant"""

    def test_plugins_initialized(self):
        """Test that PLUGINS constant is properly initialized"""
        self.assertIsInstance(PLUGINS, Plugins)

        # Verify all expected steps are registered
        expected_steps = [
            "run_python",
            "network_chaos",
            "pod_network_outage",
            "pod_egress_shaping",
            "pod_ingress_shaping"
        ]

        for step_id in expected_steps:
            self.assertIn(step_id, PLUGINS.steps_by_id)

        # Ensure the registered id matches the decorator and no legacy alias is present
        self.assertEqual(
            PLUGINS.steps_by_id["pod_network_outage"].schema.id,
            "pod_network_outage",
        )
        self.assertNotIn("pod_outage", PLUGINS.steps_by_id)

    def test_plugins_step_count(self):
        """Test that PLUGINS has the expected number of steps"""
        self.assertEqual(len(PLUGINS.steps_by_id), 5)
