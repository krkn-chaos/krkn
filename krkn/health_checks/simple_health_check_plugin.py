"""
Simple Health Check Plugin (for testing the factory)

This is a minimal health check plugin for testing the factory system.
It doesn't require any external dependencies.
"""

import logging
import queue
from typing import Any

from krkn.health_checks.abstract_health_check_plugin import AbstractHealthCheckPlugin


class SimpleHealthCheckPlugin(AbstractHealthCheckPlugin):
    """
    A simple health check plugin for testing purposes.
    """

    def __init__(
        self,
        health_check_type: str = "simple_health_check",
        iterations: int = 1,
        **kwargs
    ):
        super().__init__(health_check_type)
        self.iterations = iterations
        self.current_iterations = 0

    def get_health_check_types(self) -> list[str]:
        return ["simple_health_check", "test_health_check"]

    def increment_iterations(self) -> None:
        self.current_iterations += 1

    def run_health_check(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue,
    ) -> None:
        logging.info("Running simple health check")
        telemetry_queue.put({"status": "healthy"})
