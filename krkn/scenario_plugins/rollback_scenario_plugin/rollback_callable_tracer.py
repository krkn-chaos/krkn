import logging
import time
from typing import Callable

from krkn.scenario_plugins.rollback_scenario_plugin.serialization import Serializer


class RollbackCallableTracer:
    def __init__(self, version_directory: str):
        self.version_directory = version_directory
        self.serializer = Serializer(version_directory)

    def set_rollback_callable(self, callable: Callable, arguments=(), kwargs=None):
        """
        Set the rollback callable to be executed after the scenario is finished.
        :param callable: The callable to be executed.
        :param arguments: Tuple of arguments for the callable.
        :param kwargs: Dictionary of keyword arguments for the callable.
        """
        if kwargs is None:
            kwargs = {}

        logging.info(
            f"Rollback callable set to {callable.__name__} for version directory {self.version_directory}"
        )

        # Serialize the callable to a file
        try:
            version_file = self.serializer.serialize_callable(callable, arguments, kwargs)
            logging.info(f"Rollback callable serialized to {version_file}")
        except Exception as e:
            logging.error(f"Failed to serialize rollback callable: {e}")
