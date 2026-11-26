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

"""Externally coordinated GPU fault worker."""

import json
import math
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from krkn_lib.gpu.models import Availability, GpuSnapshot, utc_now

from . import common, devices
from .compute import ComputeLoad
from .cuda import CudaDriver
from .limits import LimitControl
from .memory import Allocation
from .parameters import (
    LIMIT_FAULTS, clock_mhz_values, compute_duty_cycle_values, csv_values,
    memory_bytes, power_limit_w_values, validate_fault,
)


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
        elif fault == "compute-pressure":
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
        remaining = deadline - clock()
        if remaining <= 0:
            raise common.WorkerError("GPU setup timed out")
        if all(allocation.ready.is_set() for allocation in allocations):
            if clock() >= deadline:
                raise common.WorkerError("GPU setup timed out")
            break
        for allocation in allocations:
            if not allocation.ready.is_set():
                allocation.ready.wait(min(0.05, remaining))
                break
    _check_errors(allocations, "during setup")
    return [allocation.ready_stats for allocation in allocations]


def _wait_for_start(start_file, deadline, sleep, clock, stop_file=None):
    while (remaining := deadline - clock()) > 0:
        if stop_file and stop_file.exists():
            raise common.WorkerCancelled("GPU worker cancelled before release")
        if os.path.exists(start_file):
            if clock() < deadline:
                return
            break
        sleep(min(0.1, remaining))
    raise common.WorkerError("common GPU start barrier timed out")

_SNAPSHOT_FIELDS = (*devices.MEMORY_FIELDS, "gpu_utilization_percent")
_CLOCK_FIELDS = (
    "sm_clock_mhz", "memory_clock_mhz", "power_limit_w", "power_draw_w",
    "gpu_temperature_c", "gpu_utilization_percent",
)
_POWER_FIELDS = (*_CLOCK_FIELDS, "power_enforced_limit_w", "sw_power_cap_active")
_SNAPSHOT_TIMEOUT_SECONDS = 5.0


def _error_snapshot(message="GPU observation failed"):
    return GpuSnapshot(None, utc_now(), [], [message])


def _record_observation_error(observation_errors, phase, message):
    errors = observation_errors.setdefault(phase, [])
    message = str(message)
    if message not in errors:
        errors.append(message)


