import abc
import logging
import queue
from typing import Tuple

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.network_chaos_ng.models import (
    BaseNetworkChaosConfig,
    NetworkChaosScenarioType,
)


class AbstractNetworkChaosModule(abc.ABC):
    """
    The abstract class that needs to be implemented by each Network Chaos Scenario
    """

    kubecli: KrknTelemetryOpenshift
    base_network_config: BaseNetworkChaosConfig

    @abc.abstractmethod
    def run(self, target: str, error_queue: queue.Queue = None):
        """
        the entrypoint method for the Network Chaos Scenario
        :param target: The resource name that will be targeted by the scenario (Node Name, Pod Name etc.)
        :param error_queue: A queue that will be used by the plugin to push the errors raised during the execution of parallel modules
        """
        pass

    @abc.abstractmethod
    def get_config(self) -> Tuple[NetworkChaosScenarioType, BaseNetworkChaosConfig]:
        """
        returns the common subset of settings shared by all the scenarios `BaseNetworkChaosConfig` and the type of Network
        Chaos Scenario that is running (Pod Scenario or Node Scenario)
        """
        pass

    def get_targets(self) -> list[str]:
        """
        checks and returns the targets based on the common scenario configuration
        """

        pass

    def get_node_targets(self, config: BaseNetworkChaosConfig):
        if self.base_network_config.label_selector:
            return self.kubecli.get_lib_kubernetes().list_nodes(
                self.base_network_config.label_selector
            )
        else:
            if not config.target:
                raise Exception(
                    "neither node selector nor node_name (target) specified, aborting."
                )
            node_info = self.kubecli.get_lib_kubernetes().list_nodes()
            if config.target not in node_info:
                raise Exception(f"node {config.target} not found, aborting")

            return [config.target]

    def get_pod_targets(self, config: BaseNetworkChaosConfig):
        if not config.namespace:
            raise Exception("namespace not specified, aborting")
        if self.base_network_config.label_selector:
            return self.kubecli.get_lib_kubernetes().list_pods(
                config.namespace, config.label_selector
            )
        else:
            if not config.target:
                raise Exception(
                    "neither node selector nor node_name (target) specified, aborting."
                )
            if not self.kubecli.get_lib_kubernetes().check_if_pod_exists(
                config.target, config.namespace
            ):
                raise Exception(
                    f"pod {config.target} not found in namespace {config.namespace}"
                )
            return [config.target]

    def __init__(
        self,
        base_network_config: BaseNetworkChaosConfig,
        kubecli: KrknTelemetryOpenshift,
    ):
        self.kubecli = kubecli
        self.base_network_config = base_network_config
