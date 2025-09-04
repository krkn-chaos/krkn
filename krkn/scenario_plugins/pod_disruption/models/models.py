from dataclasses import dataclass

@dataclass
class InputParams:
    def __init__(self, config: dict[str,any] = None):
        if config:
            self.kill = config["kill"] if "kill" in config else 1
            self.timeout = config["timeout"] if "timeout" in config else 120
            self.duration = config["duration"] if "duration" in config else 10
            self.krkn_pod_recovery_time = config["krkn_pod_recovery_time"] if "krkn_pod_recovery_time" in config else 120
            self.label_selector = config["label_selector"] if "label_selector" in config else ""
            self.namespace_pattern = config["namespace_pattern"] if "namespace_pattern" in config else ""
            self.name_pattern = config["name_pattern"] if "name_pattern" in config else ""
            self.node_label_selector = config["node_label_selector"] if "node_label_selector" in config else ""
            self.node_names = config["node_names"] if "node_names" in config else []

    namespace_pattern: str
    krkn_pod_recovery_time: int
    timeout: int
    duration: int
    kill: int
    label_selector: str
    name_pattern: str
    node_label_selector: str
    node_names: list