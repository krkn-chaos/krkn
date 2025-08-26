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
    def is_rollback_version_file_format(cls, file_name: str, expected_scenario_type: str | None = None) -> bool:
        """
        Validate the format of a rollback version file name.

        Expected format: <scenario_type>_<timestamp>_<hash_suffix>.py
        where:
            - scenario_type: string (can include underscores)
            - timestamp: integer (nanoseconds since epoch)
            - hash_suffix: alphanumeric string (length 8)
            - .py: file extension

        :param file_name: The name of the file to validate.
        :param expected_scenario_type: The expected scenario type (if any) to validate against.
        :return: True if the file name matches the expected format, False otherwise.
        """
        if not file_name.endswith(".py"):
            return False

        parts = file_name.split("_")
        if len(parts) < 3:
            return False

        scenario_type = "_".join(parts[:-2])
        timestamp_str = parts[-2]
        hash_suffix_with_ext = parts[-1]
        hash_suffix = hash_suffix_with_ext[:-3]

        if expected_scenario_type and scenario_type != expected_scenario_type:
            return False

        if not timestamp_str.isdigit():
            return False

        if len(hash_suffix) != 8 or not hash_suffix.isalnum():
            return False

        return True
    
    @classmethod
    def is_rollback_context_directory_format(cls, directory_name: str, expected_run_uuid: str | None = None) -> bool:
        """
        Validate the format of a rollback context directory name.

        Expected format: <timestamp>-<run_uuid>
        where:
            - timestamp: integer (nanoseconds since epoch)
            - run_uuid: alphanumeric string

        :param directory_name: The name of the directory to validate.
        :param expected_run_uuid: The expected run UUID (if any) to validate against.
        :return: True if the directory name matches the expected format, False otherwise.
        """
        parts = directory_name.split("-", 1)
        if len(parts) != 2:
            return False

        timestamp_str, run_uuid = parts

        # Validate timestamp is numeric
        if not timestamp_str.isdigit():
            return False

        # Validate run_uuid
        if expected_run_uuid and expected_run_uuid != run_uuid:
            return False

        return True

    @classmethod
    def search_rollback_version_files(cls, run_uuid: str | None = None, scenario_type: str | None = None) -> list[str]:
        """
        Search for rollback version files based on run_uuid and scenario_type.

        1. Search directories with "run_uuid" in name under "cls.versions_directory".
        2. Search files in those directories that start with "scenario_type" in matched directories in step 1.

        :param run_uuid: Unique identifier for the run.
        :param scenario_type: Type of the scenario.
        :return: List of version file paths.
        """

        if not os.path.exists(cls().versions_directory):
            return []

        rollback_context_directories = []
        for dir in os.listdir(cls().versions_directory):
            if cls.is_rollback_context_directory_format(dir, run_uuid):
                rollback_context_directories.append(dir)
            else:
                logger.warning(f"Directory {dir} does not match expected pattern of <timestamp>-<run_uuid>")

        if not rollback_context_directories:
            logger.warning(f"No rollback context directories found for run UUID {run_uuid}")
            return []


        version_files = []
        for rollback_context_dir in rollback_context_directories:
            rollback_context_dir = os.path.join(cls().versions_directory, rollback_context_dir)

            for file in os.listdir(rollback_context_dir):
                if cls.is_rollback_version_file_format(file, scenario_type):
                    version_files.append(
                        os.path.join(rollback_context_dir, file)
                    )
                else:
                    logger.warning(
                        f"File {file} does not match expected pattern of <{scenario_type or '*'}>_<timestamp>_<hash_suffix>.py"
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
