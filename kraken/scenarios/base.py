from typing import TypeVar, Generic, Dict

from kraken.scenarios.kube import Client
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ScenarioConfig(ABC):
    """
    ScenarioConfig is a generic base class for configurations for individual scenarios. Each scenario should define
    its own configuration classes.
    """

    @abstractmethod
    def from_dict(self, data: Dict) -> None:
        """
        from_dict loads the configuration from a dict. It is mainly used to load JSON data into the scenario
        configuration.
        """

    @abstractmethod
    def validate(self) -> None:
        """
        validate is a function that validates all data on the scenario configuration. If the scenario configuration
        is invalid an Exception should be thrown.
        """
        pass


T = TypeVar('T', bound=ScenarioConfig)


class Scenario(Generic[T]):
    """
    Scenario is a generic base class that provides a uniform run function to call in a loop. Scenario implementations
    should extend this class and accept their configuration via their initializer.
    """

    @staticmethod
    def create_config(self) -> T:
        """
        create_config creates a new copy of the configuration structure that allows loading data from a dictionary
        and validating it.
        """
        pass

    def run(self, kube: Client, config: T) -> None:
        """
        run is a function that is called when the scenario should be run. A Kubernetes client implementation will be
        passed. The scenario should execute and return immediately. If the scenario fails, an Exception should be
        thrown.
        """
        pass


class TimeoutException(Exception):
    """
    TimeoutException is an exception thrown when a scenario has a timeout waiting for a condition to happen.
    """
    pass
