from abc import ABC, abstractmethod
from enum import Enum


class HealthCheckDecision(Enum):
    GO = "GO"
    PAUSE = "PAUSE"
    STOP = "STOP"


class HealthChecker(ABC):
    @abstractmethod
    def check(self) -> HealthCheckDecision:
        pass
