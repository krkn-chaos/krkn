from __future__ import annotations

import logging
from typing import cast, TYPE_CHECKING
import sys
import subprocess
import os

from krkn.rollback.config import RollbackConfig, RollbackContext, Version
from krkn.rollback.serialization import Serializer

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
    from krkn.rollback.config import RollbackContent, RollbackCallable


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

def execute_rollback_version_files(run_uuid: str, scenario_type: str | None = None):
    """
    Execute rollback version files for the given run_uuid and scenario_type.
    This function is called when a signal is received to perform rollback operations.
    
    :param run_uuid: Unique identifier for the run.
    :param scenario_type: Type of the scenario being rolled back.
    """
    
    # Get the rollback versions directory
    version_files = RollbackConfig.search_rollback_version_files(run_uuid, scenario_type)
    
    # Execute all version files in the directory
    logger.info(f"Executing rollback version files for run_uuid={run_uuid}, scenario_type={scenario_type or '*'}")
    for version_file in version_files:
        try:
            logger.info(f"Executing rollback version file: {version_file}")
            # Use subprocess to execute the version file with real-time output
            logger.info(f"Starting execution of rollback version file: {version_file}")
            process = subprocess.Popen(
                [sys.executable, version_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
            
            # Stream output in real-time
            for line in process.stdout:
                line = line.rstrip('\n')
                logger.info(f"[{version_file}] {line}")
            
            # Wait for process to complete and check return code
            return_code = process.wait()
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, [sys.executable, version_file])
            
            logger.info(f"Executed {version_file} successfully.")
        except Exception as e:
            logger.error(f"Failed to execute rollback version file {version_file}: {e}")
            raise

def cleanup_rollback_version_files(run_uuid: str, scenario_type: str):
    """
    Cleanup rollback version files for the given run_uuid and scenario_type.
    This function is called to remove the rollback version files after execution.
    
    :param run_uuid: Unique identifier for the run.
    :param scenario_type: Type of the scenario being rolled back.
    """
    
    # Get the rollback versions directory
    version_files = RollbackConfig.search_rollback_version_files(run_uuid, scenario_type)
    
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
    ):
        self.scenario_type = scenario_type
        self.serializer = Serializer(
            scenario_type=scenario_type,
        )
        self.rollback_context: RollbackContext | None = (
            None  # will be set when `set_context` is called
        )

    def set_context(self, run_uuid: str):
        """
        Set the context for the rollback handler.
        :param scenario_types: List of scenario types.
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
        callable: RollbackCallable,
        rollback_content: RollbackContent,
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
