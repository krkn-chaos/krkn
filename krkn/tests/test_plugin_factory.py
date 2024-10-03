import unittest

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.scenario_plugin_factory import ScenarioPluginFactory
from krkn.tests.test_classes.correct_scenario_plugin import (
    CorrectScenarioPlugin,
)


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
