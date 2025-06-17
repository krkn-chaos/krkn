from dataclasses import dataclass

class BaseInput:
    def __init__(self, config: dict[str,any] = None):
        if config:
            self.namespace = config["namespace"] if "namespace" in config else ""
            self.instance_count = config["instance_count"] if "instance_count" in config  else 0
            self.wait_duration = config["wait_duration"] if "wait_duration" in config  else 0
            self.test_duration = config["test_duration"] if "test_duration" in config else 0
            self.execution_type = config["execution_type"] if "execution_type" in config  else ""
            self.label_selector = config["label_selector"] if "label_selector" in config  else ""
            self.pod_name = config["pod_name"] if "pod_name" in config else ""

    namespace: str
    instance_count: int
    wait_duration: int
    test_duration: int
    instance_count: int
    execution_type: str
    label_selector: str
    network_params: dict[str, str]
    pod_name: str



@dataclass
class InputParams(BaseInput):
    def __init__(self, config: dict[str, any] = None):
        if config:
            super().__init__(config)
            self.direction = config["direction"] if "direction" in config  else []
            self.ingress_ports = config["ingress_ports"] if "ingress_ports" in config and isinstance(config["ingress_ports"], list) else []
            self.egress_ports = config["egress_ports"] if "egress_ports" in config and isinstance(config["egress_ports"], list)  else []

    direction: list[str]
    ingress_ports: list[int]
    egress_ports: list[int]



@dataclass
class IngressEgressParams(BaseInput):
    def __init__(self, config: dict[str, any] = None):
        if config:
            super().__init__(config)
            if config and config["network_params"]:
                self.network_params = {
                    "latency": config["network_params"]["latency"] if config["network_params"]["latency"] else "",
                    "loss" : config["network_params"]["loss"] if config["network_params"]["loss"] else "",
                    "bandwidth": config["network_params"]["bandwidth"] if config["network_params"]["bandwidth"] else ""
                }
            else:
                self.network_params: dict[str, any] = {}



