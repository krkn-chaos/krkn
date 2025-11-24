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
    service_account: str
    instance_count: int
    execution: str
    namespace: str
    taints: list[str]

    def validate(self) -> list[str]:
        errors = []
        if self.execution is None:
            errors.append(
                f"execution cannot be None, supported values are: {','.join(self.supported_execution)}"
            )
        if self.execution not in self.supported_execution:
            errors.append(
                f"{self.execution} is not in supported execution mod: {','.join(self.supported_execution)}"
            )
        if self.id == "node_network_filter" and self.label_selector is None:
            errors.append("label_selector cannot be None")
        if not isinstance(self.wait_duration, int):
            errors.append("wait_duration must be an int")
        if not isinstance(self.test_duration, int):
            errors.append("test_duration must be an int")
        return errors


@dataclass
class NetworkFilterConfig(BaseNetworkChaosConfig):
    ingress: bool
    egress: bool
    interfaces: list[str]
    target: str | list[str] | None
    ports: list[int]
    image: str
    protocols: list[str]

    def validate(self) -> list[str]:
        errors = super().validate()
        # here further validations
        allowed_protocols = {"tcp", "udp"}
        if not set(self.protocols).issubset(allowed_protocols):
            errors.append(
                f"{self.protocols} contains not allowed protocols only tcp and udp is allowed"
            )
        if self.label_selector in ("", None):
            if isinstance(self.target, list) and len(self.target) == 0:
                errors.append("target list cannot be empty")
            if self.target is None or (
                isinstance(self.target, str) and len(self.target.strip()) == 0
            ):
                errors.append("target cannot be None or empty string")
        if self.target is not None and not isinstance(self.target, (str, list)):
            errors.append("target must be a string, list, or wildcard identifier")
        return errors
