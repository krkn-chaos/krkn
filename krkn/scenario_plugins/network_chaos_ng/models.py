import re
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar, Optional


class NetworkChaosScenarioType(Enum):
    Node = 1
    Pod = 2


@dataclass
class BaseNetworkChaosConfig:
    id: str
    image: str
    wait_duration: int
    test_duration: int
    label_selector: str
    service_account: str
    taints: list[str]
    namespace: str
    instance_count: int
    execution: str
    supported_execution = ["serial", "parallel"]
    interfaces: list[str]
    target: str
    ingress: bool
    egress: bool

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
    ports: list[int]
    protocols: list[str]

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
class NetworkChaosConfig(BaseNetworkChaosConfig):
    latency: Optional[str] = None
    loss: Optional[str] = None
    bandwidth: Optional[str] = None
    force: Optional[bool] = None

    def validate(self) -> list[str]:
        errors = super().validate()
        latency_regex = re.compile(r"^(\d+)(us|ms|s)$")
        bandwidth_regex = re.compile(r"^(\d+)(bit|kbit|mbit|gbit|tbit)$")
        if self.latency:
            if not (latency_regex.match(self.latency)):
                errors.append(
                    "latency must be a number followed by `us` (microseconds) or `ms` (milliseconds), or `s` (seconds)"
                )
        if self.bandwidth:
            if not (bandwidth_regex.match(self.bandwidth)):
                errors.append(
                    "bandwidth must be a number followed by `bit` `kbit` or `mbit` or `tbit`"
                )
        if self.loss:
            if "%" in self.loss or not self.loss.isdigit():
                errors.append("loss must be a number followed without the `%` symbol")
        return errors
