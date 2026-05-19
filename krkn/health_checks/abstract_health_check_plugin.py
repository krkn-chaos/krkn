import logging
import queue
import threading
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
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """
        Signals the plugin to stop its health check loop. Unblocks any join()
        waiting on a worker thread when the main loop exits early (e.g. on a
        STOP signal, critical alert, or daemon mode with iterations=inf).

        :return: None
        """
        self._stop_event.set()

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

    @abstractmethod
    def get_config_key(self) -> str:
        """
        Returns the top-level key this plugin reads from config.yaml. The factory uses
        this to map each config section to its plugin automatically, so that new plugins
        can define their own config section without modifying run_kraken.py.

        The key must be unique across all plugins.

        Example: an HTTP health check plugin might return ``"health_checks"``, meaning
        it will be configured under ``health_checks:`` in config.yaml.

        :return: the top-level config.yaml key for this plugin
        """
        pass

    def manages_own_threads(self) -> bool:
        """
        Indicates whether this plugin spawns and manages its own worker threads internally.

        Plugins that return ``True`` have ``run_health_check()`` called directly (it returns
        immediately after spawning internal threads) and must expose a ``thread_join()`` method
        for the factory to wait on completion.

        Plugins that return ``False`` (the default) are wrapped in an external thread by the
        factory's ``start_all()`` method.

        Override this method and return ``True`` only if your plugin manages its own threads.

        :return: False by default; True for self-threading plugins like VirtHealthCheckPlugin
        """
        return False

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
