import logging
import queue
from abc import ABC, abstractmethod
from typing import Any


class AbstractHealthCheckPlugin(ABC):
    """
    Abstract base class for health check plugins in krkn.

    Health check plugins are designed to monitor the health of applications,
    services, or infrastructure components during chaos engineering experiments.
    Each plugin implements specific health check logic and runs in a separate
    thread to continuously monitor health status.
    """

    def __init__(self, health_check_type: str = "placeholder_health_check_type"):
        """
        Initializes the AbstractHealthCheckPlugin with the health check type.

        :param health_check_type: the health check type defined in the config.yaml
        """
        self.health_check_type = health_check_type
        self.ret_value = 0  # 0 = success, non-zero = failure

    @abstractmethod
    def run_health_check(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue,
    ) -> None:
        """
        This method serves as the entry point for a HealthCheckPlugin. To make the plugin loadable,
        the AbstractHealthCheckPlugin class must be extended, and this method must be implemented.

        This method is typically run in a separate thread and should continuously monitor
        health status until the specified number of iterations is complete.

        :param config: the health check configuration dictionary from config.yaml
        :param telemetry_queue: a queue to put telemetry data for collection
        :return: None (updates self.ret_value to indicate success/failure)
        """
        pass

    @abstractmethod
    def get_health_check_types(self) -> list[str]:
        """
        Indicates the health check types specified in the `config.yaml`. For the plugin to be properly
        loaded, recognized and executed, it must be implemented and must return the matching `health_check_type` strings.
        One plugin can be mapped to one or many different strings, which must be unique across other plugins,
        otherwise an exception will be thrown.

        :return: the corresponding health_check_type as a list of strings
        """
        pass

    @abstractmethod
    def increment_iterations(self) -> None:
        """
        Increments the current iteration counter. This method is called by the main run loop
        after each chaos scenario iteration to keep the health check synchronized with
        the chaos run progress.

        :return: None
        """
        pass

    def get_return_value(self) -> int:
        """
        Returns the current return value indicating success or failure.

        :return: 0 for success, non-zero for failure
        """
        return self.ret_value

    def set_return_value(self, value: int) -> None:
        """
        Sets the return value to indicate success or failure.

        :param value: 0 for success, non-zero for failure
        :return: None
        """
        self.ret_value = value
