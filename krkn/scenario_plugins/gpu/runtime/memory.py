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

"""One CUDA-context-owning allocation thread per selected GPU."""

import threading

from . import common


class Allocation(threading.Thread):
    """Allocate and hold memory on one GPU, then report its cleanup."""

    def __init__(self, driver, device, requested_bytes, reserve_bytes):
        super().__init__(name=f"gpu-{device.index}", daemon=True)
        self.driver = driver
        self.device = device
        self.requested_bytes = requested_bytes
        self.reserve_bytes = reserve_bytes
        self.ready = threading.Event()
        self.stop_event = threading.Event()
        self.error = None
        self.ready_stats = None
        self.cleanup_stats = {
            "freed_bytes": 0,
            "cleanup_errors": [],
        }

    def stop(self):
        self.stop_event.set()


    def run(self):
        """Own the CUDA context through allocation, holding, and cleanup."""
        context = None
        allocations = []
        setup_complete = False
        try:
            if self.stop_event.is_set():
                return
            context = self.driver.create_context(self.device)
            free_before, total = self.driver.memory_info()
            if self.requested_bytes + self.reserve_bytes > free_before:
                raise common.WorkerError(
                    f"{self.device.uuid} has {free_before} free bytes; "
                    f"{self.requested_bytes} requested plus {self.reserve_bytes} reserve required"
                )
            remaining = self.requested_bytes
            while remaining and not self.stop_event.is_set():
                size = min(common.CHUNK_BYTES, remaining)
                allocations.append((self.driver.alloc(size), size))
                remaining -= size
            if self.stop_event.is_set():
                return
            actual = sum(size for _, size in allocations)
            if actual != self.requested_bytes:
                raise common.WorkerError(
                    f"{self.device.uuid} allocated {actual} of {self.requested_bytes} requested bytes"
                )
            free_after, context_total = self.driver.memory_info()
            total_bytes = min(total, context_total)
            self.ready_stats = {
                "uuid": self.device.uuid,
                "index": self.device.index,
                "requested_bytes": self.requested_bytes,
                "actual_bytes": actual,
                "total_bytes": total_bytes,
                "free_before_bytes": free_before,
                "free_bytes": free_after,
                "free_delta_bytes": free_before - free_after,
                "used_bytes": max(0, total_bytes - free_after),
                "allocation_chunks": len(allocations),
            }
            setup_complete = True
            self.ready.set()
            self.stop_event.wait()
        except BaseException as exc:
            self.error = exc
        finally:
            if not self.ready.is_set():
                self.ready.set()
            for pointer, size in reversed(allocations):
                try:
                    self.driver.free(pointer)
                    self.cleanup_stats["freed_bytes"] += size
                except BaseException as exc:
                    self.cleanup_stats["cleanup_errors"].append(str(exc))
            if context is not None:
                try:
                    self.driver.destroy_context(context)
                except BaseException as exc:
                    self.cleanup_stats["cleanup_errors"].append(str(exc))
            if setup_complete and not self.error and not self.cleanup_stats["cleanup_errors"]:
                self._probe_release()

    def _probe_release(self):
        context = None
        try:
            context = self.driver.create_context(self.device)
            free, total = self.driver.memory_info()
            probe_size = min(common.SMALL_ALLOCATION_BYTES, self.reserve_bytes)
            if free < probe_size:
                raise common.WorkerError(
                    f"{self.device.uuid} has insufficient free memory for release probe"
                )
            pointer = self.driver.alloc(probe_size)
            self.driver.free(pointer)
            self.cleanup_stats["post_release_free_bytes"] = free
            self.cleanup_stats["post_release_total_bytes"] = total
            self.cleanup_stats["small_allocation_bytes"] = probe_size
        except BaseException as exc:
            self.cleanup_stats["cleanup_errors"].append(
                f"post-release CUDA allocation probe failed: {exc}"
            )
        finally:
            if context is not None:
                try:
                    self.driver.destroy_context(context)
                except BaseException as exc:
                    self.cleanup_stats["cleanup_errors"].append(str(exc))
