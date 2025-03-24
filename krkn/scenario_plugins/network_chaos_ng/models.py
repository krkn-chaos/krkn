from dataclasses import dataclass
from enum import Enum


class NetworkChaosScenarioType(Enum):
    Node = 1
    Pod = 2

@dataclass
class BaseNetworkChaosConfig:
    supported_execution = ["serial", "parallel"]
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
            errors.append(f"execution cannot be None, supported values are: {','.join(self.supported_execution)}")
        if self.execution not in self.supported_execution:
            errors.append(f"{self.execution} is not in supported execution mod: {','.join(self.supported_execution)}")
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
