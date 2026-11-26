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

"""Bounded FP32 compute load on one CUDA context per selected GPU."""

import ctypes
import threading

from .common import WorkerError

_BLOCK_SIZE = 256
_BLOCKS_PER_SM = 4
_TARGET_BATCH_SECONDS = 0.010
_INITIAL_ITERATIONS = 256
_MAX_ITERATIONS = 65536
_CALIBRATION_BATCHES = 3

# Independent FMA chains keep work in registers. One final store per thread
# makes the result observable without a streaming memory workload.
_COMPUTE_PTX = b"""
.version 4.2
.target sm_50
.address_size 64

.visible .entry krkn_compute(.param .u64 output, .param .u32 iterations)
{
    .reg .pred p;
    .reg .u32 count, tid, bid, width, index;
    .reg .u64 base, offset, address;
    .reg .f32 a, b, c, d;

    ld.param.u64 base, [output];
    ld.param.u32 count, [iterations];
    mov.u32 tid, %tid.x;
    mov.u32 bid, %ctaid.x;
    mov.u32 width, %ntid.x;
    mad.lo.u32 index, bid, width, tid;
    cvt.rn.f32.u32 a, index;
    add.f32 b, a, 0f3f800000;
    add.f32 c, a, 0f40000000;
    add.f32 d, a, 0f40400000;

loop:
    fma.rn.f32 a, a, 0f3f7ffe00, 0f3d800000;
    fma.rn.f32 b, b, 0f3f7ffc00, 0f3e000000;
    fma.rn.f32 c, c, 0f3f7ff800, 0f3e800000;
    fma.rn.f32 d, d, 0f3f7ff000, 0f3f000000;
    fma.rn.f32 a, a, 0f3f7ffe00, 0f3d800000;
    fma.rn.f32 b, b, 0f3f7ffc00, 0f3e000000;
    fma.rn.f32 c, c, 0f3f7ff800, 0f3e800000;
    fma.rn.f32 d, d, 0f3f7ff000, 0f3f000000;
    fma.rn.f32 a, a, 0f3f7ffe00, 0f3d800000;
    fma.rn.f32 b, b, 0f3f7ffc00, 0f3e000000;
    fma.rn.f32 c, c, 0f3f7ff800, 0f3e800000;
    fma.rn.f32 d, d, 0f3f7ff000, 0f3f000000;
    fma.rn.f32 a, a, 0f3f7ffe00, 0f3d800000;
    fma.rn.f32 b, b, 0f3f7ffc00, 0f3e000000;
    fma.rn.f32 c, c, 0f3f7ff800, 0f3e800000;
    fma.rn.f32 d, d, 0f3f7ff000, 0f3f000000;
    sub.u32 count, count, 1;
    setp.ne.u32 p, count, 0;
    @p bra loop;

    add.f32 a, a, b;
    add.f32 c, c, d;
    add.f32 a, a, c;
    mul.wide.u32 offset, index, 4;
    add.u64 address, base, offset;
    st.global.f32 [address], a;
    ret;
}
"""


class ComputeLoad(threading.Thread):
    """Prepare a kernel, wait for the start barrier, then run paced batches."""

    def __init__(self, driver, device, duty_cycle, clock):
        super().__init__(name=f"gpu-compute-{device.index}", daemon=True)
        self.driver = driver
        self.device = device
        self.duty_cycle = duty_cycle
        self.clock = clock
        self.ready = threading.Event()
        self._start_event = threading.Event()
        self._stop_event = threading.Event()
        self._deadline = 0.0
        self._completed = (0, 0, 0.0)
        self.error = None
        self.ready_stats = None
        self.cleanup_stats = {"cleanup_errors": []}

    def start_load(self, deadline):
        """Allow kernel submissions until the common monotonic deadline."""
        self._deadline = deadline
        self._start_event.set()

    def stop(self):
        """Cancel future submissions and interrupt pacing or barrier waits."""
        self._stop_event.set()
        self._start_event.set()

    def sample(self, elapsed):
        """Return a consistent snapshot of synchronized kernel completions."""
        batches, iterations, wait_seconds = self._completed
        return {
            **self.ready_stats,
            "batches_completed": batches,
            "loop_iterations_completed": iterations,
            "batches_per_second": batches / elapsed if elapsed > 0 else 0.0,
            "launch_wait_seconds": wait_seconds,
        }

    def run(self):
        """Own all CUDA state on this thread through setup and cleanup."""
        context = module = output = None
        try:
            if self._stop_event.is_set():
                return
            sm_count = self.driver.sm_count(self.device)
            if sm_count < 1:
                raise WorkerError(f"invalid CUDA SM count: {sm_count}")
            grid = sm_count * _BLOCKS_PER_SM
            context = self.driver.create_context(self.device)
            module = self.driver.load_module(_COMPUTE_PTX)
            kernel = self.driver.get_kernel(module, b"krkn_compute")
            scratch_bytes = grid * _BLOCK_SIZE * ctypes.sizeof(ctypes.c_float)
            output = self.driver.alloc(scratch_bytes)
            self.ready_stats = {
                "uuid": self.device.uuid,
                "sm_count": sm_count,
                "compute_duty_cycle": self.duty_cycle,
                "scratch_bytes": scratch_bytes,
            }
            self.ready.set()
            self._start_event.wait()
            self._run_batches(kernel, grid, ctypes.c_uint64(output))
        except BaseException as exc:
            self.error = exc
        finally:
            for release, resource in (
                (self.driver.free, output),
                (self.driver.unload_module, module),
                (self.driver.destroy_context, context),
            ):
                if resource is not None:
                    try:
                        release(resource)
                    except Exception as exc:
                        self.cleanup_stats["cleanup_errors"].append(f"{release.__name__}: {exc}")
            self.ready.set()

    def _run_batches(self, kernel, grid, output):
        iterations = ctypes.c_uint32(_INITIAL_ITERATIONS)
        rest_ratio = (100 - self.duty_cycle) / self.duty_cycle
        batches = total_iterations = 0
        wait_seconds = 0.0
        while not self._stop_event.is_set():
            started = self.clock()
            if started >= self._deadline:
                break
            self.driver.run_compute(kernel, grid, _BLOCK_SIZE, output, iterations)
            finished = self.clock()
            busy = finished - started
            batches += 1
            total_iterations += iterations.value
            wait_seconds += busy
            self._completed = (batches, total_iterations, wait_seconds)
            if batches <= _CALIBRATION_BATCHES:
                # Bound both the adjustment and absolute work; scheduling on a
                # shared GPU can still make a launch take longer than 10 ms.
                ratio = min(8.0, _TARGET_BATCH_SECONDS / max(busy, 1e-6))
                iterations.value = max(1, min(_MAX_ITERATIONS, int(iterations.value * ratio)))
            rest = min(busy * rest_ratio, self._deadline - finished)
            if rest > 0:
                self._stop_event.wait(rest)
