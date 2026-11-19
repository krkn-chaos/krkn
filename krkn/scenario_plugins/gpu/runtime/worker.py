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

"""Externally coordinated CUDA VRAM and compute pressure worker."""

import json
import math
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, replace

from krkn_lib.gpu.models import Availability, GpuSnapshot, utc_now

from . import common, devices
from .compute import ComputeLoad
from .cuda import CudaDriver
from .memory import Allocation
from .parameters import compute_duty_cycle_values, csv_values, memory_bytes, validate_fault


@dataclass(frozen=True)
class _Settings:
    fault: str
    gpu_ids: str
    vram: str | None
    duty_cycles: list[int] | None
    duration: float
    setup_timeout: float
    recovery_timeout: float
    reserve_bytes: int | None
    targets: list


def _positive_float(value, name, default=None):
    if value is None:
        value = default
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise common.WorkerError(f"{name} must be a positive number") from None
    if not math.isfinite(result) or result <= 0:
        raise common.WorkerError(f"{name} must be a positive number")
    return result


def _settings(environ):
    try:
        fault = validate_fault(environ.get("GPU_FAULT_TYPE", ""))
        gpu_ids = environ.get("GPU_IDS", "all")
        if not isinstance(gpu_ids, str) or not gpu_ids.strip():
            raise common.WorkerError("GPU_IDS must be 'all' or a non-empty CSV list")
        gpu_ids = gpu_ids.strip()
        if gpu_ids.lower() != "all":
            csv_values(gpu_ids)
        vram = duty_cycles = reserve_bytes = None
        if fault == "vram-pressure":
            vram = environ.get("GPU_VRAM")
            if not vram:
                raise common.WorkerError("GPU_VRAM is required")
            reserve = environ.get("GPU_MEMORY_RESERVE", "64Mi")
            if not isinstance(reserve, str) or "%" in reserve:
                raise common.WorkerError("GPU_MEMORY_RESERVE must use an explicit binary unit such as 64Mi")
            reserve_bytes = memory_bytes(reserve, 1 << 63)
        else:
            duty_cycles = compute_duty_cycle_values(environ.get("GPU_COMPUTE_DUTY_CYCLE"))
        return _Settings(
            fault=fault,
            gpu_ids=gpu_ids,
            vram=vram,
            duty_cycles=duty_cycles,
            duration=_positive_float(environ.get("GPU_DURATION"), "GPU_DURATION"),
            setup_timeout=_positive_float(
                environ.get("GPU_SETUP_TIMEOUT"), "GPU_SETUP_TIMEOUT", common.DEFAULT_SETUP_TIMEOUT
            ),
            recovery_timeout=_positive_float(
                environ.get("GPU_RECOVERY_TIMEOUT"), "GPU_RECOVERY_TIMEOUT", common.DEFAULT_RECOVERY_TIMEOUT
            ),
            reserve_bytes=reserve_bytes,
            targets=devices.parse_targets(environ.get("GPU_TARGET_PODS", "[]")),
        )
    except ValueError as exc:
        raise common.WorkerError(str(exc)) from exc


def _emit(emit, record):
    emit(json.dumps(record, separators=(",", ":"), sort_keys=True))


def _per_gpu(values, count, name):
    if len(values) == 1:
        return values * count
    if len(values) != count:
        raise common.WorkerError(f"{name} has {len(values)} values for {count} selected GPUs")
    return values


def _requested_sizes(vram, selected):
    values = _per_gpu(csv_values(vram), len(selected), "GPU_VRAM")
    return [memory_bytes(value, device.total_bytes) for value, device in zip(values, selected)]


def _discover(environ, driver, smi, settings, pods_loader):
    nvidia_devices = smi.devices()
    cuda_devices = driver.devices()
    discovered = []
    for ordinal, cuda_index, uuid in cuda_devices:
        normalized = devices.normalize_uuid(uuid)
        if normalized not in nvidia_devices:
            raise common.WorkerError(f"CUDA GPU {normalized} is missing from nvidia-smi")
        host_index, total, mode = nvidia_devices[normalized]
        discovered.append(common.Device(cuda_index, host_index, normalized, total, mode))
    target_ids = None
    if settings.targets:
        target_ids = pods_loader(
            settings.targets,
            resource_name=environ.get("GPU_RESOURCE_NAME", "nvidia.com/gpu"),
        )
    selected = devices.select_devices(discovered, settings.gpu_ids, target_ids)
    for device in selected:
        if device.compute_mode != "Default":
            raise common.WorkerError(f"unsupported compute mode on {device.uuid}: {device.compute_mode}")
    return selected


