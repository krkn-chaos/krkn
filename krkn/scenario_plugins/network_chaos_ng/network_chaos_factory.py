from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.network_chaos_ng.models import NetworkFilterConfig, PodNetworkShaping
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.modules.node_network_filter import (
    NodeNetworkFilterModule,
)
from krkn.scenario_plugins.network_chaos_ng.modules.pod_egress_shaping import PodEgressShapingModule
from krkn.scenario_plugins.network_chaos_ng.modules.pod_ingress_shaping import PodIngressShapingModule
from krkn.scenario_plugins.network_chaos_ng.modules.pod_network_filter import (
    PodNetworkFilterModule,
)



class NetworkChaosFactory:

    @staticmethod
    def get_instance(
        config: dict[str, str], kubecli: KrknTelemetryOpenshift
    ) -> AbstractNetworkChaosModule:
        if config["id"] is None:
            raise Exception("network chaos id cannot be None")

        if config["id"] == "node_network_filter":
            config = NetworkFilterConfig(**config)
            errors = config.validate()
            if len(errors) > 0:
                raise Exception(f"config validation errors: [{';'.join(errors)}]")
            return NodeNetworkFilterModule(config, kubecli)
        elif config["id"] == "pod_network_filter":
            config = NetworkFilterConfig(**config)
            errors = config.validate()
            if len(errors) > 0:
                raise Exception(f"config validation errors: [{';'.join(errors)}]")
            return PodNetworkFilterModule(config, kubecli)

        elif config["id"] == "pod_egress_shaping":
            config = PodNetworkShaping(**config)
            errors = config.validate()
            if len(errors) > 0:
                raise Exception(f"config validation errors: [{';'.join(errors)}]")
            return PodEgressShapingModule(config, kubecli)

        elif config["id"] == "pod_ingress_shaping":
            config = PodNetworkShaping(**config)
            errors = config.validate()
            if len(errors) > 0:
                raise Exception(f"config validation errors: [{';'.join(errors)}]")
            return PodIngressShapingModule(config, kubecli)
        else:
            raise Exception(f"{config['id']} Network Chaos NG scenario type not supported (yet)!")
