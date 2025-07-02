from __future__ import annotations

import logging
from typing import Callable, cast

from krkn.rollback.config import RollbackConfig, RollbackContext
from krkn.rollback.serialization import Serializer

logger = logging.getLogger(__name__)

def set_rollback_context_decorator(func):
    """
    Decorator to automatically set and clear rollback context.
    It extracts run_uuid from the function arguments and sets the context in rollback_handler
    before executing the function, and clears it after execution.

    Usage:

    .. code-block:: python
        from krkn.rollback.handler import set_rollback_context_decorator
        # for any scenario plugin that inherits from AbstractScenarioPlugin
        @set_rollback_context_decorator
        def run(
            self,
            run_uuid: str,
            scenario: str,
            krkn_config: dict[str, any],
            lib_telemetry: KrknTelemetryOpenshift,
            scenario_telemetry: ScenarioTelemetry,
        ):
            # Your scenario logic here
            pass
    """
    def wrapper(self, *args, **kwargs): 
        # Since `AbstractScenarioPlugin.run_scenarios` will call `self.run` and pass all parameters as `kwargs`
        logger.debug(f"kwargs of ScenarioPlugin.run: {kwargs}")
        run_uuid = kwargs.get('run_uuid', None)
        # so we can safely assume that `run_uuid` will be present in `kwargs`
        assert run_uuid is not None, "run_uuid must be provided in kwargs"
            
        # Set context if run_uuid is available and rollback_handler exists
        if run_uuid and hasattr(self, 'rollback_handler'):
            self.rollback_handler = cast("RollbackHandler", self.rollback_handler)
            self.rollback_handler.set_context(run_uuid)
        
        try:
            # Execute the `run` method with the original arguments
            result = func(self, *args, **kwargs)
            return result
        finally:
            # Clear context after function execution, regardless of success or failure
            if hasattr(self, 'rollback_handler'):
                self.rollback_handler = cast("RollbackHandler", self.rollback_handler)
                self.rollback_handler.clear_context()
                
    return wrapper


class RollbackHandler:
    def __init__(
        self,
        scenario_type: str,
    ):
        self.scenario_type = scenario_type
        self.serializer = Serializer(
            scenario_type=scenario_type,
        )
        self.rollback_context: RollbackContext | None = None # will be set when `set_context` is called


    def set_context(self, run_uuid: str):
        """
        Set the context for the rollback handler.
        :param scenario_types: List of scenario types.
        :param run_uuid: Unique identifier for the run.
        """
        self.rollback_context = RollbackContext(run_uuid)
        self.serializer.set_context(self.rollback_context)
        logger.info(
            f"Set rollback_context: {self.rollback_context} for scenario_type: {self.scenario_type} RollbackHandler"
        )

    def clear_context(self):
        """
        Clear the run_uuid context for the rollback handler.
        """
        logger.debug(
            f"Clear rollback_context {self.rollback_context} for scenario type {self.scenario_type} RollbackHandler"
        )
        self.rollback_context = None
        self.serializer.clear_context()

    def set_rollback_callable(self, callable: Callable, arguments=(), kwargs=None):
        """
        Set the rollback callable to be executed after the scenario is finished.

        :param callable: The callable to be executed.
        :param arguments: Tuple of arguments for the callable.
        :param kwargs: Dictionary of keyword arguments for the callable.
        """
        if kwargs is None:
            kwargs = {}

        logger.debug(
            f"Rollback callable set to {callable.__name__} for version directory {RollbackConfig.get_rollback_versions_directory(self.scenario_type, self.rollback_context)}"
        )

        # Serialize the callable to a file
        try:
            version_file = self.serializer.serialize_callable(callable, arguments, kwargs)
            logger.info(f"Rollback callable serialized to {version_file}")
        except Exception as e:
            logger.error(f"Failed to serialize rollback callable: {e}")