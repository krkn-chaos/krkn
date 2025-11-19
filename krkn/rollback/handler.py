from __future__ import annotations

import logging
from typing import cast, TYPE_CHECKING
import os
import importlib.util
import inspect

from krkn.rollback.config import RollbackConfig, RollbackContext, Version


logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

    from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
    from krkn.rollback.config import RollbackContent, RollbackCallable
    from krkn.rollback.serialization import Serializer


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
        self = cast("AbstractScenarioPlugin", self)
        # Since `AbstractScenarioPlugin.run_scenarios` will call `self.run` and pass all parameters as `kwargs`
        logger.debug(f"kwargs of ScenarioPlugin.run: {kwargs}")
        run_uuid = kwargs.get("run_uuid", None)
        # so we can safely assume that `run_uuid` will be present in `kwargs`
        assert run_uuid is not None, "run_uuid must be provided in kwargs"

        # Set context if run_uuid is available and rollback_handler exists
        if run_uuid and hasattr(self, "rollback_handler"):
            self.rollback_handler = cast("RollbackHandler", self.rollback_handler)
            self.rollback_handler.set_context(run_uuid)

        try:
            # Execute the `run` method with the original arguments
            result = func(self, *args, **kwargs)
            return result
        finally:
            # Clear context after function execution, regardless of success or failure
            if hasattr(self, "rollback_handler"):
                self.rollback_handler = cast("RollbackHandler", self.rollback_handler)
                self.rollback_handler.clear_context()

    return wrapper

def _parse_rollback_module(version_file_path: str) -> tuple[RollbackCallable, RollbackContent]:
    """
    Parse a rollback module to extract the rollback function and RollbackContent.
    
    :param version_file_path: Path to the rollback version file
    :return: Tuple of (rollback_callable, rollback_content)
    """
    
    # Create a unique module name based on the file path
    module_name = f"rollback_module_{os.path.basename(version_file_path).replace('.py', '').replace('-', '_')}"
    
    # Load the module using importlib
    spec = importlib.util.spec_from_file_location(module_name, version_file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {version_file_path}")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # Find the rollback function
    rollback_callable = None
    for name, obj in inspect.getmembers(module):
        if inspect.isfunction(obj) and name.startswith('rollback_'):
            # Check function signature
            sig = inspect.signature(obj)
            params = list(sig.parameters.values())
            if (len(params) == 2 and 
                'RollbackContent' in str(params[0].annotation) and 
                'KrknTelemetryOpenshift' in str(params[1].annotation)):
                rollback_callable = obj
                logger.debug(f"Found rollback function: {name}")
                break
    
    if rollback_callable is None:
        raise ValueError(f"No valid rollback function found in {version_file_path}")
    
    # Find the rollback_content variable
    if not hasattr(module, 'rollback_content'):
        raise ValueError("Could not find variable named 'rollback_content' in the module")
    
    rollback_content = getattr(module, 'rollback_content', None)
    if rollback_content is None:
        raise ValueError("Variable 'rollback_content' is None")
    
    logger.debug(f"Found rollback_content variable in module: {rollback_content}")
    return rollback_callable, rollback_content


def execute_rollback_version_files(
    telemetry_ocp: "KrknTelemetryOpenshift",
    run_uuid: str | None = None,
    scenario_type: str | None = None,
    ignore_auto_rollback_config: bool = False
):
    """
    Execute rollback version files for the given run_uuid and scenario_type.
    This function is called when a signal is received to perform rollback operations.
    
    :param run_uuid: Unique identifier for the run.
    :param scenario_type: Type of the scenario being rolled back.
    :param ignore_auto_rollback_config: Flag to ignore auto rollback configuration. Will be set to True for manual execute-rollback calls.
    """

    if not ignore_auto_rollback_config and RollbackConfig.auto is False:
        logger.warning(f"Auto rollback is disabled, skipping execution for run_uuid={run_uuid or '*'}, scenario_type={scenario_type or '*'}")
        return

    # Get the rollback versions directory
    version_files = RollbackConfig.search_rollback_version_files(run_uuid, scenario_type)
    if not version_files:
        logger.warning(f"Skip execution for run_uuid={run_uuid or '*'}, scenario_type={scenario_type or '*'}")
        return

    # Execute all version files in the directory
    logger.info(f"Executing rollback version files for run_uuid={run_uuid or '*'}, scenario_type={scenario_type or '*'}")
    for version_file in version_files:
        try:
            logger.info(f"Executing rollback version file: {version_file}")
            
            # Parse the rollback module to get function and content
            rollback_callable, rollback_content = _parse_rollback_module(version_file)
            # Execute the rollback function
            logger.info('Executing rollback callable...')
            rollback_callable(rollback_content, telemetry_ocp)
            logger.info('Rollback completed.')
            success = True
        except Exception as e:
            success = False
            logger.error(f"Failed to execute rollback version file {version_file}: {e}")
            raise

        # Rename the version file with .executed suffix if successful
        if success:
            try:
                executed_file = f"{version_file}.executed"
                os.rename(version_file, executed_file)
                logger.info(f"Renamed {version_file} to {executed_file} successfully.")
            except Exception as e:
                logger.error(f"Failed to rename rollback version file {version_file}: {e}")
                raise

def cleanup_rollback_version_files(run_uuid: str, scenario_type: str):
    """
    Cleanup rollback version files for the given run_uuid and scenario_type.
    This function is called to remove the rollback version files after successful scenario execution in run_scenarios.
    
    :param run_uuid: Unique identifier for the run.
    :param scenario_type: Type of the scenario being rolled back.
    """

    # Get the rollback versions directory
    version_files = RollbackConfig.search_rollback_version_files(run_uuid, scenario_type)
    if not version_files:
        logger.warning(f"Skip cleanup for run_uuid={run_uuid}, scenario_type={scenario_type or '*'}")
        return

    # Remove all version files in the directory
    logger.info(f"Cleaning up rollback version files for run_uuid={run_uuid}, scenario_type={scenario_type}")
    for version_file in version_files:
        try:
            os.remove(version_file)
            logger.info(f"Removed {version_file} successfully.")
        except Exception as e:
            logger.error(f"Failed to remove rollback version file {version_file}: {e}")
            raise

class RollbackHandler:
    def __init__(
        self,
        scenario_type: str,
        serializer: "Serializer",
    ):
        self.scenario_type = scenario_type
        self.serializer = serializer
        self.rollback_context: RollbackContext | None = (
            None  # will be set when `set_context` is called
        )

    def set_context(self, run_uuid: str):
        """
        Set the context for the rollback handler.
        :param run_uuid: Unique identifier for the run.
        """
        self.rollback_context = RollbackContext(run_uuid)
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

    def set_rollback_callable(
        self,
        callable: "RollbackCallable",
        rollback_content: "RollbackContent",
    ):
        """
        Set the rollback callable to be executed after the scenario is finished.

        :param callable: The rollback callable to be set.
        :param rollback_content: The rollback content for the callable.
        """
        logger.debug(
            f"Rollback callable set to {callable.__name__} for version directory {RollbackConfig.get_rollback_versions_directory(self.rollback_context)}"
        )

        version: Version = Version.new_version(
            scenario_type=self.scenario_type,
            rollback_context=self.rollback_context,
        )

        # Serialize the callable to a file
        try:
            version_file = self.serializer.serialize_callable(
                callable, rollback_content, version
            )
            logger.info(f"Rollback callable serialized to {version_file}")
        except Exception as e:
            logger.error(f"Failed to serialize rollback callable: {e}")
