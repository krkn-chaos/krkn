from dataclasses import dataclass

@dataclass
class InputParams:
    namespace: str
    direction: str
    ingress_ports: int
    egress_ports: int
    kubeconfig_path: str
    pod_name: str
    label_selector: str
    kraken_config: str
    test_duration: int
    wait_duration: int
    instance_count: int


@dataclass
class EgressParams:
    namespace: str
    network_params: dict[str,str]
    kubeconfig_path: str
    pod_name: str
    label_selector: str
    kraken_config: dict[str,any]
    test_duration: int
    wait_duration: int
    instance_count: int
    execution_type: str


@dataclass
class IngressParams:
    namespace: str
    network_params: dict[str, str]
    kubeconfig_path: str
    pod_name: str
    label_selector: str
    kraken_config: dict[str, any]
    test_duration: int
    wait_duration: int
    instance_count: int
    execution_type: str
