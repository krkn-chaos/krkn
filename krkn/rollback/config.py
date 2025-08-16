from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING, Optional
from typing_extensions import TypeAlias
import time
import os

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


@dataclass(frozen=True)
class Version:
    scenario_type: str
    rollback_context: RollbackContext
    timestamp: int = time.time_ns()  # Get current timestamp in nanoseconds
    hash_suffix: str = os.urandom(
        4
    ).hex()  # Generate a random 4-byte hexadecimal string

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
