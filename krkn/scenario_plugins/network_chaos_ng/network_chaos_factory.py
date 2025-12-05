from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkFilterConfig,
    NetworkChaosConfig,
)
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.modules.node_network_filter import (
    NodeNetworkFilterModule,
)
from krkn.scenario_plugins.network_chaos_ng.modules.pod_network_chaos import (
    PodNetworkChaos,
)
from krkn.scenario_plugins.network_chaos_ng.modules.pod_network_filter import (
    PodNetworkFilterModule,
)

supported_modules = ["node_network_filter", "pod_network_filter", "pod_network_chaos"]


class NetworkChaosFactory:

    @staticmethod
    def get_instance(
        config: dict[str, str], kubecli: KrknTelemetryOpenshift
    ) -> AbstractNetworkChaosModule:
        if config["id"] is None:
            raise Exception("network chaos id cannot be None")
        if config["id"] not in supported_modules:
            raise Exception(f"{config['id']} is not a supported network chaos module")

        if config["id"] == "node_network_filter":
            scenario_config = NetworkFilterConfig(**config)
            errors = scenario_config.validate()
            if len(errors) > 0:
                raise Exception(f"config validation errors: [{';'.join(errors)}]")
            return NodeNetworkFilterModule(scenario_config, kubecli)
        if config["id"] == "pod_network_filter":
            scenario_config = NetworkFilterConfig(**config)
            errors = scenario_config.validate()
            if len(errors) > 0:
                raise Exception(f"config validation errors: [{';'.join(errors)}]")
            return PodNetworkFilterModule(scenario_config, kubecli)
        if config["id"] == "pod_network_chaos":
            scenario_config = NetworkChaosConfig(**config)
            errors = scenario_config.validate()
            if len(errors) > 0:
                raise Exception(f"config validation errors: [{';'.join(errors)}]")
            return PodNetworkChaos(scenario_config, kubecli)
        else:
            raise Exception(f"invalid network chaos id {config['id']}")
