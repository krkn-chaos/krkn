# Copyright 2026 The Krkn Authors
# SPDX-License-Identifier: Apache-2.0

"""Bounded NVML commands for physical GPU limits."""

import ctypes as c
import json
import subprocess
import sys

from .common import WorkerError


class LimitControl:
    """Run each driver call with a timeout, outside the watchdog process."""

    def __init__(self, fault):
        self.fault = fault

    def call(self, operation, uuid, timeout, target=None):
        if timeout <= 0:
            raise WorkerError(f"GPU {uuid} {self.fault} {operation} deadline expired")
        command = [sys.executable, "-m", __name__, self.fault, operation, uuid]
        if target is not None:
            command.append(str(target))
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise WorkerError(f"GPU {uuid} {self.fault} {operation} timed out") from exc
        if result.returncode:
            raise WorkerError(f"GPU {uuid} {self.fault} {operation}: {result.stderr.strip() or result.returncode}")
        if result.stdout:
            return json.loads(result.stdout)


def _nvml(fault, operation, uuid, *values):
    lib = c.CDLL("libnvidia-ml.so.1")
    lib.nvmlErrorString.argtypes = [c.c_int]
    lib.nvmlErrorString.restype = c.c_char_p

    def check(status):
        if status:
            raise WorkerError(lib.nvmlErrorString(status).decode())

    check(lib.nvmlInit_v2())
    try:
        handle = c.c_void_p()
        lookup = lib.nvmlDeviceGetHandleByUUID
        lookup.argtypes = [c.c_char_p, c.POINTER(c.c_void_p)]
        check(lookup(uuid.encode(), c.byref(handle)))
        if fault == "power-limit":
            return _power(lib, check, handle, operation, *values)
        if fault == "clock-limit":
            return _clock(lib, check, handle, operation, *values)
        raise WorkerError(f"unsupported NVML fault: {fault}")
    finally:
        check(lib.nvmlShutdown())


def _clock(lib, check, handle, operation, *values):
    if operation == "reset":
        reset = lib.nvmlDeviceResetGpuLockedClocks
        reset.argtypes = [c.c_void_p]
        check(reset(handle))
        return None
    if operation == "set":
        lock = lib.nvmlDeviceSetGpuLockedClocks
        lock.argtypes = [c.c_void_p, c.c_uint, c.c_uint]
        target, = map(int, values)
        check(lock(handle, target, target))
        return None
    max_clock = lib.nvmlDeviceGetMaxClockInfo
    max_clock.argtypes = [c.c_void_p, c.c_uint, c.POINTER(c.c_uint)]
    maximum = c.c_uint()
    check(max_clock(handle, 1, c.byref(maximum)))  # NVML_CLOCK_SM

    def bins(name, *args):
        func = getattr(lib, name)
        func.argtypes = [c.c_void_p, *([c.c_uint] * len(args)), c.POINTER(c.c_uint), c.POINTER(c.c_uint)]
        count = c.c_uint()
        status = func(handle, *args, c.byref(count), None)
        if status != 7:  # NVML_ERROR_INSUFFICIENT_SIZE
            check(status)
        if not count.value:
            return []
        frequencies = (c.c_uint * count.value)()
        check(func(handle, *args, c.byref(count), frequencies))
        return frequencies[:count.value]

    supported = {
        mhz for memory in bins("nvmlDeviceGetSupportedMemoryClocks")
        for mhz in bins("nvmlDeviceGetSupportedGraphicsClocks", memory)
    }
    return maximum.value, sorted(supported)


def _power(lib, check, handle, operation, *values):
    def read(name, count=1):
        func = getattr(lib, name)
        func.argtypes = [c.c_void_p, *([c.POINTER(c.c_uint)] * count)]
        outputs = [c.c_uint() for _ in range(count)]
        check(func(handle, *(c.byref(value) for value in outputs)))
        return tuple(value.value for value in outputs)

    configured = "nvmlDeviceGetPowerManagementLimit"
    enforced = "nvmlDeviceGetEnforcedPowerLimit"
    if operation == "inspect":
        return (
            *read("nvmlDeviceGetPowerManagementLimitConstraints", 2),
            *read(configured),
            *read(enforced),
        )
    if operation == "read":
        return (*read(configured), *read(enforced))
    target, = map(int, values)
    setter = lib.nvmlDeviceSetPowerManagementLimit
    setter.argtypes = [c.c_void_p, c.c_uint]
    if operation == "restore":
        status = setter(handle, target)
        restored, = read(configured)
        if restored != target:
            check(status)
        return restored
    check(setter(handle, target))


if __name__ == "__main__":
    try:
        result = _nvml(*sys.argv[1:])
        if result is not None:
            print(json.dumps(result))
    except (WorkerError, OSError, AttributeError) as exc:
        sys.exit(str(exc))
