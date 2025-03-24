import abc
import logging
import queue

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.network_chaos_ng.models import BaseNetworkChaosConfig, NetworkChaosScenarioType


class AbstractNetworkChaosModule(abc.ABC):
    @abc.abstractmethod
    def run(self, target: str, kubecli: KrknTelemetryOpenshift, error_queue: queue.Queue = None):
        pass

    @abc.abstractmethod
    def get_config(self) -> (NetworkChaosScenarioType, BaseNetworkChaosConfig):
        pass


    def log_info(self, message: str, parallel: bool = False, node_name: str = ""):
        if parallel:
            logging.info(f"[{node_name}]: {message}")
        else:
            logging.info(message)

    def log_warning(self, message: str, parallel: bool = False, node_name: str = ""):
        if parallel:
            logging.warning(f"[{node_name}]: {message}")
        else:
            logging.warning(message)


    def log_error(self, message: str, parallel: bool = False, node_name: str = ""):
        if parallel:
            logging.error(f"[{node_name}]: {message}")
        else:
            logging.error(message)