import abc
import logging
import queue

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.network_chaos_ng.models import BaseNetworkChaosConfig, NetworkChaosScenarioType


class AbstractNetworkChaosModule(abc.ABC):
    """
    The abstract class that needs to be implemented by each Network Chaos Scenario
    """
    @abc.abstractmethod
    def run(self, target: str, kubecli: KrknTelemetryOpenshift, error_queue: queue.Queue = None):
        """
        the entrypoint method for the Network Chaos Scenario
        :param target: The resource name that will be targeted by the scenario (Node Name, Pod Name etc.)
        :param kubecli: The `KrknTelemetryOpenshift` needed by the scenario to access to the krkn-lib methods
        :param error_queue: A queue that will be used by the plugin to push the errors raised during the execution of parallel modules
        """
        pass

    @abc.abstractmethod
    def get_config(self) -> (NetworkChaosScenarioType, BaseNetworkChaosConfig):
        """
        returns the common subset of settings shared by all the scenarios `BaseNetworkChaosConfig` and the type of Network
        Chaos Scenario that is running (Pod Scenario or Node Scenario)
        """
        pass


    def log_info(self, message: str, parallel: bool = False, node_name: str = ""):
        """
        log helper method for INFO severity to be used in the scenarios
        """
        if parallel:
            logging.info(f"[{node_name}]: {message}")
        else:
            logging.info(message)

    def log_warning(self, message: str, parallel: bool = False, node_name: str = ""):
        """
        log helper method for WARNING severity to be used in the scenarios
        """
        if parallel:
            logging.warning(f"[{node_name}]: {message}")
        else:
            logging.warning(message)


    def log_error(self, message: str, parallel: bool = False, node_name: str = ""):
        """
        log helper method for ERROR severity to be used in the scenarios
        """
        if parallel:
            logging.error(f"[{node_name}]: {message}")
        else:
            logging.error(message)