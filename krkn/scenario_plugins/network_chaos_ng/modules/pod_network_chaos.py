import queue
from typing import Tuple

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosScenarioType,
    BaseNetworkChaosConfig,
    NetworkChaosConfig,
)
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)


class PodNetworkChaos(AbstractNetworkChaosModule):

    def __init__(self, config: NetworkChaosConfig, kubecli: KrknTelemetryOpenshift):
        super().__init__(config, kubecli)
        self.config = config

    def run(self, target: str, error_queue: queue.Queue = None):
        pass

    def get_config(self) -> Tuple[NetworkChaosScenarioType, BaseNetworkChaosConfig]:
        return NetworkChaosScenarioType.Pod, self.config
