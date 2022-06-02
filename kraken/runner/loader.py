from typing import List, Dict

from kraken.scenarios.base import Scenario
from kraken.scenarios.runner import ScenarioRunnerConfig


class Loader:
    def __init__(self, scenarios: List[Scenario]):
        self.scenarios = scenarios

    def load(self, data: Dict) -> ScenarioRunnerConfig:
        """
        This function loads data from a dictionary and produces a scenario runner config. It uses the scenarios provided
        when instantiating the loader.
        """

