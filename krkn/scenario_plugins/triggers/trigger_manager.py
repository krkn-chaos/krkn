# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import time

from krkn.scenario_plugins.triggers.abstract_trigger import AbstractTrigger
from krkn.scenario_plugins.triggers.command_trigger import CommandTrigger

VALID_MODES = {"all_of", "any_of"}
VALID_ON_TIMEOUT = {"skip", "fail", "run_anyway"}

DEFAULT_TIMEOUT = 300
DEFAULT_INTERVAL = 5
DEFAULT_MODE = "all_of"
DEFAULT_ON_TIMEOUT = "skip"


class TriggerManager:
    """Orchestrates polling across multiple triggers."""

    def __init__(self, trigger_config: dict):
        conditions = trigger_config.get("conditions")
        if not conditions:
            raise ValueError(
                "trigger config must include a non-empty 'conditions' list"
            )
        if not isinstance(conditions, list):
            raise ValueError(
                "trigger 'conditions' must be a list, "
                f"got {type(conditions).__name__}"
            )

        self._mode = trigger_config.get("mode", DEFAULT_MODE)
        if self._mode not in VALID_MODES:
            raise ValueError(
                f"invalid trigger mode '{self._mode}', "
                f"must be one of: {', '.join(sorted(VALID_MODES))}"
            )

        self._on_timeout = trigger_config.get("on_timeout", DEFAULT_ON_TIMEOUT)
        if self._on_timeout not in VALID_ON_TIMEOUT:
            raise ValueError(
                f"invalid on_timeout '{self._on_timeout}', "
                f"must be one of: {', '.join(sorted(VALID_ON_TIMEOUT))}"
            )

        self._timeout = trigger_config.get("timeout", DEFAULT_TIMEOUT)
        self._interval = trigger_config.get("interval", DEFAULT_INTERVAL)

        try:
            self._timeout = float(self._timeout)
            self._interval = float(self._interval)
        except (TypeError, ValueError):
            raise ValueError(
                f"timeout and interval must be numeric, "
                f"got timeout={trigger_config.get('timeout')!r}, "
                f"interval={trigger_config.get('interval')!r}"
            )

        if self._timeout <= 0:
            raise ValueError(
                f"timeout must be positive, got {self._timeout}"
            )
        if self._interval <= 0:
            raise ValueError(
                f"interval must be positive, got {self._interval}"
            )

        self._triggers: list[AbstractTrigger] = []
        for condition in trigger_config["conditions"]:
            self._triggers.append(self._build_trigger(condition))

        # Track per-trigger satisfaction state for get_status
        self._trigger_states: list[bool | None] = [None] * len(self._triggers)

    @property
    def on_timeout(self) -> str:
        return self._on_timeout

    @staticmethod
    def _build_trigger(condition_config: dict) -> AbstractTrigger:
        """Factory method that creates a trigger from a condition config."""
        trigger_type = condition_config.get("type")
        if not trigger_type:
            raise ValueError("each condition must have a 'type' field")

        if trigger_type == "command":
            return CommandTrigger(condition_config)

        raise ValueError(f"unknown trigger type: '{trigger_type}'")

    def wait_for_triggers(self) -> bool:
        """Polls triggers until conditions are met or timeout expires.

        Returns True if conditions were met, False if timed out.
        """
        logging.info(
            f"waiting for triggers: mode={self._mode}, "
            f"timeout={self._timeout}s, interval={self._interval}s, "
            f"on_timeout={self._on_timeout}"
        )
        deadline = time.monotonic() + self._timeout

        while time.monotonic() < deadline:
            results = []
            for i, trigger in enumerate(self._triggers):
                result = trigger.evaluate()
                self._trigger_states[i] = result
                results.append(result)

            logging.debug(
                f"trigger poll: {[r for r in results]}"
            )

            if self._mode == "all_of" and all(results):
                logging.info("all trigger conditions satisfied")
                return True
            elif self._mode == "any_of" and any(results):
                logging.info("at least one trigger condition satisfied")
                return True

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(self._interval, remaining))

        logging.warning(
            f"triggers timed out after {self._timeout}s "
            f"(on_timeout={self._on_timeout})"
        )
        return False

    def describe(self) -> str:
        """Human-readable summary of all triggers."""
        parts = [
            f"TriggerManager(mode={self._mode}, "
            f"timeout={self._timeout}s, interval={self._interval}s, "
            f"on_timeout={self._on_timeout})",
        ]
        for i, trigger in enumerate(self._triggers):
            parts.append(f"  [{i}] {trigger.describe()}")
        return "\n".join(parts)

    def get_status(self) -> dict:
        """Returns current state of each trigger for the signal server."""
        return {
            "mode": self._mode,
            "timeout": self._timeout,
            "interval": self._interval,
            "on_timeout": self._on_timeout,
            "triggers": [
                {
                    "description": trigger.describe(),
                    "satisfied": self._trigger_states[i],
                }
                for i, trigger in enumerate(self._triggers)
            ],
        }
