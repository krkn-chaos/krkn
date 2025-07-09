from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict, Callable, TYPE_CHECKING
from typing_extensions import TypeAlias
import time

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

    namespace: str
    resource_identifier: str


class RollbackContext(str):
    """
    RollbackContext is a string formatted as '<timestamp (s) >-<run_uuid>'.
    It represents the context for rollback operations, uniquely identifying a run.
    """

    def __new__(cls, run_uuid: str):
        timestamp = int(time.time())
        return super().__new__(cls, f"{timestamp}-{run_uuid}")


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
    def get_scenario_rollback_versions_directory(
        cls, scenario_type: str, rollback_context: RollbackContext
    ) -> str:
        """
        Get the rollback context directory for a given scenario type and rollback context.

        :param scenario_type: The type of the scenario.
        :param rollback_context: The rollback context string.
        :return: The path to the rollback context directory.
        """
        return f"{cls().versions_directory}/{rollback_context}/{scenario_type}"

    @classmethod
    def get_rollback_versions_directory(cls, rollback_context: RollbackContext) -> str:
        """
        Get the rollback context directory for a given rollback context.

        :param rollback_context: The rollback context string.
        :return: The path to the rollback context directory.
        """
        return f"{cls().versions_directory}/{rollback_context}"