def _check_errors(jobs, stage):
    for job in jobs:
        if job.error is not None:
            raise common.WorkerError(
                f"GPU {job.device.uuid} worker failed {stage}: {job.error}"
            ) from job.error


def _await_ready(allocations, deadline, clock):
    while True:
        _check_errors(allocations, "during setup")
        if all(allocation.ready.is_set() for allocation in allocations):
            break
        remaining = deadline - clock()
        if remaining <= 0:
            raise common.WorkerError("GPU setup timed out")
        for allocation in allocations:
            if not allocation.ready.is_set():
                allocation.ready.wait(min(0.05, remaining))
                break
    _check_errors(allocations, "during setup")
    return [allocation.ready_stats for allocation in allocations]


def _wait_for_start(allocations, start_file, deadline, sleep, clock):
    while not os.path.exists(start_file):
        _check_errors(allocations, "before common start")
        remaining = deadline - clock()
        if remaining <= 0:
            raise common.WorkerError("common GPU start barrier timed out")
        sleep(min(0.1, remaining))
    _check_errors(allocations, "at common start")


_SNAPSHOT_FIELDS = (*devices.MEMORY_FIELDS, "gpu_utilization_percent")
_SNAPSHOT_TIMEOUT_SECONDS = 5.0


def _error_snapshot():
    return GpuSnapshot(None, utc_now(), [], ["GPU observation failed"])


def _snapshot_dict(snapshot, selected):
    selected_uuids = {device.uuid for device in selected}
    filtered = []
    for measurement in snapshot.measurements:
        if measurement.scope != "physical_gpu":
            continue
        if _measurement_uuid(measurement) in selected_uuids:
            filtered.append(measurement)
    return replace(snapshot, measurements=filtered).to_dict()


def _measurement_uuid(measurement):
    try:
        return devices.normalize_uuid(measurement.device_uuid)
    except (common.WorkerError, TypeError, ValueError):
        return None


def _capture_snapshot(smi, selected, observations, phase, timeout_seconds):
    timeout_seconds = max(0.0, min(_SNAPSHOT_TIMEOUT_SECONDS, timeout_seconds))
    if timeout_seconds <= 0:
        snapshot = _error_snapshot()
    else:
        try:
            snapshot = smi.snapshot(_SNAPSHOT_FIELDS, timeout_seconds=timeout_seconds)
        except Exception:
            snapshot = _error_snapshot()
    observations[phase] = _snapshot_dict(snapshot, selected)
    return snapshot


