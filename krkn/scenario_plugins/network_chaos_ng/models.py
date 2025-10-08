from dataclasses import dataclass
from enum import Enum
from typing import Optional


class NetworkChaosScenarioType(Enum):
    Node = 1
    Pod = 2


@dataclass
class BaseNetworkChaosConfig:
    supported_execution = ["serial", "parallel"]
    taints: list[str]
    id: str
    wait_duration: int
    test_duration: int
    label_selector: str
    instance_count: int
    execution: str
    namespace: str
    target: str
    service_account: str
    image: str

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
    ports: list[int]
    protocols: list[str]
    force: bool

    def validate(self) -> list[str]:
        errors = super().validate()
        # here further validations
        allowed_protocols = {"tcp", "udp"}
        if not set(self.protocols).issubset(allowed_protocols):
            errors.append(
                f"{self.protocols} contains not allowed protocols only tcp and udp is allowed"
            )
        return errors


@dataclass
class PodNetworkShaping(BaseNetworkChaosConfig):
    network_shaping_execution: str
    latency: str
    loss: str
    bandwidth: str

    def __iter__(self):
        if self.network_shaping_execution:
            yield "network_shaping_execution"
        if self.latency:
            yield "latency"
        if self.loss:
            yield "loss"
        if self.bandwidth:
            yield "bandwidth"
