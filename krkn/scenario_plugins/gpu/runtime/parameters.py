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

"""Validated environment parameter parsing for the GPU worker."""

import math
import re


_UNIT_BYTES = {
    "ki": 1 << 10,
    "mi": 1 << 20,
    "gi": 1 << 30,
    "ti": 1 << 40,
}
_MEMORY_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(%|Ki|Mi|Gi|Ti)$", re.IGNORECASE)

LIMIT_FAULTS = ("clock-limit", "power-limit")


def csv_values(value):
    """Split a CSV setting, rejecting blank values and empty entries."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("value must be a non-empty comma-separated string")
    values = [item.strip() for item in value.split(",")]
    if any(not item for item in values):
        raise ValueError("comma-separated values cannot contain empty entries")
    return values


def memory_bytes(value: str, total: int) -> int:
    """Convert a percentage or explicit binary unit to an allocation size."""
    match = _MEMORY_RE.fullmatch(value.strip()) if isinstance(value, str) else None
    if not match:
        raise ValueError(f"invalid GPU_VRAM value: {value!r}; use a percentage or Ki/Mi/Gi/Ti")
    amount = float(match.group(1))
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("GPU_VRAM must be positive")
    unit = match.group(2)
    if unit == "%":
        if amount > 100:
            raise ValueError("GPU_VRAM percentage cannot exceed 100%")
        size = int(total * amount / 100)
    else:
        size = int(amount * _UNIT_BYTES[unit.lower()])
    if size <= 0:
        raise ValueError("GPU_VRAM resolves to less than one byte")
    return size


def validate_fault(value):
    """Reject unimplemented GPU fault identifiers explicitly."""
    faults = ("vram-pressure", "compute-pressure", *LIMIT_FAULTS)
    if value not in faults:
        raise ValueError(f"unsupported GPU_FAULT_TYPE: {value!r}; use {', '.join(faults)}")
    return value


def compute_duty_cycle(value):
    """Parse a whole compute load percentage, with an optional percent sign."""
    match = re.fullmatch(r"([1-9][0-9]{0,2})%?", str(value).strip())
    if match is None or int(match[1]) > 100:
        raise ValueError("GPU_COMPUTE_DUTY_CYCLE must be a whole percentage from 1 to 100")
    return int(match[1])


def compute_duty_cycle_values(value) -> list[int]:
    """Parse one duty cycle or an ordered comma-separated list."""
    try:
        values = csv_values(str(value))
    except ValueError as exc:
        raise ValueError(f"GPU_COMPUTE_DUTY_CYCLE: {exc}") from exc
    return [compute_duty_cycle(item) for item in values]


def clock_mhz_values(value) -> list[int]:
    """Parse one positive whole MHz ceiling or an ordered list of ceilings."""
    values = csv_values(str(value))
    if any(not re.fullmatch(r"[1-9][0-9]{0,9}", item) or int(item) > 0xFFFFFFFF for item in values):
        raise ValueError("GPU_CLOCK_MHZ requires positive whole MHz values")
    return [int(item) for item in values]


def power_limit_w_values(value) -> list[int]:
    """Parse one positive whole-watt limit or an ordered list of limits."""
    values = csv_values(str(value))
    if any(not re.fullmatch(r"[1-9][0-9]{0,6}", item) or int(item) > 0xFFFFFFFF // 1000 for item in values):
        raise ValueError("GPU_POWER_LIMIT_W requires positive whole watts representable in milliwatts")
    return [int(item) for item in values]


def is_gpu_resource(name: str, resource_name: str = "nvidia.com/gpu") -> bool:
    """Match GPU resources without including unrelated NVIDIA devices."""
    return name in (resource_name, "nvidia.com/gpu", "nvidia.com/gpu.shared") or name.startswith("nvidia.com/mig-")
