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
import subprocess

from krkn.scenario_plugins.triggers.abstract_trigger import AbstractTrigger

COMMAND_TIMEOUT_SECONDS = 30


class CommandTrigger(AbstractTrigger):
    """Trigger that runs a shell command and checks its exit code."""

    def __init__(self, config: dict):
        self._cmd = config.get("cmd") or config.get("inline")
        if not self._cmd:
            raise ValueError(
                "command trigger requires either 'cmd' or 'inline' field"
            )
        try:
            self._expected_rc = int(config.get("expected_rc", 0))
        except (TypeError, ValueError):
            raise ValueError(
                f"expected_rc must be an integer, got {config.get('expected_rc')!r}"
            )
        if not 0 <= self._expected_rc <= 255:
            raise ValueError(
                f"expected_rc must be between 0 and 255, got {self._expected_rc}"
            )
        self._last_result: bool | None = None

    def evaluate(self) -> bool:
        try:
            result = subprocess.run(
                self._cmd,
                shell=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
                capture_output=True,
                text=True,
            )
            met = result.returncode == self._expected_rc
            logging.debug(
                f"command trigger: rc={result.returncode} "
                f"expected={self._expected_rc} cmd='{self._cmd}'"
            )
            if result.stderr:
                logging.debug(
                    f"command trigger stderr: {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            logging.warning(
                f"command trigger timed out after {COMMAND_TIMEOUT_SECONDS}s: "
                f"{self._cmd}"
            )
            met = False
        except FileNotFoundError:
            logging.error(
                f"command trigger binary not found: {self._cmd}"
            )
            met = False
        except Exception as e:
            logging.error(
                f"command trigger unexpected error: {e}: {self._cmd}"
            )
            met = False

        # Log only on state change
        if met != self._last_result:
            if met:
                logging.info(
                    f"trigger condition satisfied: {self._cmd}"
                )
            else:
                logging.info(
                    f"trigger condition not satisfied: {self._cmd}"
                )
        self._last_result = met
        return met

    def describe(self) -> str:
        return (
            f"command trigger: '{self._cmd}' "
            f"(expected rc={self._expected_rc})"
        )
