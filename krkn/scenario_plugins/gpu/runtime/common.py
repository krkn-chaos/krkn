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

"""Data and limits shared by the standalone GPU runtime."""

from dataclasses import dataclass

MIB = 1 << 20
CHUNK_BYTES = 64 * MIB
SMALL_ALLOCATION_BYTES = MIB
POD_RESOURCES_SOCKET = "/var/lib/kubelet/pod-resources/kubelet.sock"
START_FILE = "/tmp/krkn-gpu-start"
STOP_FILE = START_FILE + "-stop"
DEFAULT_SETUP_TIMEOUT = 120.0
DEFAULT_RECOVERY_TIMEOUT = 30.0
LIFETIME_MARGIN_SECONDS = 10.0


class WorkerError(RuntimeError):
    """GPU discovery, allocation, or recovery failed."""


class WorkerCancelled(WorkerError):
    """The GPU workload was cancelled."""


@dataclass(frozen=True)
class Device:
    """A CUDA device matched to its host index and physical UUID."""

    ordinal: int
    index: int
    uuid: str
    total_bytes: int
    compute_mode: str