def _capture_snapshot(smi, selected, phase, timeout_seconds, observation_errors, fields=_SNAPSHOT_FIELDS):
    timeout_seconds = max(0.0, min(_SNAPSHOT_TIMEOUT_SECONDS, timeout_seconds))
    if timeout_seconds <= 0:
        snapshot = _error_snapshot("GPU observation timed out")
    else:
        try:
            snapshot = smi.snapshot(
                fields,
                device_uuids=[device.uuid for device in selected],
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            snapshot = _error_snapshot()
            _record_observation_error(observation_errors, phase, exc)
    for error in snapshot.errors:
        _record_observation_error(observation_errors, phase, error)
    return snapshot


def _snapshot_available(snapshot, selected, field):
    available = {
        measurement.device_uuid
        for measurement in snapshot.measurements
        if measurement.scope == "physical_gpu"
        and measurement.field == field
        and measurement.status == Availability.AVAILABLE
    }
    return all(device.uuid in available for device in selected)


def _memory_samples(snapshot, selected):
    measurements = {}
    for measurement in snapshot.measurements:
        if measurement.scope != "physical_gpu" or measurement.field not in devices.MEMORY_FIELDS:
            continue
        uuid = measurement.device_uuid
        value = measurement.value
        if (
            uuid is None
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


def _hold(jobs, fault, started, deadline, observe, observations, observation_errors,
          emit, sleep, clock):
    next_observation = started
    last_records = None
    while (now := clock()) < deadline:
        _check_errors(jobs, "during hold")
        if now >= next_observation:
            elapsed = now - started
            records = observe(elapsed, max(0.0, deadline - now))
            if records is not None:
                last_records = records
            if last_records is not None:
                payload = {
                    "phase": "holding",
                    "fault_type": fault,
                    "elapsed_seconds": elapsed,
                    "gpus": last_records,
                    "observation_errors": dict(observation_errors),
                }
                if "holding" in observations:
                    payload["observations"] = {"holding": observations["holding"]}
                _emit(emit, payload)
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


def _error_gpu_stats(jobs):
    records = []
    for job in jobs:
        record = {"uuid": job.device.uuid, **(job.ready_stats or {})}
        cleanup = job.cleanup_stats
        requested = getattr(job, "requested_bytes", None)
        if requested is not None:
            record["requested_bytes"] = requested
        if "freed_bytes" in cleanup:
            record["freed_bytes"] = cleanup["freed_bytes"]
        for source, target in (
            ("post_release_free_bytes", "post_release_cuda_free_bytes"),
            ("post_release_total_bytes", "post_release_cuda_total_bytes"),
            ("small_allocation_bytes", "small_allocation_bytes"),
        ):
            if source in cleanup:
                record[target] = cleanup[source]
        if cleanup.get("cleanup_errors"):
            record["cleanup_errors"] = list(cleanup["cleanup_errors"])
        records.append(record)
    return records


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
            **allocation.ready_stats,
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


def _run_limit_worker(environ, smi, pods_loader, emit, sleep, clock, start_file):
    fault = environ["GPU_FAULT_TYPE"]
    power = fault == "power-limit"
    backend = LimitControl(fault)
    stop_file = Path(f"{start_file}-stop")
    observations, errors, records, restorations = {}, {}, {}, {}
    limit_targets, original_power_limits = {}, {}
    attempted = []
    failure = None

    def event(phase, **extra):
        _emit(emit, {
            "phase": phase, "fault_type": fault, "gpus": list(records.values()),
            "observations": dict(observations), "observation_errors": dict(errors),
            **extra,
        })

    def snapshot(phase, deadline):
        fields = _POWER_FIELDS if power else _CLOCK_FIELDS
        result = _capture_snapshot(smi, selected, phase, deadline - clock(), errors, fields)
        observations[phase] = result.to_dict()
        return result

    def verify_power_limit(uuid, target, record, deadline):
        deadline = min(deadline, clock() + 5)
        last_readback = "no successful readback"
        read_error = None
        while (remaining := deadline - clock()) > 0:
            if stop_file.exists():
                raise common.WorkerCancelled(f"GPU {fault} fault cancelled")
            try:
                configured, enforced = backend.call("read", uuid, remaining)
            except common.WorkerError as exc:
                read_error = exc
                break
            configured_w, enforced_w = configured / 1000, enforced / 1000
            record.update(applied_power_limit_w=configured_w, enforced_power_limit_w=enforced_w)
            if configured == enforced == target:
                return
            last_readback = f"configured {configured_w:g} W, enforced {enforced_w:g} W"
            sleep(max(0, min(0.2, deadline - clock())))
        reason = f"NVML read failed: {read_error}" if read_error else "verification timed out"
        raise common.WorkerError(
            f"GPU {uuid}: {target / 1000:g} W power cap not verified ({reason}; last NVML readback: {last_readback})"
        ) from read_error

    try:
        settings = _settings(environ)
        setup_deadline = clock() + settings.setup_timeout
        smi = devices.NvidiaSmi() if smi is None else smi
        targets = settings.targets
        resource = environ.get("GPU_RESOURCE_NAME", "nvidia.com/gpu")
        visible = [
            common.Device(index, index, uuid, total, mode)
            for uuid, (index, total, mode) in smi.devices().items()
        ]
        allocated = pods_loader(targets, resource_name=resource) if targets else None
        selected = devices.select_devices(visible, settings.gpu_ids, allocated)
        env_name, parse = (
            ("GPU_POWER_LIMIT_W", power_limit_w_values) if power
            else ("GPU_CLOCK_MHZ", clock_mhz_values)
        )
        values = _per_gpu(parse(environ.get(env_name)), len(selected), env_name)
        for device, requested in zip(selected, values, strict=True):
            uuid = device.uuid
            if device.compute_mode != "Default":
                raise common.WorkerError(f"unsupported compute mode on {uuid}: {device.compute_mode}")
            record = {"uuid": uuid, "index": device.index}
            if power:
                minimum, maximum, original, enforced = backend.call("inspect", uuid, min(5, setup_deadline - clock()))
                target = requested * 1000
                if not 0 < minimum <= original <= maximum or enforced <= 0:
                    raise common.WorkerError(f"GPU {uuid}: unusable power limits reported by NVML")
                if not minimum <= target <= maximum:
                    raise common.WorkerError(f"GPU {uuid}: {requested} W is outside {minimum / 1000:g}–{maximum / 1000:g} W")
                if target >= min(original, enforced):
                    raise common.WorkerError(f"GPU {uuid}: {requested} W must lower the current power limit")
                original_power_limits[uuid] = original
                record.update(
                    requested_power_limit_w=requested, original_power_limit_w=original / 1000,
                    min_power_limit_w=minimum / 1000, max_power_limit_w=maximum / 1000,
                )
            else:
                maximum, supported = backend.call("inspect", uuid, min(5, setup_deadline - clock()))
                if requested > maximum:
                    raise common.WorkerError(f"GPU {uuid}: {requested} MHz exceeds maximum {maximum} MHz")
                target = max((mhz for mhz in supported if 0 < mhz <= requested), default=None)
                if target is None:
                    raise common.WorkerError(f"GPU {uuid}: no supported SM clock at or below {requested} MHz")
                record.update(requested_sm_clock_mhz=requested, max_sm_clock_mhz=maximum, clock_target_observed=False)
            limit_targets[uuid] = target
            records[uuid] = record
            restorations[uuid] = {"status": "not_needed"}

        Path(start_file).unlink(missing_ok=True)
        event("ready")
        _wait_for_start(start_file, setup_deadline, sleep, clock, stop_file)
        devices.require_exclusive_gpus(visible, selected, targets, resource, min(5, setup_deadline - clock()))
        snapshot("baseline", setup_deadline)
        for uuid, record in records.items():
            if stop_file.exists():
                raise common.WorkerCancelled(f"GPU {fault} fault cancelled")
            if clock() >= setup_deadline:
                raise common.WorkerError(f"GPU {fault} setup timed out")
            attempted.append(uuid)
            target = limit_targets[uuid]
            backend.call("set", uuid, min(5, setup_deadline - clock()), target)
            if power:
                verify_power_limit(uuid, target, record, setup_deadline)
            else:
                record["applied_sm_clock_mhz"] = target
        deadline = clock() + settings.duration
        event("started")
        while clock() < deadline and not stop_file.exists():
            at_target = set()
            for measurement in snapshot("holding", deadline).measurements:
                uuid = measurement.device_uuid
                if uuid not in records or measurement.scope != "physical_gpu" or measurement.status != Availability.AVAILABLE:
                    continue
                record = records[uuid]
                if power and measurement.field == "sw_power_cap_active":
                    record["power_throttle_observed"] = record.get("power_throttle_observed", False) or measurement.value
                elif not power and measurement.field == "sm_clock_mhz" and measurement.value == record["applied_sm_clock_mhz"]:
                    record["clock_target_observed"] = True
                    at_target.add(uuid)
            if (power or len(at_target) == len(records)) and clock() < deadline and not stop_file.exists():
                event("holding")
            sample_at = min(clock() + 1, deadline)
            while clock() < sample_at and not stop_file.exists():
                sleep(max(0, min(0.2, sample_at - clock())))
        if stop_file.exists():
            raise common.WorkerCancelled(f"GPU {fault} fault cancelled")
        if not power and not all(record["clock_target_observed"] for record in records.values()):
            raise common.WorkerError("applied SM clocks were not observed on all selected GPUs")
    except BaseException as exc:
        failure = exc
    finally:
        if attempted:
            recovery_deadline = clock() + settings.recovery_timeout
            for i, uuid in enumerate(attempted):
                restoration = restorations[uuid]
                try:
                    budget = (recovery_deadline - clock()) / (len(attempted) - i)
                    if power:
                        original = original_power_limits[uuid]
                        restored = backend.call("restore", uuid, min(5, budget), original)
                        if restored != original:
                            raise common.WorkerError(f"GPU {uuid}: expected {original} mW after restore, read {restored} mW")
                        restoration["status"] = "verified"
                    else:
                        backend.call("reset", uuid, min(5, budget))
                        restoration["status"] = "reset_acknowledged"
                except Exception as exc:
                    restoration.update(status="unverified", reason=str(exc))
                    failure = failure or exc
            snapshot("after_release", recovery_deadline)

    safe = all(item["status"] != "unverified" for item in restorations.values())
    details = {"device_restorations": restorations, "restoration_safe": safe}
    if failure is not None:
        event("error", message=str(failure) or type(failure).__name__, **details)
        raise common.WorkerError(str(failure)) from failure
    return_event = {
        "phase": "complete", "fault_type": fault, "gpus": list(records.values()),
        "observations": observations, "observation_errors": errors, **details,
    }
    _emit(emit, return_event)
    return return_event


def run_worker(environ=None, *, driver=None, smi=None, pods_loader=devices.pod_resource_devices,
               emit=None, sleep=time.sleep, clock=time.monotonic, start_file=common.START_FILE):
    """Apply the selected GPU fault and report setup, pressure, and cleanup."""
    emit = (lambda line: print(line, flush=True)) if emit is None else emit
    environ = os.environ if environ is None else environ
    if environ.get("GPU_FAULT_TYPE") in LIMIT_FAULTS:
        return _run_limit_worker(environ, smi, pods_loader, emit, sleep, clock, start_file)
    jobs = []
    observations = {}
    observation_errors = {}
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
        duty_cycles = (
            _per_gpu(settings.duty_cycles, len(selected), "GPU_COMPUTE_DUTY_CYCLE")
            if settings.fault == "compute-pressure"
            else None
        )
        if os.path.exists(start_file):
            os.unlink(start_file)
        _emit(emit, {
            "phase": "ready",
            "fault_type": settings.fault,
            "gpus": [{"uuid": device.uuid, "index": device.index} for device in selected],
            "observation_errors": dict(observation_errors),
        })
        _wait_for_start(start_file, setup_deadline, sleep, clock)

        baseline_snapshot = _capture_snapshot(
            smi, selected, "baseline", setup_deadline - clock(), observation_errors,
        )
        observations["baseline"] = baseline_snapshot.to_dict()
        baseline = None
        if settings.fault == "vram-pressure":
            try:
                baseline = _memory_by_uuid(baseline_snapshot, selected)
            except common.WorkerError as exc:
                _record_observation_error(observation_errors, "baseline", exc)
                raise
        if settings.fault == "vram-pressure":
            jobs = [
                Allocation(driver, device, requested, settings.reserve_bytes)
                for device, requested in zip(selected, requested_sizes)
            ]

            def observe(_elapsed, timeout_seconds):
                snapshot = _capture_snapshot(
                    smi, selected, "holding", timeout_seconds, observation_errors,
                )
                try:
                    records = _memory_samples(snapshot, selected)
                except common.WorkerError as exc:
                    _record_observation_error(observation_errors, "holding", exc)
                    return None
                observations["holding"] = snapshot.to_dict()
                return records
        else:
            driver.bind_compute()
            jobs = [
                ComputeLoad(driver, device, duty_cycle, clock)
                for device, duty_cycle in zip(selected, duty_cycles)
            ]

            def observe(elapsed, timeout_seconds):
                records = _compute_samples(jobs, elapsed)
                if records is not None:
                    snapshot = _capture_snapshot(
                        smi, selected, "holding", timeout_seconds, observation_errors,
                    )
                    if _snapshot_available(snapshot, selected, "gpu_utilization_percent"):
                        observations["holding"] = snapshot.to_dict()
                    else:
                        _record_observation_error(
                            observation_errors,
                            "holding",
                            "nvidia-smi cannot observe selected GPU utilization",
                        )
                return records
        for job in jobs:
            if clock() >= setup_deadline:
                raise common.WorkerError("GPU setup timed out")
            job.start()
        ready_stats = _await_ready(jobs, setup_deadline, clock)
        _emit(emit, {
            "phase": "started",
            "fault_type": settings.fault,
            "gpus": ready_stats,
            "observations": dict(observations),
            "observation_errors": dict(observation_errors),
        })
        started = clock()
        deadline = started + settings.duration
        if settings.fault == "compute-pressure":
            for job in jobs:
                job.start_load(deadline)
        _hold(
            jobs, settings.fault, started, deadline, observe, observations,
            observation_errors, emit, sleep, clock,
        )
        recovery_deadline = clock() + recovery_timeout
        _stop_and_join(jobs, recovery_deadline, clock)
        _check_errors(jobs, "during cleanup")
        errors = _cleanup_errors(jobs)
        if errors:
            raise common.WorkerError("; ".join(errors))
        after_release = _capture_snapshot(
            smi, selected, "after_release", recovery_deadline - clock(), observation_errors,
        )
        observations["after_release"] = after_release.to_dict()
        if settings.fault == "vram-pressure":
            try:
                final = _memory_by_uuid(after_release, selected)
            except common.WorkerError as exc:
                _record_observation_error(observation_errors, "after_release", exc)
                raise
            complete = _complete(jobs, selected, requested_sizes, baseline, final)
        else:
            records = [job.sample(settings.duration) for job in jobs]
            for record in records:
                if not record["batches_completed"]:
                    raise common.WorkerError(f"GPU {record['uuid']} completed no compute batches")
            complete = {"phase": "complete", "gpus": records}
        complete["fault_type"] = settings.fault
        complete["observations"] = dict(observations)
        complete["observation_errors"] = dict(observation_errors)
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
            "gpus": _error_gpu_stats(jobs),
            "observations": dict(observations),
            "observation_errors": dict(observation_errors),
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
        if os.environ.get("GPU_FAULT_TYPE") in LIMIT_FAULTS:
            Path(common.STOP_FILE).touch()
            return
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
