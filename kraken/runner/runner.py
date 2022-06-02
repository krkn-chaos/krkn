from dataclasses import dataclass
from typing import List

from kraken.scenarios import base

from kraken.scenarios.health import HealthChecker


@dataclass
class ScenarioRunnerConfig:
    iterations: int
    steps: List[base.ScenarioConfig]


class ScenarioRunner:
    """
    This class provides the services to load a scenario configuration and iterate over the scenarios, while
    observing the health checks.
    """

    def __init__(self, scenarios: List[base.Scenario], health_checker: HealthChecker):
        self._scenarios = scenarios
        self._health_checker = health_checker

    def run(self, config: ScenarioRunnerConfig):
        """
        This function runs a list of scenarios described in the configuration.
        """
