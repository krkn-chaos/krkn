# Copyright 2026 The Krkn Authors
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

"""
Parsing and validation utilities for the storage throttle scenario plugin.

Kubernetes-style binary byte suffixes (powers of 1024):
  Ki = Kibibyte = 1024 bytes
  Mi = Mebibyte = 1024^2 = 1,048,576 bytes
  Gi = Gibibyte = 1024^3 = 1,073,741,824 bytes

SI decimal suffixes (powers of 1000):
  K = Kilobyte  = 1,000 bytes
  M = Megabyte  = 1,000,000 bytes
  G = Gigabyte  = 1,000,000,000 bytes

Duration suffixes:
  s = seconds
  m = minutes (x60)
  h = hours   (x3600)
"""

import re

_BYTE_UNITS = {
    "Ki": 1024,
    "Mi": 1024 ** 2,
    "Gi": 1024 ** 3,
    "K": 1000,
    "M": 1000 ** 2,
    "G": 1000 ** 3,
}

_DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
}

_BYTE_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(Ki|Mi|Gi|K|M|G)?\s*$"
)
_DURATION_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(s|m|h)?\s*$"
)

_SAFE_PATH_RE = re.compile(r"^/[a-zA-Z0-9._/\-]+$")
_CGROUP_PATH_RE = re.compile(r"^/[a-zA-Z0-9._/\-]+$")
_MAJ_MIN_RE = re.compile(r"^\d+:\d+$")
_CONTAINER_ID_RE = re.compile(r"^[a-f0-9]+$")


def validate_mount_path(path: str) -> bool:
    """Validate mount path contains only safe characters and no traversal."""
    if ".." in path:
        return False
    return bool(_SAFE_PATH_RE.match(path))


def validate_cgroup_path(path: str) -> bool:
    """Validate cgroup path contains only safe characters and no traversal."""
    if ".." in path:
        return False
    return bool(_CGROUP_PATH_RE.match(path))


def validate_maj_min(value: str) -> bool:
    """Validate device major:minor format (e.g. '8:16')."""
    return bool(_MAJ_MIN_RE.match(value))


def validate_container_id(value: str) -> bool:
    """Validate container ID is a hex string (CRI-O/containerd format)."""
    return bool(value) and bool(_CONTAINER_ID_RE.match(value))


def parse_byte_value(value) -> int:
    """Parse a byte value that may use Kubernetes-style unit suffixes.

    Accepts:
      - Plain integers: 1048576 -> 1048576
      - String with suffix: "1Mi" -> 1048576, "512Ki" -> 524288, "5Gi" -> 5368709120
      - String without suffix: "1048576" -> 1048576

    Supported suffixes (binary, Kubernetes-style):
      Ki = 1024, Mi = 1024^2 (1,048,576), Gi = 1024^3 (1,073,741,824)
    Supported suffixes (decimal, SI):
      K = 1000, M = 1000^2, G = 1000^3
    """
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        raise ValueError("byte value must be an int or string, got: %r" % value)

    match = _BYTE_PATTERN.match(value)
    if not match:
        raise ValueError(
            "invalid byte value '%s'. Use a number optionally followed by "
            "Ki, Mi, Gi (binary) or K, M, G (decimal). "
            "Examples: 1048576, '1Mi', '512Ki', '5Gi'" % value
        )
    number = float(match.group(1))
    suffix = match.group(2)
    if suffix:
        return int(number * _BYTE_UNITS[suffix])
    return int(number)


def parse_duration_value(value) -> int:
    """Parse a duration value into seconds.

    Accepts:
      - Plain integers: 120 -> 120 (seconds)
      - String with suffix: "2m" -> 120, "30s" -> 30, "1h" -> 3600
      - String without suffix: "120" -> 120 (seconds)

    Supported suffixes:
      s = seconds, m = minutes (x60), h = hours (x3600)
    """
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        raise ValueError("duration must be an int or string, got: %r" % value)

    match = _DURATION_PATTERN.match(value)
    if not match:
        raise ValueError(
            "invalid duration '%s'. Use a number optionally followed by "
            "s (seconds), m (minutes), or h (hours). "
            "Examples: 120, '2m', '30s', '1h'" % value
        )
    number = float(match.group(1))
    suffix = match.group(2)
    if suffix:
        return int(number * _DURATION_UNITS[suffix])
    return int(number)
