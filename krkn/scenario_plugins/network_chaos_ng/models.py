from dataclasses import dataclass
from enum import Enum
from krkn.scenario_plugins.types import ExecutionType


class NetworkChaosScenarioType(Enum):
    Node = 1
    Pod = 2

@dataclass
class BaseNetworkChaosConfig:
    id: str
    wait_duration: int
    test_duration: int
    label_selector: str
    instance_count: int
    execution: str
    namespace: str

    def validate(self) -> list[str]:
        errors = []
        if self.execution is None:
            errors.append(f"execution cannot be None, supported values are: {', '.join([e.value for e in ExecutionType])}")
        if self.execution not in [e.value for e in ExecutionType]:
            errors.append(f"{self.execution} is not in supported execution mode: {', '.join([e.value for e in ExecutionType])}")
        if self.label_selector is None:
            errors.append("label_selector cannot be None")
        return errors

@dataclass
class NetworkFilterConfig(BaseNetworkChaosConfig):
    ingress: bool
    egress: bool
    interfaces: list[str]
    target: str
    ports: list[int]

    def validate(self) -> list[str]:
        errors = super().validate()
        # here further validations
        return errors
