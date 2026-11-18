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

"""Direct bindings to CUDA Driver API device, memory, and kernel calls."""

import ctypes
import ctypes.util
import glob
import os

from .common import WorkerError


class _CUuuid(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]


class CudaDriver:
    """Small direct binding to the CUDA Driver API."""

    def __init__(self, library=None):
        if library is not None and not isinstance(library, str):
            self.lib = library
        else:
            candidates = []
            if library:
                candidates.append(library)
            found = ctypes.util.find_library("cuda")
            if found:
                candidates.append(found)
            for directory in (
                "/host-driver/usr/lib64",
                "/host-driver/usr/lib/x86_64-linux-gnu",
                "/host-driver/lib64",
                "/host-driver/lib/x86_64-linux-gnu",
                "/usr/local/nvidia/lib64",
                "/usr/local/nvidia/lib",
                "/host-driver/usr/lib/aarch64-linux-gnu",
                "/host-driver/lib/aarch64-linux-gnu",
            ):
                candidates.extend(glob.glob(os.path.join(directory, "libcuda.so*")))
            candidates.extend(("libcuda.so.1", "libcuda.so"))
            error = None
            self.lib = None
            for candidate in dict.fromkeys(candidates):
                try:
                    self.lib = ctypes.CDLL(candidate)
                    break
                except OSError as exc:
                    error = exc
            if self.lib is None:
                raise WorkerError(f"cannot load CUDA driver library: {error or 'libcuda.so.1 not found'}")
        self._bind("cuInit", [ctypes.c_uint])
        self._bind("cuDeviceGetCount", [ctypes.POINTER(ctypes.c_int)])
        self._bind("cuDeviceGet", [ctypes.POINTER(ctypes.c_int), ctypes.c_int])
        uuid_fn = getattr(self.lib, "cuDeviceGetUuid_v2", None) or getattr(self.lib, "cuDeviceGetUuid", None)
        if uuid_fn is None:
            raise WorkerError("CUDA driver lacks cuDeviceGetUuid")
        uuid_fn.argtypes = [ctypes.POINTER(_CUuuid), ctypes.c_int]
        uuid_fn.restype = ctypes.c_int
        self._device_uuid = uuid_fn
        self._bind("cuCtxCreate_v2", [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint, ctypes.c_int])
        self._bind("cuCtxDestroy_v2", [ctypes.c_void_p])
        self._bind("cuMemGetInfo_v2", [ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)])
        self._bind("cuMemAlloc_v2", [ctypes.POINTER(ctypes.c_uint64), ctypes.c_size_t])
        self._bind("cuMemFree_v2", [ctypes.c_uint64])
        self._bind("cuGetErrorName", [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)], required=False)
        self._bind("cuGetErrorString", [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)], required=False)
        self.check(self.lib.cuInit(0))

    def _bind(self, name, argtypes, required=True):
        fn = getattr(self.lib, name, None)
        if fn is None:
            if required:
                raise WorkerError(f"CUDA driver lacks {name}")
            return
        fn.argtypes = argtypes
        fn.restype = ctypes.c_int

    def _error_text(self, code):
        parts = []
        for name in ("cuGetErrorName", "cuGetErrorString"):
            fn = getattr(self.lib, name, None)
            if fn is not None:
                value = ctypes.c_char_p()
                if fn(code, ctypes.byref(value)) == 0 and value.value:
                    parts.append(value.value.decode("utf-8", "replace"))
        return ": ".join(parts) or f"CUDA error {code}"

    def check(self, code):
        if code:
            raise WorkerError(self._error_text(code))

    def devices(self):
        count = ctypes.c_int()
        self.check(self.lib.cuDeviceGetCount(ctypes.byref(count)))
        result = []
        for ordinal in range(count.value):
            device = ctypes.c_int()
            self.check(self.lib.cuDeviceGet(ctypes.byref(device), ordinal))
            identifier = _CUuuid()
            self.check(self._device_uuid(ctypes.byref(identifier), device.value))
            raw = bytes(identifier.bytes).hex()
            uuid = "GPU-" + "-".join((raw[:8], raw[8:12], raw[12:16], raw[16:20], raw[20:]))
            result.append((ordinal, device.value, uuid))
        return result

    def create_context(self, device):
        context = ctypes.c_void_p()
        self.check(self.lib.cuCtxCreate_v2(ctypes.byref(context), 0, device.ordinal))
        return context

    def destroy_context(self, context):
        self.check(self.lib.cuCtxDestroy_v2(context))

    def memory_info(self):
        free = ctypes.c_size_t()
        total = ctypes.c_size_t()
        self.check(self.lib.cuMemGetInfo_v2(ctypes.byref(free), ctypes.byref(total)))
        return free.value, total.value

    def alloc(self, size):
        pointer = ctypes.c_uint64()
        self.check(self.lib.cuMemAlloc_v2(ctypes.byref(pointer), size))
        return pointer.value

    def free(self, pointer):
        self.check(self.lib.cuMemFree_v2(pointer))

    def bind_compute(self):
        """Bind kernel APIs only for the compute fault, before starting workers."""
        uint = ctypes.c_uint
        handle = ctypes.c_void_p
        pointer = ctypes.POINTER(handle)
        self._bind("cuDeviceGetAttribute", [ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int])
        self._bind("cuModuleLoadData", [pointer, ctypes.c_char_p])
        self._bind("cuModuleUnload", [handle])
        self._bind("cuModuleGetFunction", [pointer, handle, ctypes.c_char_p])
        self._bind("cuLaunchKernel", [handle, uint, uint, uint, uint, uint, uint, uint,
                                      handle, pointer, pointer])
        self._bind("cuCtxSynchronize", [])

    def sm_count(self, device):
        """Return the number of streaming multiprocessors on the device."""
        count = ctypes.c_int()
        multiprocessor_count = 16  # CU_DEVICE_ATTRIBUTE_MULTIPROCESSOR_COUNT
        self.check(self.lib.cuDeviceGetAttribute(ctypes.byref(count), multiprocessor_count, device.ordinal))
        return count.value

    def load_module(self, ptx):
        """Load a NUL-terminated PTX module in the calling thread's context."""
        module = ctypes.c_void_p()
        result = self.lib.cuModuleLoadData(ctypes.byref(module), ptx)
        if result:
            raise WorkerError(f"cannot JIT GPU compute PTX: {self._error_text(result)}")
        return module

    def unload_module(self, module):
        """Release the module in the calling thread's context."""
        self.check(self.lib.cuModuleUnload(module))

    def get_kernel(self, module, name):
        """Resolve a kernel entry point by name."""
        function = ctypes.c_void_p()
        self.check(self.lib.cuModuleGetFunction(ctypes.byref(function), module, name))
        return function

    def run_compute(self, kernel, grid, block, output, iterations):
        """Submit one compute batch and wait for completion in this context."""
        args = (ctypes.c_void_p * 2)(
            ctypes.addressof(output), ctypes.addressof(iterations),
        )
        self.check(self.lib.cuLaunchKernel(kernel, grid, 1, 1, block, 1, 1, 0, None, args, None))
        self.check(self.lib.cuCtxSynchronize())
