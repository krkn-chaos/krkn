import queue
import time

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.network_chaos_ng.models import BaseNetworkChaosConfig, NetworkFilterConfig, \
    NetworkChaosScenarioType
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import AbstractNetworkChaosModule


class NodeNetworkFilterModule(AbstractNetworkChaosModule):
    def run(self, target: str, kubecli: KrknTelemetryOpenshift, error_queue: queue.Queue = None):
        parallel = False
        if error_queue:
            parallel = True

        for i in range(5):
            self.log_info("node network filter module", parallel, target)
            time.sleep(2)
        pass

    config: NetworkFilterConfig

    def __init__(self, config: NetworkFilterConfig):
        self.config = config

    def get_config(self) -> (NetworkChaosScenarioType, BaseNetworkChaosConfig):
        return NetworkChaosScenarioType.Node, self.config