def _memory_samples(snapshot, selected):
    selected_uuids = {device.uuid for device in selected}
    measurements = {}
    for measurement in snapshot.measurements:
        if measurement.scope != "physical_gpu" or measurement.field not in devices.MEMORY_FIELDS:
            continue
        uuid = _measurement_uuid(measurement)
        value = measurement.value
        if (
            uuid not in selected_uuids
            or measurement.status != Availability.AVAILABLE
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            continue
        measurements.setdefault(uuid, {})[measurement.field] = value
    records = []
    for device in selected:
        values = measurements.get(device.uuid, {})
        if any(field not in values for field in devices.MEMORY_FIELDS):
            raise common.WorkerError(f"nvidia-smi cannot observe selected GPU {device.uuid}")
        records.append({
            "uuid": device.uuid,
            "total_bytes": values["memory_total_bytes"],
            "free_bytes": values["memory_free_bytes"],
            "used_bytes": values["memory_used_bytes"],
        })
    return records


def _memory_by_uuid(snapshot, selected):
    return {
        record["uuid"]: record
        for record in _memory_samples(snapshot, selected)
    }



def _compute_samples(jobs, elapsed):
    records = [job.sample(elapsed) for job in jobs]
    return records if all(record["batches_completed"] for record in records) else None


def _hold(jobs, fault, started, deadline, observe, observations, emit, sleep, clock):
    next_observation = started
    while (now := clock()) < deadline:
        _check_errors(jobs, "during hold")
        if now >= next_observation:
            elapsed = now - started
            records = observe(elapsed, max(0.0, deadline - now))
            if records is not None:
                _emit(emit, {"phase": "holding", "fault_type": fault,
                             "elapsed_seconds": elapsed, "gpus": records,
                             "observations": {"holding": observations["holding"]}})
            next_observation = clock() + (
                5.0 if records is not None or fault == "vram-pressure" else 0.05
            )
        sleep(max(0.0, min(0.2, min(deadline, next_observation) - clock())))

def _stop_and_join(allocations, deadline, clock):
    for allocation in allocations:
        allocation.stop()
    for allocation in allocations:
        if allocation.ident is not None:
            allocation.join(max(0.0, deadline - clock()))


def _cleanup(allocations):
    return {
        allocation.device.uuid: {
            **allocation.cleanup_stats,
            "cleanup_errors": list(allocation.cleanup_stats["cleanup_errors"]),
        }
        for allocation in allocations
    }


def _cleanup_errors(allocations):
    errors = []
    for allocation in allocations:
        uuid = allocation.device.uuid
        errors.extend(f"{uuid}: {error}" for error in allocation.cleanup_stats["cleanup_errors"])
        if allocation.error is not None:
            errors.append(f"{uuid}: worker failed: {allocation.error}")
        if allocation.is_alive():
            errors.append(f"{uuid}: cleanup exceeded GPU_RECOVERY_TIMEOUT")
    return errors


def _complete(allocations, selected, requested_sizes, baseline, final):
    released = []
    for allocation, device, requested in zip(allocations, selected, requested_sizes):
        cleanup = allocation.cleanup_stats
        if cleanup["freed_bytes"] != requested:
            raise common.WorkerError(
                f"GPU {allocation.device.uuid} freed {cleanup['freed_bytes']} of {requested} requested bytes"
            )
        if cleanup.get("small_allocation_bytes", 0) < min(common.SMALL_ALLOCATION_BYTES, allocation.reserve_bytes):
            raise common.WorkerError(f"GPU {allocation.device.uuid} post-release CUDA allocation probe was too small")
        before = baseline[device.uuid]["free_bytes"]
        after = final[device.uuid]["free_bytes"]
        delta = after - before
        tolerance = max(allocation.reserve_bytes, int(requested * 0.10))
        released.append({
            "uuid": device.uuid,
            "requested_bytes": requested,
            "freed_bytes": cleanup["freed_bytes"],
            "post_release_free_bytes": after,
            "baseline_free_bytes": before,
            "free_delta_bytes": delta,
            "free_delta_tolerance_bytes": tolerance,
            "post_release_cuda_free_bytes": cleanup.get("post_release_free_bytes"),
            "post_release_cuda_total_bytes": cleanup.get("post_release_total_bytes"),
            "small_allocation_bytes": cleanup.get("small_allocation_bytes"),
            "free_delta_within_tolerance": abs(delta) <= tolerance,
        })
    return {"phase": "complete", "gpus": released}


def run_worker(environ=None, *, driver=None, smi=None, pods_loader=devices.pod_resource_devices,
               emit=None, sleep=time.sleep, clock=time.monotonic, start_file=common.START_FILE):
    """Apply the selected GPU fault and report setup, pressure, and cleanup."""
    emit = (lambda line: print(line, flush=True)) if emit is None else emit
    environ = os.environ if environ is None else environ
    jobs = []
    observations = {}
    recovery_timeout = common.DEFAULT_RECOVERY_TIMEOUT
    recovery_deadline = None
    try:
        settings = _settings(environ)
        recovery_timeout = settings.recovery_timeout
        setup_deadline = clock() + settings.setup_timeout
        driver = CudaDriver() if driver is None else driver
        smi = devices.NvidiaSmi() if smi is None else smi
        selected = _discover(environ, driver, smi, settings, pods_loader)
        requested_sizes = (
            _requested_sizes(settings.vram, selected)
            if settings.fault == "vram-pressure"
            else None
        )
        baseline_snapshot = _capture_snapshot(
            smi, selected, observations, "baseline", setup_deadline - clock(),
        )
        baseline = (
            _memory_by_uuid(baseline_snapshot, selected)
            if settings.fault == "vram-pressure"
            else None
        )
        if settings.fault == "vram-pressure":
            jobs = [
                Allocation(driver, device, requested, settings.reserve_bytes)
                for device, requested in zip(selected, requested_sizes)
            ]

            def observe(_elapsed, timeout_seconds):
                snapshot = _capture_snapshot(
                    smi, selected, observations, "holding", timeout_seconds,
                )
                try:
                    return _memory_samples(snapshot, selected)
                except common.WorkerError:
                    return None
        else:
            duty_cycles = _per_gpu(settings.duty_cycles, len(selected), "GPU_COMPUTE_DUTY_CYCLE")
            driver.bind_compute()
            jobs = [
                ComputeLoad(driver, device, duty_cycle, clock)
                for device, duty_cycle in zip(selected, duty_cycles)
            ]

            def observe(elapsed, timeout_seconds):
                records = _compute_samples(jobs, elapsed)
                if records is not None:
                    _capture_snapshot(
                        smi, selected, observations, "holding", timeout_seconds,
                    )
                return records
        if os.path.exists(start_file):
            os.unlink(start_file)
        for job in jobs:
            job.start()
        ready_stats = _await_ready(jobs, setup_deadline, clock)
        _emit(emit, {"phase": "ready", "fault_type": settings.fault, "gpus": ready_stats,
                     "observations": dict(observations)})
        _wait_for_start(jobs, start_file, setup_deadline, sleep, clock)
        started = clock()
        deadline = started + settings.duration
        if settings.fault == "compute-pressure":
            for job in jobs:
                job.start_load(deadline)
        _hold(jobs, settings.fault, started, deadline, observe, observations, emit, sleep, clock)
        recovery_deadline = clock() + recovery_timeout
        _stop_and_join(jobs, recovery_deadline, clock)
        _check_errors(jobs, "during cleanup")
        errors = _cleanup_errors(jobs)
        if errors:
            raise common.WorkerError("; ".join(errors))
        after_release = _capture_snapshot(
            smi, selected, observations, "after_release", recovery_deadline - clock(),
        )
        if settings.fault == "vram-pressure":
            final = _memory_by_uuid(after_release, selected)
            complete = _complete(jobs, selected, requested_sizes, baseline, final)
        else:
            records = [job.sample(settings.duration) for job in jobs]
            for record in records:
                if not record["batches_completed"]:
                    raise common.WorkerError(f"GPU {record['uuid']} completed no compute batches")
            complete = {"phase": "complete", "gpus": records}
        complete["fault_type"] = settings.fault
        complete["observations"] = dict(observations)
        _emit(emit, complete)
        return complete
    except BaseException as exc:
        if recovery_deadline is None:
            recovery_deadline = clock() + recovery_timeout
        _stop_and_join(jobs, recovery_deadline, clock)
        cleanup = _cleanup(jobs)
        errors = _cleanup_errors(jobs)
        message = str(exc) or exc.__class__.__name__
        record = {
            "phase": "error",
            "message": message,
            "cleanup": cleanup,
            "cleanup_errors": errors,
            "observations": dict(observations),
        }
        _emit(emit, record)
        raise common.WorkerError(message) from exc


def main():
    """Install signal cancellation and a bounded process lifetime."""
    emit = lambda line: print(line, flush=True)
    try:
        setup = _positive_float(
            os.environ.get("GPU_SETUP_TIMEOUT"), "GPU_SETUP_TIMEOUT", common.DEFAULT_SETUP_TIMEOUT
        )
        duration = _positive_float(os.environ.get("GPU_DURATION"), "GPU_DURATION")
        recovery = _positive_float(
            os.environ.get("GPU_RECOVERY_TIMEOUT"), "GPU_RECOVERY_TIMEOUT", common.DEFAULT_RECOVERY_TIMEOUT
        )
    except common.WorkerError as exc:
        _emit(emit, {"phase": "error", "message": str(exc), "cleanup": {}, "cleanup_errors": []})
        return 1
    timer = threading.Timer(
        setup + duration + recovery + common.LIFETIME_MARGIN_SECONDS,
        os._exit,
        args=(1,),
    )
    timer.daemon = True
    timer.start()

    def cancel(signum, _frame):
        raise common.WorkerCancelled(f"worker received signal {signum}")

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, cancel)
    try:
        run_worker()
        return 0
    except common.WorkerError:
        return 1
    finally:
        timer.cancel()


if __name__ == "__main__":
    sys.exit(main())
