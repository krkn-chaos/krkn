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

"""Isolated tests for GPU worker parsing, discovery, and allocation lifetimes."""

import json
import os
import sys
import tempfile
import threading
import types
import unittest
from dataclasses import replace
from unittest import mock

from krkn_lib.gpu.models import Availability, GpuSnapshot, Measurement

from krkn.scenario_plugins.gpu.runtime import compute, cuda, devices, worker
from krkn.scenario_plugins.gpu.runtime.common import (
    CHUNK_BYTES, MIB, SMALL_ALLOCATION_BYTES, Device, WorkerError,
)
from krkn.scenario_plugins.gpu.runtime.parameters import compute_duty_cycle, csv_values, memory_bytes, validate_fault


UUID0 = "GPU-00000000-0000-0000-0000-000000000001"
UUID1 = "GPU-00000000-0000-0000-0000-000000000002"
TOTAL = 1024 * MIB
FREE = 512 * MIB


class FakeDriver:
    def __init__(self, device_uuids=(UUID0, UUID1), fail_at=None):
        self.device_uuids = device_uuids
        self.free_by_uuid = {uuid: FREE for uuid in device_uuids}
        self.local = threading.local()
        self.fail_at = fail_at
        self.alloc_calls = 0
        self.allocations = {}
        self.freed_bytes = 0
        self.destroyed = 0
        self.lock = threading.Lock()

    def devices(self):
        return [(index, index, uuid) for index, uuid in enumerate(self.device_uuids)]

    def create_context(self, device):
        self.local.uuid = device.uuid
        return (threading.get_ident(), device.uuid)

    def destroy_context(self, _context):
        self.destroyed += 1

    def memory_info(self):
        return self.free_by_uuid[self.local.uuid], TOTAL

    def alloc(self, size):
        with self.lock:
            self.alloc_calls += 1
            if self.alloc_calls == self.fail_at:
                raise WorkerError("mock CUDA allocation failure")
            uuid = self.local.uuid
            if size > self.free_by_uuid[uuid]:
                raise WorkerError("mock out of memory")
            self.free_by_uuid[uuid] -= size
            pointer = (uuid, self.alloc_calls)
            self.allocations[pointer] = size
            return pointer

    def free(self, pointer):
        uuid, _ = pointer
        size = self.allocations.pop(pointer)
        self.free_by_uuid[uuid] += size
        self.freed_bytes += size


class FakeSmi:
    def __init__(self, device_uuids=(UUID0, UUID1)):
        self.metadata = {
            uuid: (index, TOTAL, "Default")
            for index, uuid in enumerate(device_uuids)
        }
        self.free = {uuid: FREE for uuid in device_uuids}
        self.snapshot_calls = []

    def devices(self):
        return self.metadata

    def snapshot(self, fields, timeout_seconds=10.0):
        self.snapshot_calls.append((tuple(fields), timeout_seconds))
        measurements = []
        for uuid, values in self.metadata.items():
            field_values = {
                "memory_total_bytes": values[1],
                "memory_free_bytes": self.free[uuid],
                "memory_used_bytes": values[1] - self.free[uuid],
                "gpu_utilization_percent": 37.5,
            }
            for field in fields:
                measurements.append(Measurement(
                    device_uuid=uuid,
                    scope="physical_gpu",
                    field=field,
                    value=field_values[field],
                    unit="percent" if field == "gpu_utilization_percent" else "bytes",
                    value_type="float" if field == "gpu_utilization_percent" else "integer",
                    source="local:nvidia-smi",
                    observed_at="2026-01-01T00:00:00Z",
                    status=Availability.AVAILABLE,
                ))
        return GpuSnapshot(None, "2026-01-01T00:00:00Z", measurements)

