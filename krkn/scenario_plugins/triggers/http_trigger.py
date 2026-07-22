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

import requests

from krkn.scenario_plugins.triggers.abstract_trigger import AbstractTrigger

HTTP_REQUEST_TIMEOUT_SECONDS = 30

VALID_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}


class HttpTrigger(AbstractTrigger):
    """Trigger that polls an HTTP endpoint and checks its response status."""

    def __init__(self, config: dict):
        self._url = config.get("url")
        if not self._url:
            raise ValueError("http trigger requires a 'url' field")

        method = config.get("method", "GET")
        self._method = str(method).upper()
        if self._method not in VALID_METHODS:
            raise ValueError(
                f"http trigger method must be one of "
                f"{', '.join(sorted(VALID_METHODS))}, got {self._method!r}"
            )

        try:
            self._expected_status = int(config.get("expected_status", 200))
        except (TypeError, ValueError):
            raise ValueError(
                f"expected_status must be an integer, "
                f"got {config.get('expected_status')!r}"
            )
        if not 100 <= self._expected_status <= 599:
            raise ValueError(
                f"expected_status must be a valid HTTP status code (100-599), "
                f"got {self._expected_status}"
            )

        self._headers: dict = dict(config.get("headers") or {})
        bearer_token = config.get("bearer_token")
        if bearer_token:
            self._headers["Authorization"] = f"Bearer {bearer_token}"

        self._body_contains: str | None = config.get("body_contains")
        self._last_result: bool | None = None

    def evaluate(self) -> bool:
        try:
            with requests.Session() as session:
                response = session.request(
                    self._method,
                    self._url,
                    headers=self._headers,
                    timeout=HTTP_REQUEST_TIMEOUT_SECONDS,
                )
            met = response.status_code == self._expected_status
            logging.debug(
                f"http trigger: status={response.status_code} "
                f"expected={self._expected_status} url='{self._url}'"
            )
            if met and self._body_contains is not None:
                met = self._body_contains in response.text
                if not met:
                    logging.debug(
                        f"http trigger: body_contains={self._body_contains!r} "
                        f"not found in response"
                    )
        except requests.exceptions.Timeout:
            logging.warning(
                f"http trigger timed out after {HTTP_REQUEST_TIMEOUT_SECONDS}s: "
                f"{self._url}"
            )
            met = False
        except requests.exceptions.ConnectionError:
            logging.warning(
                f"http trigger connection error: {self._url}"
            )
            met = False
        except requests.exceptions.RequestException as e:
            logging.error(
                f"http trigger request error: {e}: {self._url}"
            )
            met = False
        except Exception as e:
            logging.error(
                f"http trigger unexpected error: {e}: {self._url}"
            )
            met = False

        # Log only on state change
        if met != self._last_result:
            if met:
                logging.info(
                    f"trigger condition satisfied: {self.describe()}"
                )
            else:
                logging.info(
                    f"trigger condition not satisfied: {self.describe()}"
                )
        self._last_result = met
        return met

    def describe(self) -> str:
        return (
            f"http trigger: {self._method} {self._url} "
            f"expect={self._expected_status}"
        )
