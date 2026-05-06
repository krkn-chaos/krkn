import importlib
import inspect
import logging
import pkgutil
import queue
import threading
from typing import Type, Tuple, Optional, Any
from krkn.health_checks.abstract_health_check_plugin import AbstractHealthCheckPlugin


class HealthCheckPluginNotFound(Exception):
    """Exception raised when a requested health check plugin cannot be found."""
    pass


class HealthCheckFactory:
    """
    Factory class for dynamically loading and creating health check plugin instances.

    This factory automatically discovers and loads all health check plugins in the
    krkn.health_checks package that follow the naming conventions and inherit from
    AbstractHealthCheckPlugin.
    """

    loaded_plugins: dict[str, Any] = {}
    failed_plugins: list[Tuple[str, str, str]] = []
    config_key_map: dict[str, str] = {}
    package_name = None
    active_plugins: list = []

    def __init__(self, package_name: str = "krkn.health_checks"):
        """
        Initializes the HealthCheckFactory and loads all available health check plugins.

        :param package_name: the package to scan for health check plugins
        """
        self.package_name = package_name
        self.active_plugins = []
        self.config_key_map = {}
        self.__load_plugins(AbstractHealthCheckPlugin)

    def create_plugin(
        self, health_check_type: str, iterations: int = 1, **kwargs
    ) -> AbstractHealthCheckPlugin:
        """
        Creates a health check plugin instance based on the config.yaml health check type.
        The health check type is provided by the method `get_health_check_types`
        defined by the `AbstractHealthCheckPlugin` abstract class that must
        be implemented by all the plugins in order to be loaded correctly.

        :param health_check_type: the health check type defined in the config.yaml
            e.g. `http_health_check`, `vm_health_check`, etc.
        :param iterations: the number of iterations for the health check
        :param kwargs: additional keyword arguments to pass to the plugin constructor
        :return: an instance of the class that implements this health check and
            inherits from the AbstractHealthCheckPlugin abstract class
        """
        if health_check_type in self.loaded_plugins:
            plugin = self.loaded_plugins[health_check_type](
                health_check_type, iterations=iterations, **kwargs
            )
            self.active_plugins.append(plugin)
            return plugin
        else:
            raise HealthCheckPluginNotFound(
                f"Failed to load the {health_check_type} health check plugin. "
                f"Please verify the logs to ensure it was loaded correctly."
            )

    def increment_all_iterations(self) -> None:
        """
        Increments the iteration counter on all active plugin instances created by this factory.

        :return: None
        """
        for plugin in self.active_plugins:
            plugin.increment_iterations()

    def stop_all(self) -> None:
        """
        Signals all active plugin instances to stop their health check loops.
        Call this before joining worker threads when the main loop exits early
        (e.g. on a STOP signal, critical alert, or daemon mode with iterations=inf).

        :return: None
        """
        for plugin in self.active_plugins:
            plugin.stop()

    def start_all(
        self, config: dict[str, Any], iterations: int = 1, **kwargs
    ) -> list[tuple[AbstractHealthCheckPlugin, Any, Any]]:
        """
        Starts all health check plugins that have a matching section in config.

        Iterates over ``config_key_map`` and for each key present in config:

        - Plugins where ``manages_own_threads()`` returns ``True`` (e.g. virt) have
          ``run_health_check()`` called directly and use a ``SimpleQueue``.
          ``worker=None`` is stored as the sentinel so callers can detect this case
          and use ``plugin.thread_join()`` instead of ``worker.join()``.

        - All other plugins are wrapped in an external ``threading.Thread`` and use
          a standard ``Queue``.

        Any extra ``kwargs`` (e.g. ``krkn_lib=kubecli``) are forwarded to
        ``create_plugin()``; plugins that don't need them ignore them via ``**kwargs``
        in their constructors.

        :param config: the full config dict loaded from config.yaml
        :param iterations: the number of chaos iterations to run
        :param kwargs: additional keyword arguments forwarded to each plugin constructor
        :return: list of ``(plugin, worker_thread, telemetry_queue)`` tuples;
                 ``worker_thread`` is ``None`` for self-threading plugins
        """
        checkers = []
        for config_key, plugin_type in self.config_key_map.items():
            plugin_config = config.get(config_key)
            if not plugin_config:
                continue
            try:
                plugin = self.create_plugin(
                    health_check_type=plugin_type,
                    iterations=iterations,
                    **kwargs
                )
                if plugin.manages_own_threads():
                    tq = queue.SimpleQueue()
                    plugin.run_health_check(plugin_config, tq)
                    checkers.append((plugin, None, tq))
                else:
                    tq = queue.Queue()
                    worker = threading.Thread(
                        target=plugin.run_health_check,
                        args=(plugin_config, tq)
                    )
                    worker.start()
                    checkers.append((plugin, worker, tq))
                logging.info(
                    f"Started health check plugin '{plugin_type}' "
                    f"reading from config key '{config_key}'"
                )
            except HealthCheckPluginNotFound:
                logging.warning(
                    f"Health check plugin '{plugin_type}' not found, skipping"
                )
        return checkers

    def __load_plugins(self, base_class: Type):
        """
        Loads all plugins that inherit from the base class.

        :param base_class: the base class that plugins must inherit from
        """
        base_package = importlib.import_module(self.package_name)
        for _, module_name, is_pkg in pkgutil.walk_packages(
            base_package.__path__, base_package.__name__ + "."
        ):

            if not is_pkg:
                # Skip modules that don't follow the naming convention
                if not module_name.split(".")[-1].endswith("_health_check_plugin"):
                    continue

                try:
                    module = importlib.import_module(module_name)
                except Exception as e:
                    self.failed_plugins.append(
                        (
                            module_name,
                            "N/A",
                            f"Failed to import module: {str(e)}"
                        )
                    )
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
                        # The AbstractHealthCheckPlugin constructor requires a health_check_type.
                        # However, since we only need to call `get_health_check_types()` here,
                        # it is acceptable to use a placeholder value.
                        instance = cls("placeholder_health_check_type")
                        get_health_check_types = getattr(instance, "get_health_check_types")
                        health_check_types = get_health_check_types()
                        has_duplicates = False
                        for health_check_type in health_check_types:
                            if health_check_type in self.loaded_plugins.keys():
                                self.failed_plugins.append(
                                    (
                                        module_name,
                                        name,
                                        f"health check type {health_check_type} defined by {self.loaded_plugins[health_check_type].__name__} "
                                        f"and {name} and this is not allowed.",
                                    )
                                )
                                has_duplicates = True
                                break
                        if has_duplicates:
                            continue
                        for health_check_type in health_check_types:
                            self.loaded_plugins[health_check_type] = cls

                        # Register the config key → primary health check type mapping
                        config_key = instance.get_config_key()
                        if config_key:
                            if config_key in self.config_key_map:
                                self.failed_plugins.append(
                                    (
                                        module_name,
                                        name,
                                        f"config key '{config_key}' is already registered by "
                                        f"{self.config_key_map[config_key]} and this is not allowed.",
                                    )
                                )
                            else:
                                self.config_key_map[config_key] = health_check_types[0]

    def is_naming_convention_correct(
        self, module_name: str, class_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Defines the Krkn HealthCheckPlugin API naming conventions.

        :param module_name: the fully qualified module name that is loaded by
            walk_packages
        :param class_name: the plugin class name
        :return: a tuple of boolean result of the check and optional error message
        """
        # plugin file names must end with _health_check_plugin
        if not module_name.split(".")[-1].endswith("_health_check_plugin"):
            return (
                False,
                "health check plugin module file names must end with `_health_check_plugin` suffix",
            )

        # plugin class names must be capital camel cased and end with HealthCheckPlugin
        if (
            class_name == "HealthCheckPlugin"
            or not class_name.endswith("HealthCheckPlugin")
            or not class_name[0].isupper()
        ):
            return (
                False,
                "health check plugin class name must start with a capital letter, "
                "end with `HealthCheckPlugin`, and cannot be just `HealthCheckPlugin`.",
            )

        # plugin file name in snake case must match class name in capital camel case
        if self.__snake_to_capital_camel(module_name.split(".")[-1]) != class_name:
            return False, (
                "module file name in snake case must match class name in capital camel case "
                "e.g. `http_health_check_plugin` -> `HttpHealthCheckPlugin`"
            )

        return True, None

    def __snake_to_capital_camel(self, snake_string: str) -> str:
        """
        Converts snake_case string to CapitalCamelCase.

        :param snake_string: the snake_case string
        :return: the CapitalCamelCase string
        """
        return snake_string.title().replace("_", "")