def base_env(**changes):
    environ = {
        "GPU_FAULT_TYPE": "vram-pressure",
        "GPU_IDS": "all",
        "GPU_VRAM": "1Mi",
        "GPU_DURATION": "0.02",
        "GPU_SETUP_TIMEOUT": "1",
        "GPU_RECOVERY_TIMEOUT": "1",
        "GPU_MEMORY_RESERVE": "1Mi",
        "GPU_TARGET_PODS": "[]",
    }
    environ.update(changes)
    return environ


class ParameterTests(unittest.TestCase):
    def test_csv_and_memory_units(self):
        self.assertEqual(csv_values(" GPU-0, 1 "), ["GPU-0", "1"])
        with self.assertRaises(ValueError):
            csv_values("GPU-0,,1")
        self.assertEqual(memory_bytes("12.5%", 8 * MIB), MIB)
        self.assertEqual(memory_bytes("2Gi", 8 * (1 << 30)), 2 * (1 << 30))
        for value in ("0%", "101%", "10", "-1Mi", "NaN%"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                memory_bytes(value, TOTAL)
        self.assertEqual(validate_fault("vram-pressure"), "vram-pressure")
        with self.assertRaises(ValueError):
            validate_fault("power-limit")

    def test_compute_duty_cycle(self):
        self.assertEqual(compute_duty_cycle("20%"), 20)
        self.assertEqual(compute_duty_cycle(100), 100)
        for value in (None, True, 0, "101%", "20.5%", "1%%"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "GPU_COMPUTE_DUTY_CYCLE"):
                compute_duty_cycle(value)

    def test_selection_order_deduplication_and_target_restriction(self):
        candidates = [
            Device(0, 0, UUID0, TOTAL, "Default"),
            Device(1, 1, UUID1, TOTAL, "Default"),
            Device(2, 2, UUID0, TOTAL, "Default"),
        ]
        all_selected = devices.select_devices(candidates, "all", None)
        self.assertEqual([device.uuid for device in all_selected], [UUID0, UUID1])
        explicit = devices.select_devices(candidates, "1,0", None)
        self.assertEqual([device.uuid for device in explicit], [UUID1, UUID0])
        with self.assertRaisesRegex(WorkerError, "duplicate physical GPU"):
            devices.select_devices(candidates, "0," + UUID0, None)
        targets = devices.select_devices(candidates, "all", [UUID0 + "::0", UUID0 + "::1"])
        self.assertEqual([device.uuid for device in targets], [UUID0])
        with self.assertRaises(WorkerError):
            devices.select_devices(candidates, "1", [UUID0])
        with self.assertRaises(WorkerError):
            devices.select_devices(candidates, "all", ["MIG-GPU-00000000/1/2"])

    def test_targets_json_validation_and_podresources_filtering(self):
        targets = devices.parse_targets('[{"namespace":"ns","name":"pod"}]')
        self.assertEqual(targets, [("ns", "pod")])
        with self.assertRaises(WorkerError):
            devices.parse_targets("{}")
        pod = types.SimpleNamespace(
            namespace="ns", name="pod",
            containers=[types.SimpleNamespace(devices=[
                types.SimpleNamespace(resource_name="nvidia.com/gpu", device_ids=[UUID0]),
                types.SimpleNamespace(resource_name="nvidia.com/hostdev", device_ids=["nic-0"]),
            ])],
        )
        ignored = types.SimpleNamespace(namespace="other", name="pod", containers=pod.containers)
        response = types.SimpleNamespace(pod_resources=[ignored, pod])
        channel = types.SimpleNamespace(close=mock.Mock())
        grpc = types.SimpleNamespace(insecure_channel=mock.Mock(return_value=channel))
        pb2 = types.SimpleNamespace(ListPodResourcesRequest=lambda: object())

        class Stub:
            def __init__(self, _channel):
                pass

            def List(self, _request, timeout):
                self.timeout = timeout
                return response

        pb2_grpc = types.SimpleNamespace(PodResourcesListerStub=Stub)
        with mock.patch.dict(sys.modules, {"grpc": grpc, "podresources_pb2": pb2, "podresources_pb2_grpc": pb2_grpc}):
            self.assertEqual(devices.pod_resource_devices(targets, "/socket"), [UUID0])
        pod.containers[0].devices[0].resource_name = "example.com/accelerator"
        with mock.patch.dict(sys.modules, {"grpc": grpc, "podresources_pb2": pb2, "podresources_pb2_grpc": pb2_grpc}):
            self.assertEqual(
                devices.pod_resource_devices(targets, "/socket", resource_name="example.com/accelerator"),
                [UUID0],
            )
        pod.containers[0].devices[0].resource_name = "nvidia.com/gpu"
        self.assertTrue(channel.close.called)
        response.pod_resources = []
        with mock.patch.dict(sys.modules, {"grpc": grpc, "podresources_pb2": pb2, "podresources_pb2_grpc": pb2_grpc}):
            with self.assertRaisesRegex(WorkerError, "missing"):
                devices.pod_resource_devices(targets, "/socket")
        targets_two = targets + [("ns", "other-pod")]
        no_gpu_pod = types.SimpleNamespace(namespace="ns", name="other-pod", containers=[])
        response.pod_resources = [pod, no_gpu_pod]
        with mock.patch.dict(sys.modules, {"grpc": grpc, "podresources_pb2": pb2, "podresources_pb2_grpc": pb2_grpc}):
            with self.assertRaisesRegex(WorkerError, "no GPU device allocations"):
                devices.pod_resource_devices(targets_two, "/socket")
        dra_container = types.SimpleNamespace(
            devices=pod.containers[0].devices,
            dynamic_resources=[object()],
        )
        response.pod_resources = [
            types.SimpleNamespace(namespace="ns", name="pod", containers=[dra_container])
        ]
        with mock.patch.dict(sys.modules, {"grpc": grpc, "podresources_pb2": pb2, "podresources_pb2_grpc": pb2_grpc}):
            with self.assertRaisesRegex(WorkerError, "unresolved DRA resources"):
                devices.pod_resource_devices(targets, "/socket")


class CudaBindingTests(unittest.TestCase):
    class Function:
        def __init__(self, fn):
            self.fn = fn

        def __call__(self, *args):
            return self.fn(*args)

    def test_driver_api_binding_and_allocation(self):
        class Library:
            pass

        library = Library()
        library.cuInit = self.Function(lambda _flags: 0)
        library.cuDeviceGetCount = self.Function(lambda out: setattr(out._obj, "value", 1) or 0)
        library.cuDeviceGet = self.Function(lambda out, ordinal: setattr(out._obj, "value", ordinal) or 0)

        def set_uuid(out, _device):
            out._obj.bytes[:] = bytes.fromhex("00000000000000000000000000000001")
            return 0

        library.cuDeviceGetUuid_v2 = self.Function(set_uuid)
        library.cuCtxCreate_v2 = self.Function(lambda out, _flags, _device: setattr(out._obj, "value", 99) or 0)
        library.cuCtxDestroy_v2 = self.Function(lambda _context: 0)

        def memory_info(free, total):
            free._obj.value, total._obj.value = 1024, 2048
            return 0

        library.cuMemGetInfo_v2 = self.Function(memory_info)
        library.cuMemAlloc_v2 = self.Function(lambda out, _size: setattr(out._obj, "value", 1234) or 0)
        library.cuMemFree_v2 = self.Function(lambda _pointer: 0)
        driver = cuda.CudaDriver(library=library)
        devices = driver.devices()
        self.assertEqual(devices[0][2], UUID0)
        device = Device(0, 0, UUID0, TOTAL, "Default")
        context = driver.create_context(device)
        self.assertEqual(context.value, 99)
        self.assertEqual(driver.memory_info(), (1024, 2048))
        self.assertEqual(driver.alloc(64), 1234)
        driver.free(1234)
        driver.destroy_context(context)

        library.cuMemAlloc_v2 = self.Function(lambda _out, _size: 2)
        driver = cuda.CudaDriver(library=library)
        with self.assertRaisesRegex(WorkerError, "CUDA error 2"):
            driver.alloc(1)
    def test_missing_cuda_library_reports_failure(self):
        with mock.patch.object(cuda.ctypes.util, "find_library", return_value=None), \
                mock.patch.object(cuda.glob, "glob", return_value=[]), \
                mock.patch.object(cuda.ctypes, "CDLL", side_effect=OSError("missing")):
            with self.assertRaisesRegex(WorkerError, "cannot load CUDA driver library"):
                cuda.CudaDriver()



class NvidiaSmiTests(unittest.TestCase):
    def test_discovery_and_snapshot_delegate_with_driver_setup(self):
        xml = (
            "<nvidia_smi_log><gpu><uuid>{}</uuid><mig_mode>"
            "<current_mig>Disabled</current_mig></mig_mode>"
            "<gpu_virtualization_mode><virtualization_mode>None</virtualization_mode>"
            "</gpu_virtualization_mode></gpu></nvidia_smi_log>"
        ).format(UUID0)

        def run(args, **kwargs):
            self.assertEqual(kwargs["timeout"], 10.0)
            if args[1].startswith("--query-gpu=uuid,index"):
                result = f"{UUID0}, 0, 1024, Default\n"
            elif args[1:3] == ["-q", "-x"]:
                result = xml
            elif args[1].startswith("--query-compute-apps"):
                result = "123, python\n"
            else:
                raise AssertionError(args)
            return types.SimpleNamespace(returncode=0, stdout=result, stderr="")

        smi = devices.NvidiaSmi(executable="nvidia-smi", run=run)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(smi.devices()[UUID0][0], 0)
            snapshot = GpuSnapshot(None, "2026-01-01T00:00:00Z", [])
            with mock.patch(
                "krkn.scenario_plugins.gpu.runtime.devices.snapshot_local_gpus",
                return_value=snapshot,
            ) as local_snapshot:
                fields = ("gpu_utilization_percent",)
                self.assertIs(smi.snapshot(fields, timeout_seconds=4.0), snapshot)
            local_snapshot.assert_called_once_with(
                fields=fields, executable="nvidia-smi", run=run, timeout_seconds=4.0,
            )
            with mock.patch.object(smi, "_command", side_effect=[f"{UUID0}, 0, 1024, Default\n", xml.replace("Disabled", "Enabled")]):
                with self.assertRaisesRegex(WorkerError, "MIG is enabled"):
                    smi.devices()
            with mock.patch.object(smi, "_command", side_effect=[f"{UUID0}, 0, 1024, Default\n", xml.replace("None", "Host VGPU")]):
                with self.assertRaisesRegex(WorkerError, "virtualized GPU mode"):
                    smi.devices()
            with mock.patch.dict(os.environ, {"CUDA_MPS_PIPE_DIRECTORY": "/tmp/mps"}):
                with mock.patch.object(smi, "_command", side_effect=[f"{UUID0}, 0, 1024, Default\n", xml]):
                    with self.assertRaisesRegex(WorkerError, "CUDA MPS environment"):
                        smi.devices()


class ComputeLifecycleTests(unittest.TestCase):
    class Driver(FakeDriver):
        def __init__(self, fail_jit=False):
            super().__init__()
            self.fail_jit = fail_jit
            self.launched = []
            self.unloaded = []

        def bind_compute(self):
            pass

        def sm_count(self, _device):
            return 2

        def load_module(self, _ptx):
            if self.fail_jit:
                raise WorkerError("PTX JIT unavailable")
            return self.local.uuid

        def get_kernel(self, module, _name):
            return module

        def alloc(self, size):
            self.scratch = size
            return 1234

        def free(self, pointer):
            if pointer != 1234:
                raise AssertionError(pointer)
            self.freed_bytes += self.scratch

        def unload_module(self, module):
            self.unloaded.append(module)

        def run_compute(self, kernel, _grid, _block, _output, _iterations):
            self.launched.append(kernel)

    def test_targeted_compute_starts_after_barrier_and_observes_gpu_utilization(self):
        driver = self.Driver()
        smi = FakeSmi()
        lines = []
        env = base_env(
            GPU_FAULT_TYPE="compute-pressure", GPU_COMPUTE_DUTY_CYCLE="25%",
            GPU_VRAM="", GPU_DURATION="0.2",
            GPU_TARGET_PODS='[{"namespace":"ns","name":"pod"}]',
        )
        with tempfile.TemporaryDirectory() as directory:
            start_file = os.path.join(directory, "start")

            def emit(line):
                record = json.loads(line)
                lines.append(record)
                if record["phase"] == "ready":
                    self.assertEqual(driver.launched, [])
                    with open(start_file, "w", encoding="utf-8"):
                        pass

            result = worker.run_worker(
                env, driver=driver, smi=smi, pods_loader=lambda *_args, **_kwargs: [UUID1],
                emit=emit, start_file=start_file,
            )

        record, = result["gpus"]
        self.assertEqual(record["uuid"], UUID1)
        self.assertEqual(record["compute_duty_cycle"], 25)
        self.assertGreater(record["batches_completed"], 0)
        holding, = [event for event in lines if event["phase"] == "holding"]
        utilization, = [
            measurement for measurement in holding["observations"]["holding"]["measurements"]
            if measurement["field"] == "gpu_utilization_percent"
        ]
        self.assertEqual(utilization["value"], 37.5)
        self.assertEqual(set(driver.launched), {UUID1})
        self.assertEqual(driver.unloaded, [UUID1])
        self.assertEqual(driver.freed_bytes, driver.scratch)
        self.assertEqual(driver.destroyed, 1)
        self.assertLessEqual(len(smi.snapshot_calls), 3)

    def test_compute_monitor_failure_is_recorded_without_failing_fault(self):
        class FailingHoldingSmi(FakeSmi):
            calls = 0

            def snapshot(self, fields, timeout_seconds=10.0):
                self.calls += 1
                if self.calls == 2:
                    raise WorkerError("optional monitor failure")
                return super().snapshot(fields, timeout_seconds)

        driver = self.Driver()
        smi = FailingHoldingSmi()
        lines = []
        env = base_env(
            GPU_FAULT_TYPE="compute-pressure", GPU_COMPUTE_DUTY_CYCLE="25%",
            GPU_VRAM="", GPU_DURATION="0.2",
        )
        with tempfile.TemporaryDirectory() as directory:
            start_file = os.path.join(directory, "start")

            def emit(line):
                record = json.loads(line)
                lines.append(record)
                if record["phase"] == "ready":
                    with open(start_file, "w", encoding="utf-8"):
                        pass

            result = worker.run_worker(env, driver=driver, smi=smi, emit=emit, start_file=start_file)
        self.assertEqual(result["phase"], "complete")
        holding, = [event for event in lines if event["phase"] == "holding"]
        self.assertEqual(
            holding["observations"]["holding"]["errors"],
            ["GPU observation failed"],
        )

    def test_compute_duty_cycles_follow_gpu_selection_order(self):
        for gpu_ids, duty_cycles, expected in (
            ("1,0", "20,30", [(UUID0, 20), (UUID1, 30)]),
            ("all", "20%,30%", [(UUID1, 20), (UUID0, 30)]),
            ("all", "25%", [(UUID1, 25), (UUID0, 25)]),
        ):
            with self.subTest(gpu_ids=gpu_ids, duty_cycles=duty_cycles), \
                    tempfile.TemporaryDirectory() as directory:
                start_file = os.path.join(directory, "start")
                smi = FakeSmi()
                smi.metadata = {UUID0: (1, TOTAL, "Default"), UUID1: (0, TOTAL, "Default")}

                def emit(line):
                    if json.loads(line)["phase"] == "ready":
                        with open(start_file, "w", encoding="utf-8"):
                            pass

                result = worker.run_worker(
                    base_env(GPU_FAULT_TYPE="compute-pressure", GPU_IDS=gpu_ids,
                             GPU_COMPUTE_DUTY_CYCLE=duty_cycles, GPU_DURATION="0.2"),
                    driver=self.Driver(), smi=smi, emit=emit, start_file=start_file,
                )
            self.assertEqual([(gpu["uuid"], gpu["compute_duty_cycle"]) for gpu in result["gpus"]], expected)

    def test_compute_duty_cycle_count_is_checked_after_pod_targeting(self):
        driver = self.Driver()
        with self.assertRaisesRegex(WorkerError, "GPU_COMPUTE_DUTY_CYCLE has 2 values for 1 selected GPUs"):
            worker.run_worker(
                base_env(GPU_FAULT_TYPE="compute-pressure", GPU_COMPUTE_DUTY_CYCLE="20%,30%",
                         GPU_TARGET_PODS='[{"namespace":"ns","name":"pod"}]'),
                driver=driver, smi=FakeSmi(), pods_loader=lambda *_args, **_kwargs: [UUID1],
            )
        self.assertEqual(driver.launched, [])

    def test_jit_failure_destroys_context_without_advertising_readiness(self):
        driver = self.Driver(fail_jit=True)
        records = []
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(WorkerError, "PTX JIT unavailable"):
                worker.run_worker(
                    base_env(GPU_FAULT_TYPE="compute-pressure", GPU_COMPUTE_DUTY_CYCLE="20", GPU_IDS="0"),
                    driver=driver, smi=FakeSmi(), emit=lambda line: records.append(json.loads(line)),
                    start_file=os.path.join(directory, "start"),
                )
        self.assertEqual([record["phase"] for record in records], ["error"])
        self.assertEqual(driver.launched, [])
        self.assertEqual(driver.destroyed, 1)

    def test_batch_pacing_stops_at_deadline_without_catch_up(self):
        driver = self.Driver()
        clock = iter([0.0, 0.012, 0.048, 0.06, 0.07])
        load = compute.ComputeLoad(driver, Device(0, 0, UUID0, TOTAL, "Default"), 25, lambda: next(clock))
        load._deadline = 0.07
        with mock.patch.object(load._stop_event, "wait") as wait:
            load._run_batches(UUID0, 8, 1234)
        self.assertEqual(driver.launched, [UUID0, UUID0])
        rest_times = [call.args[0] for call in wait.call_args_list]
        self.assertEqual(len(rest_times), 2)
        self.assertAlmostEqual(rest_times[0], 0.036)
        self.assertAlmostEqual(rest_times[1], 0.01)


class WorkerLifecycleTests(unittest.TestCase):
    def _run(self, *, env=None, target_ids=None, fail_at=None, start=True):
        driver = FakeDriver(device_uuids=(UUID0,), fail_at=fail_at)
        smi = FakeSmi()
        lines = []
        with tempfile.TemporaryDirectory() as directory:
            start_file = os.path.join(directory, "start")

            def emit(line):
                lines.append(json.loads(line))
                if start and lines[-1]["phase"] == "ready":
                    with open(start_file, "w", encoding="utf-8"):
                        pass

            arguments = {
                "environ": base_env(**(env or {})),
                "driver": driver,
                "smi": smi,
                "pods_loader": lambda _targets, **_kwargs: target_ids,
                "emit": emit,
                "start_file": start_file,
            }
            if fail_at:
                with self.assertRaises(WorkerError):
                    worker.run_worker(**arguments)
                return None, lines, driver
            result = worker.run_worker(**arguments)
            return result, lines, driver

    def test_ready_hold_complete_and_partial_target_release(self):
        result, lines, driver = self._run(
            env={"GPU_TARGET_PODS": '[{"namespace":"ns","name":"pod"}]'},
            target_ids=[UUID0 + "::0", UUID0 + "::1"],
        )
        self.assertEqual(result["phase"], "complete")
        self.assertEqual(set(lines[0]["observations"]), {"baseline"})
        self.assertEqual(set(lines[1]["observations"]), {"holding"})
        self.assertEqual(set(lines[-1]["observations"]), {"baseline", "holding", "after_release"})
        for event in (lines[0], lines[1], lines[-1]):
            for snapshot in event["observations"].values():
                self.assertNotIn(UUID1, {
                    measurement["device_uuid"] for measurement in snapshot["measurements"]
                })
        self.assertEqual(len(lines[0]["gpus"]), 1)
        self.assertEqual(lines[0]["gpus"][0]["actual_bytes"], MIB)
        self.assertEqual(lines[-1]["gpus"][0]["small_allocation_bytes"], MIB)
        self.assertEqual(driver.freed_bytes, MIB + SMALL_ALLOCATION_BYTES)

    def test_partial_allocation_failure_cancels_and_frees_prior_chunks(self):
        _result, lines, driver = self._run(env={"GPU_VRAM": "65Mi"}, fail_at=2)
        self.assertEqual(lines[-1]["phase"], "error")
        self.assertEqual(lines[-1]["cleanup"][UUID0]["freed_bytes"], CHUNK_BYTES)
        self.assertEqual(driver.destroyed, 1)

    def test_setup_timeout_cleans_allocations(self):
        driver = FakeDriver(device_uuids=(UUID0,))
        lines = []
        clock_offset = [0.0]

        def clock():
            return worker.time.monotonic() + clock_offset[0]

        def emit(line):
            record = json.loads(line)
            lines.append(record)
            if record["phase"] == "ready":
                clock_offset[0] += 60.0

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(WorkerError, "common GPU start barrier timed out"):
                worker.run_worker(
                    base_env(GPU_SETUP_TIMEOUT="30"), driver=driver,
                    smi=FakeSmi(device_uuids=(UUID0,)), emit=emit,
                    start_file=os.path.join(directory, "start"), clock=clock,
                )
        self.assertEqual(driver.free_by_uuid[UUID0], FREE)
        self.assertEqual(lines[-1]["cleanup"][UUID0]["freed_bytes"], MIB)

    def test_vram_baseline_requires_all_memory_measurements(self):
        class MissingFreeSmi(FakeSmi):
            calls = 0

            def snapshot(self, fields, timeout_seconds=10.0):
                snapshot = super().snapshot(fields, timeout_seconds)
                self.calls += 1
                if self.calls == 1:
                    return replace(snapshot, measurements=[
                        measurement for measurement in snapshot.measurements
                        if measurement.field != "memory_free_bytes"
                    ])
                return snapshot

        lines = []
        with tempfile.TemporaryDirectory() as directory:
            start_file = os.path.join(directory, "start")

            def emit(line):
                lines.append(json.loads(line))

            with self.assertRaisesRegex(WorkerError, "cannot observe selected GPU"):
                worker.run_worker(
                    base_env(), driver=FakeDriver(device_uuids=(UUID0,)),
                    smi=MissingFreeSmi(), emit=emit, start_file=start_file,
                )
        self.assertEqual(lines[-1]["phase"], "error")
        self.assertEqual(set(lines[-1]["observations"]), {"baseline"})

    def test_post_release_memory_delta_is_observed_with_tolerance(self):
        class DriftingSmi(FakeSmi):
            pressure_seen = False

            def snapshot(self, fields, timeout_seconds=10.0):
                result = super().snapshot(fields, timeout_seconds)
                if self.pressure_seen:
                    result = replace(result, measurements=[
                        replace(
                            measurement,
                            value=measurement.value - 100 * MIB
                            if measurement.field == "memory_free_bytes"
                            else measurement.value,
                        )
                        for measurement in result.measurements
                    ])
                return result

        driver = FakeDriver(device_uuids=(UUID0,))
        lines = []
        smi = DriftingSmi(device_uuids=(UUID0,))
        with tempfile.TemporaryDirectory() as directory:
            start_file = os.path.join(directory, "start")

            def emit(line):
                record = json.loads(line)
                lines.append(record)
                if record["phase"] == "ready":
                    with open(start_file, "w", encoding="utf-8"):
                        pass
                if record["phase"] == "holding":
                    smi.pressure_seen = True

            result = worker.run_worker(
                base_env(), driver=driver, smi=smi,
                emit=emit, start_file=start_file,
            )
        self.assertEqual(driver.free_by_uuid[UUID0], FREE)
        self.assertEqual(result["phase"], "complete")
        self.assertFalse(result["gpus"][0]["free_delta_within_tolerance"])
        self.assertEqual(lines[-1]["phase"], "complete")

    def test_invalid_fault_fails_explicitly_before_cuda(self):
        lines = []
        with self.assertRaisesRegex(WorkerError, "unsupported GPU_FAULT_TYPE"):
            worker.run_worker(base_env(GPU_FAULT_TYPE="clock-limit"), emit=lines.append)
        self.assertEqual(json.loads(lines[-1])["phase"], "error")

    def test_memory_csv_must_match_selected_gpu_count(self):
        driver = FakeDriver()
        smi = FakeSmi()
        lines = []
        with self.assertRaisesRegex(WorkerError, "GPU_VRAM has 2 values for 1 selected GPUs"):
            worker.run_worker(
                base_env(GPU_VRAM="1Mi,2Mi", GPU_IDS="0"), driver=driver,
                smi=smi, emit=lines.append,
            )
        self.assertEqual(json.loads(lines[-1])["phase"], "error")

    def test_unsupported_compute_mode_and_percent_reserve_fail_before_allocation(self):
        driver = FakeDriver(device_uuids=(UUID0,))
        smi = FakeSmi(device_uuids=(UUID0,))
        smi.metadata[UUID0] = (*smi.metadata[UUID0][:2], "Exclusive_Process")
        lines = []
        with self.assertRaisesRegex(WorkerError, "unsupported compute mode"):
            worker.run_worker(base_env(), driver=driver, smi=smi, emit=lines.append)
        self.assertEqual(driver.alloc_calls, 0)
        self.assertEqual(json.loads(lines[-1])["phase"], "error")

        lines.clear()
        with self.assertRaisesRegex(WorkerError, "explicit binary unit"):
            worker.run_worker(base_env(GPU_MEMORY_RESERVE="10%"), emit=lines.append)
        self.assertEqual(json.loads(lines[-1])["phase"], "error")

    def _run_failing_driver(self, driver):
        records = []
        with tempfile.TemporaryDirectory() as directory:
            start_file = os.path.join(directory, "start")

            def emit(line):
                record = json.loads(line)
                records.append(record)
                if record["phase"] == "ready":
                    with open(start_file, "w"):
                        pass

            with self.assertRaises(WorkerError):
                worker.run_worker(
                    base_env(GPU_RECOVERY_TIMEOUT="5"), driver=driver,
                    smi=FakeSmi(device_uuids=driver.device_uuids),
                    emit=emit, start_file=start_file,
                )
        self.assertEqual(records[-1]["phase"], "error")
        return records[-1]

    def test_one_gpu_allocation_failure_releases_other_gpu(self):
        driver = FakeDriver(fail_at=2)
        result = self._run_failing_driver(driver)
        self.assertEqual(driver.allocations, {})
        self.assertEqual(driver.free_by_uuid, {UUID0: FREE, UUID1: FREE})
        self.assertTrue(result["cleanup"])

    def test_cleanup_failure_is_not_reported_as_success(self):
        class FailingFreeDriver(FakeDriver):
            def free(self, pointer):
                super().free(pointer)
                raise WorkerError("CUDA free failed")

        result = self._run_failing_driver(FailingFreeDriver(device_uuids=(UUID0,)))
        self.assertTrue(any(
            "CUDA free failed" in error
            for cleanup in result["cleanup"].values()
            for error in cleanup["cleanup_errors"]
        ))




if __name__ == "__main__":
    unittest.main()


