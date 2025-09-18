import abc
import logging
import queue

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
    def get_config(self) -> (NetworkChaosScenarioType, BaseNetworkChaosConfig):
        """
        returns the common subset of settings shared by all the scenarios `BaseNetworkChaosConfig` and the type of Network
        Chaos Scenario that is running (Pod Scenario or Node Scenario)
        """
        pass

    @abc.abstractmethod
    def get_targets(self) -> list[str]:
        """
        checks and returns the targets based on the common scenario configuration
        """

        pass

    def __init__(
        self,
        base_network_config: BaseNetworkChaosConfig,
        kubecli: KrknTelemetryOpenshift,
    ):
        self.kubecli = kubecli
        self.base_network_config = base_network_config


    def get_pod_targets(self) -> list[str]:
        if not self.base_network_config.namespace:
            raise Exception("namespace not specified, aborting")
        if self.base_network_config.label_selector:
            return self.kubecli.get_lib_kubernetes().list_pods(
                self.base_network_config.namespace, self.base_network_config.label_selector
            )
        else:
            if not self.base_network_config.target:
                raise Exception(
                    "neither pod selector nor pod name (target) specified, aborting."
                )
            if not self.kubecli.get_lib_kubernetes().check_if_pod_exists(
                self.base_network_config.target, self.base_network_config.namespace
            ):
                raise Exception(
                    f"pod {self.base_network_config.target} not found in namespace {self.base_network_config.namespace}"
                )

            return [self.base_network_config.target]

    def get_node_targets(self) -> list[str]:
        if self.base_network_config.label_selector:
            return self.kubecli.get_lib_kubernetes().list_nodes(
                self.base_network_config.label_selector
            )
        else:
            if not self.base_network_config.target:
                raise Exception(
                    "neither node selector nor node_name (target) specified, aborting."
                )
            node_info = self.kubecli.get_lib_kubernetes().list_nodes()
            if self.base_network_config.target not in node_info:
                raise Exception(f"node {self.base_network_config.target} not found, aborting")

            return [self.base_network_config.target]

