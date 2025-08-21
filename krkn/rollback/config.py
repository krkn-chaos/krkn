from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING, Optional
from typing_extensions import TypeAlias
import time
import os
import logging

from krkn_lib.utils import get_random_string

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

RollbackCallable: TypeAlias = Callable[
    ["RollbackContent", "KrknTelemetryOpenshift"], None
]


if TYPE_CHECKING:
    from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

RollbackCallable: TypeAlias = Callable[
    ["RollbackContent", "KrknTelemetryOpenshift"], None
]


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


@dataclass(frozen=True)
class RollbackContent:
    """
    RollbackContent is a dataclass that defines the necessary fields for rollback operations.
    """

    resource_identifier: str
    namespace: Optional[str] = None

    def __str__(self):
        namespace = f'"{self.namespace}"' if self.namespace else "None"
        resource_identifier = f'"{self.resource_identifier}"'
        return f"RollbackContent(namespace={namespace}, resource_identifier={resource_identifier})"


class RollbackContext(str):
    """
    RollbackContext is a string formatted as '<timestamp (s) >-<run_uuid>'.
    It represents the context for rollback operations, uniquely identifying a run.
    """

    def __new__(cls, run_uuid: str):
        return super().__new__(cls, f"{time.time_ns()}-{run_uuid}")


class RollbackConfig(metaclass=SingletonMeta):
    """Configuration for the rollback scenarios."""

    def __init__(self):
        self._auto = False
        self._versions_directory = ""
        self._registered = False

    @property
    def auto(self):
        return self._auto

    @auto.setter
    def auto(self, value):
        if self._registered:
            raise AttributeError("Can't modify 'auto' after registration")
        self._auto = value

    @property
    def versions_directory(self):
        return self._versions_directory

    @versions_directory.setter
    def versions_directory(self, value):
        if self._registered:
            raise AttributeError("Can't modify 'versions_directory' after registration")
        self._versions_directory = value
    @classmethod
    def register(cls, auto=False, versions_directory=""):
        """Initialize and return the singleton instance with given configuration."""
        instance = cls()
        instance.auto = auto
        instance.versions_directory = versions_directory
        instance._registered = True
        return instance

    @classmethod
    def get_rollback_versions_directory(cls, rollback_context: RollbackContext) -> str:
        """
        Get the rollback context directory for a given rollback context.

        :param rollback_context: The rollback context string.
        :return: The path to the rollback context directory.
        """
        return f"{cls().versions_directory}/{rollback_context}"
    
    @classmethod
    def search_rollback_version_files(cls, run_uuid: str, scenario_type: str | None = None) -> list[str]:
        """
        Search for rollback version files based on run_uuid and scenario_type.

        1. Search directories with "run_uuid" in name under "cls.versions_directory".
        2. Search files in those directories that start with "scenario_type" in matched directories in step 1.

        :param run_uuid: Unique identifier for the run.
        :param scenario_type: Type of the scenario.
        :return: List of version file paths.
        """
        rollback_context_directories = [
            dirname for dirname in os.listdir(cls().versions_directory) if run_uuid in dirname
        ]
        if not rollback_context_directories:
            logger.warning(f"No rollback context directories found for run UUID {run_uuid}")
            return []

        if len(rollback_context_directories) > 1:
            logger.warning(
                f"Expected one directory for run UUID {run_uuid}, found: {rollback_context_directories}"
            )

        rollback_context_directory = rollback_context_directories[0]

        version_files = []
        scenario_rollback_versions_directory = os.path.join(
            cls().versions_directory, rollback_context_directory
        )
        for file in os.listdir(scenario_rollback_versions_directory):
            # assert all files start with scenario_type and end with .py
            if file.endswith(".py") and (scenario_type is None or file.startswith(scenario_type)):
                version_files.append(
                    os.path.join(scenario_rollback_versions_directory, file)
                )
            else:
                logger.warning(
                    f"File {file} does not match expected pattern for scenario type {scenario_type}"
                )
        return version_files

@dataclass(frozen=True)
class Version:
    scenario_type: str
    rollback_context: RollbackContext
    timestamp: int = time.time_ns()  # Get current timestamp in nanoseconds
    hash_suffix: str = get_random_string(8)  # Generate a random string of 8 characters

    @property
    def version_file_name(self) -> str:
        """
        Generate a version file name based on the timestamp and hash suffix.
        :return: The generated version file name.
        """
        return f"{self.scenario_type}_{self.timestamp}_{self.hash_suffix}.py"

    @property
    def version_file_full_path(self) -> str:
        """
        Get the full path for the version file based on the version object and current context.

        :return: The generated version file full path.
        """
        return f"{RollbackConfig.get_rollback_versions_directory(self.rollback_context)}/{self.version_file_name}"

    @staticmethod
    def new_version(scenario_type: str, rollback_context: RollbackContext) -> "Version":
        """
        Get the current version of the rollback configuration.
        :return: An instance of Version with the current timestamp and hash suffix.
        """
        return Version(
            scenario_type=scenario_type,
            rollback_context=rollback_context,
        )
