import importlib
import inspect
import pkgutil
from typing import Type, Tuple, Optional
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class ScenarioPluginNotFound(Exception):
    pass


class ScenarioPluginFactory:

    loaded_plugins: dict[str, any] = {}
    failed_plugins: list[Tuple[str, str, str]] = []
    package_name = None

    def __init__(self, package_name: str = "krkn.scenario_plugins"):
        self.package_name = package_name
        self.__load_plugins(AbstractScenarioPlugin)

    def create_plugin(self, scenario_type: str) -> AbstractScenarioPlugin:
        """
        Creates a plugin instance based on the config.yaml scenario name.
        The scenario name is provided by the method `get_scenario_type`
        defined by the `AbstractScenarioPlugin` abstract class that must
        be implemented by all the plugins in order to be loaded correctly

        :param scenario_type: the scenario type defined in the config.yaml
            e.g. `arcaflow_scenarios`, `network_scenarios`, `plugin_scenarios`
            etc.
        :return: an instance of the class that implements this scenario and
            inherits from the AbstractScenarioPlugin abstract class
        """
        if scenario_type in self.loaded_plugins:
            return self.loaded_plugins[scenario_type](scenario_type)
        else:
            raise ScenarioPluginNotFound(
                f"Failed to load the {scenario_type} scenario plugin. "
                f"Please verify the logs to ensure it was loaded correctly."
            )

    def __load_plugins(self, base_class: Type):
        base_package = importlib.import_module(self.package_name)
        for _, module_name, is_pkg in pkgutil.walk_packages(
            base_package.__path__, base_package.__name__ + "."
        ):

            if not is_pkg:
                try:
                    module = importlib.import_module(module_name)
                except Exception as imp_exc:  
                    self.failed_plugins.append((module_name, "<module>", f"Import failed: {imp_exc}"))
                    continue

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, base_class) and obj is not base_class:
                        is_correct, exception_message = (
                            self.is_naming_convention_correct(module_name, name)
                        )
                        if not is_correct:
                            self.failed_plugins.append(
                                (module_name, name, exception_message)
                            )
                            continue

                        cls = getattr(module, name)
                        # The AbstractScenarioPlugin constructor requires a scenario_type.
                        # However, since we only need to call `get_scenario_types()` here,
                        # it is acceptable to use a placeholder value.
                        instance = cls("placeholder_scenario_type")
                        get_scenario_type = getattr(instance, "get_scenario_types")
                        scenario_types = get_scenario_type()
                        has_duplicates = False
                        for scenario_type in scenario_types:
                            if scenario_type in self.loaded_plugins.keys():
                                self.failed_plugins.append(
                                    (
                                        module_name,
                                        name,
                                        f"scenario type {scenario_type} defined by {self.loaded_plugins[scenario_type].__name__} "
                                        f"and {name} and this is not allowed.",
                                    )
                                )
                                has_duplicates = True
                                break
                        if has_duplicates:
                            continue
                        for scenario_type in scenario_types:
                            self.loaded_plugins[scenario_type] = cls

    def is_naming_convention_correct(
        self, module_name: str, class_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Defines the Krkn ScenarioPlugin API naming conventions

        :param module_name: the fully qualified module name that is loaded by
            walk_packages
        :param class_name: the plugin class name
        :return: a tuple of boolean result of the check and optional error message
        """
        # plugin file names must end with _scenario_plugin
        if not module_name.split(".")[-1].endswith("_scenario_plugin"):
            return (
                False,
                "scenario plugin module file names must end with `_scenario_plugin` suffix",
            )

        if (
            "scenario" in module_name.split(".")[-2]
            or "plugin" in module_name.split(".")[-2]
        ):
            return (
                False,
                "scenario plugin folder cannot contain `scenario` or `plugin` word",
            )

        # plugin class names must be capital camel cased and end with ScenarioPlugin
        if (
            class_name == "ScenarioPlugin"
            or not class_name.endswith("ScenarioPlugin")
            or not class_name[0].isupper()
        ):
            return (
                False,
                "scenario plugin class name must start with a capital letter, "
                "end with `ScenarioPlugin`, and cannot be just `ScenarioPlugin`.",
            )

        # plugin file name in snake case must match class name in capital camel case
        if self.__snake_to_capital_camel(module_name.split(".")[-1]) != class_name:
            return False, (
                "module file name must in snake case must match class name in capital camel case "
                "e.g. `example_scenario_plugin` -> `ExampleScenarioPlugin`"
            )

        return True, None

    def __snake_to_capital_camel(self, snake_string: str) -> str:
        return snake_string.title().replace("_", "")
