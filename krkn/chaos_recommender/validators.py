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
import re

# Kubernetes namespace: lowercase alphanumeric and hyphens, 1-63 chars
_NAMESPACE_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?$")
# Kubernetes pod name: lowercase alphanumeric, hyphens, and dots, 1-253 chars
_POD_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9\-\.]{0,251}[a-z0-9])?$")
# Prometheus duration: digits followed by a time unit
_PROM_DURATION_RE = re.compile(r"^\d+[smhdwy]$")


def validate_namespace(namespace):
    if not _NAMESPACE_RE.match(namespace):
        raise ValueError(
            f"Invalid namespace name: {namespace!r}. "
            "Must match Kubernetes naming rules (lowercase alphanumeric and hyphens, 1-63 chars)."
        )


def validate_scrape_duration(duration):
    if not _PROM_DURATION_RE.match(duration):
        raise ValueError(
            f"Invalid scrape duration: {duration!r}. "
            "Must be a Prometheus duration (e.g. '5m', '1h', '30s')."
        )


def validate_pod_name(pod_name):
    if not _POD_NAME_RE.match(pod_name):
        raise ValueError(
            f"Invalid pod name: {pod_name!r}. "
            "Must match Kubernetes naming rules (lowercase alphanumeric, hyphens, and dots, 1-253 chars)."
        )
