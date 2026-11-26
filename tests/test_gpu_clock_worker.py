# Copyright 2026 The Krkn Authors
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from krkn_lib.gpu.models import Availability, GpuSnapshot, Measurement

from krkn.scenario_plugins.gpu.runtime import worker
from tests.test_gpu_worker import FakeSmi, UUID0, UUID1, base_env


class ClockWorkerTests(unittest.TestCase):
    def setUp(self):
        self.current = {UUID0: 2040, UUID1: 1905}
        self.original = self.current.copy()
        self.supported = {UUID0: [1395, 1410, 1500, 1800], UUID1: [1380, 1425, 1500, 1800]}
        self.commands = []
        self.events = []
        self.fail = None
        self.now = 0.0
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.start = Path(temp.name) / "start"
        self.stop = Path(temp.name) / "start-stop"

    def command(self, op, uuid, timeout, target=None):
        self.commands.append((op, uuid, target))
        if op == "inspect":
            return self.original[uuid], self.supported[uuid]
        if op == "set":
            self.current[uuid] = target
        if (op, uuid) == self.fail:
            raise worker.common.WorkerError(f"{op} failed on {uuid}")
        if op == "reset":
            self.current[uuid] = self.original[uuid]

    def snapshot(self, fields, device_uuids, timeout_seconds):
        return GpuSnapshot(None, "2026-01-01T00:00:00Z", [
            Measurement(
                device_uuid=uuid, scope="physical_gpu", field="sm_clock_mhz",
                value=self.current[uuid], unit="MHz", value_type="int", source="test",
                status=Availability.AVAILABLE, observed_at="2026-01-01T00:00:00Z",
            ) for uuid in device_uuids
        ])

    def run_fault(self, mhz, ids="all", cancel=False):
        def emit(line):
            event = json.loads(line)
            self.events.append(event)
            if event["phase"] == "ready":
                self.start.touch()
            if cancel and event["phase"] == "holding":
                self.stop.touch()

        def sleep(seconds):
            self.now += seconds

        smi = FakeSmi()
        smi.snapshot = self.snapshot
        with (
            mock.patch.object(worker, "LimitControl", return_value=mock.Mock(call=self.command)),
            mock.patch.object(worker.devices, "require_exclusive_gpus"),
        ):
            return worker.run_worker(
                base_env(GPU_FAULT_TYPE="clock-limit", GPU_CLOCK_MHZ=mhz, GPU_IDS=ids),
                smi=smi, emit=emit, sleep=sleep, clock=lambda: self.now, start_file=self.start,
            )

    def test_explicit_order_and_all_broadcast(self):
        for ids, mhz, order in (
            ("1,0", "1800,1500", [(UUID1, 1800), (UUID0, 1500)]),
            ("all", "1800", [(UUID0, 1800), (UUID1, 1800)]),
        ):
            with self.subTest(ids=ids):
                self.commands.clear()
                result = self.run_fault(mhz, ids)
                self.assertEqual([(uuid, t) for op, uuid, t in self.commands if op == "set"], order)
                self.assertEqual(
                    [(row["uuid"], row["requested_sm_clock_mhz"], row["max_sm_clock_mhz"])
                     for row in result["gpus"]],
                    [(uuid, target, self.original[uuid]) for uuid, target in order],
                )
                self.assertEqual(self.current, self.original)
                self.assertTrue(result["restoration_safe"])
                self.assertEqual(result["device_restorations"][UUID1]["status"], "reset_acknowledged")

    def test_broadcast_ceiling_resolves_and_is_observed_per_gpu(self):
        result = self.run_fault("1400")
        self.assertEqual([(uuid, target) for op, uuid, target in self.commands if op == "set"],
                         [(UUID0, 1395), (UUID1, 1380)])
        self.assertEqual(
            [(row["requested_sm_clock_mhz"], row["applied_sm_clock_mhz"], row["clock_target_observed"])
             for row in result["gpus"]],
            [(1400, 1395, True), (1400, 1380, True)],
        )
        self.assertEqual(self.current, self.original)

    def test_below_second_gpu_minimum_rejects_all_writes(self):
        with self.assertRaisesRegex(worker.common.WorkerError, "no supported SM clock at or below 1379 MHz"):
            self.run_fault("1400,1379")
        self.assertEqual(self.commands, [("inspect", UUID0, None), ("inspect", UUID1, None)])
        self.assertTrue(self.events[-1]["restoration_safe"])

    def test_non_positive_ceilings_are_rejected(self):
        for mhz in ("0", "-1", "1800,0", "1800,-1"):
            with self.subTest(mhz=mhz):
                with self.assertRaisesRegex(worker.common.WorkerError, "requires positive whole MHz"):
                    self.run_fault(mhz)
                self.assertEqual(self.commands, [])

    def test_above_max_on_second_gpu_rejects_all_writes(self):
        with self.assertRaisesRegex(worker.common.WorkerError, "exceeds maximum 1905"):
            self.run_fault("1800,2000")
        self.assertEqual(self.current, self.original)
        self.assertTrue(all(op == "inspect" for op, _, _ in self.commands))
        self.assertTrue(self.events[-1]["restoration_safe"])

    def test_partial_apply_failure_resets_both_attempted_devices(self):
        self.fail = ("set", UUID1)
        with self.assertRaisesRegex(worker.common.WorkerError, "set failed"):
            self.run_fault("1800")
        self.assertEqual(self.current, self.original)
        self.assertEqual([uuid for op, uuid, _ in self.commands if op == "reset"], [UUID0, UUID1])
        first, second = self.events[-1]["gpus"]
        self.assertEqual(first["applied_sm_clock_mhz"], 1800)
        self.assertNotIn("applied_sm_clock_mhz", second)

    def test_failed_reset_is_reported_and_other_gpu_is_restored(self):
        self.fail = ("reset", UUID0)
        with self.assertRaisesRegex(worker.common.WorkerError, "reset failed"):
            self.run_fault("1800")
        self.assertEqual([uuid for op, uuid, _ in self.commands if op == "reset"], [UUID0, UUID1])
        self.assertFalse(self.events[-1]["restoration_safe"])
        self.assertEqual(self.events[-1]["device_restorations"], {
            UUID0: {"status": "unverified", "reason": f"reset failed on {UUID0}"},
            UUID1: {"status": "reset_acknowledged"},
        })
        self.assertEqual(self.current, {UUID0: 1800, UUID1: self.original[UUID1]})

    def test_stop_during_hold_restores_the_clock(self):
        with self.assertRaisesRegex(worker.common.WorkerError, "cancelled"):
            self.run_fault("1800", cancel=True)
        self.assertEqual(self.current, self.original)
        self.assertTrue(self.events[-1]["restoration_safe"])
