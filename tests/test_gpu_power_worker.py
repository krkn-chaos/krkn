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


class PowerWorkerTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.start = directory / "start"
        self.stop = directory / "start-stop"
        self.original = {UUID0: 71250, UUID1: 67500}
        self.current = self.original.copy()
        self.enforced = self.original.copy()
        self.events = []
        self.writes = []
        self.enforced_at = {}
        self.started_at = None
        self.fail_apply = None
        self.fail_restore = None
        self.now = 0.0
        self.enterContext(mock.patch.object(worker, "LimitControl", return_value=mock.Mock(call=self.command)))
        self.enterContext(mock.patch.object(worker.devices, "require_exclusive_gpus"))

    def command(self, op, uuid, timeout, target=None):
        if op == "inspect":
            return 40000, 72000, self.current[uuid], self.enforced[uuid]
        if op == "read":
            configured = self.current[uuid]
            enforced = configured if self.now >= self.enforced_at.get(uuid, 0) else self.enforced[uuid]
            return configured, enforced
        self.writes.append((op, uuid, target))
        if op == "set":
            self.current[uuid] = target
            if uuid == self.fail_apply:
                raise worker.common.WorkerError("apply timed out")
            return None
        if op == "restore":
            if uuid != self.fail_restore:
                self.current[uuid] = target
            return self.current[uuid]
        raise AssertionError(op)

    def snapshot(self, fields, device_uuids, timeout_seconds):
        return GpuSnapshot(None, "2026-01-01T00:00:00Z", [
            Measurement(
                device_uuid=UUID0, scope="physical_gpu", field="sw_power_cap_active",
                value=False, unit=None, value_type="bool", source="test",
                status=Availability.AVAILABLE, observed_at="2026-01-01T00:00:00Z",
            )
        ])

    def run_fault(self, watts, ids="all", cancel=False, setup_timeout="1"):
        def emit(line):
            event = json.loads(line)
            self.events.append(event)
            if event["phase"] == "ready":
                self.start.touch()
            if event["phase"] == "started":
                self.started_at = self.now
            if cancel and event["phase"] == "holding":
                self.stop.touch()

        def sleep(seconds):
            self.now += seconds

        smi = FakeSmi()
        smi.snapshot = self.snapshot
        return worker.run_worker(
            base_env(GPU_FAULT_TYPE="power-limit", GPU_POWER_LIMIT_W=watts, GPU_IDS=ids,
                     GPU_SETUP_TIMEOUT=setup_timeout),
            smi=smi, emit=emit, sleep=sleep, clock=lambda: self.now, start_file=self.start,
        )

    def test_targets_follow_selection_order_and_restore_exact_milliwatts(self):
        for ids, watts, order in (
            ("1,0", "55,65", [(UUID1, 55000), (UUID0, 65000)]),
            ("all", "65,55", [(UUID0, 65000), (UUID1, 55000)]),
            ("all", "60", [(UUID0, 60000), (UUID1, 60000)]),
        ):
            with self.subTest(ids=ids, watts=watts):
                self.writes.clear()
                result = self.run_fault(watts, ids)
                self.assertEqual(self.writes, [
                    *(("set", uuid, cap) for uuid, cap in order),
                    *(("restore", uuid, self.original[uuid]) for uuid, _ in order),
                ])
                self.assertEqual(self.current, self.original)
                records = {row["uuid"]: row for row in result["gpus"]}
                self.assertIs(records[UUID0]["power_throttle_observed"], False)
                self.assertNotIn("power_throttle_observed", records[UUID1])
                self.assertTrue(result["restoration_safe"])

    def test_invalid_limit_on_last_gpu_does_not_change_first_gpu(self):
        self.enforced[UUID1] = 60000
        for watts, reason in (("65,39", "outside"), ("65,60", "must lower")):
            with self.subTest(watts=watts), self.assertRaisesRegex(worker.common.WorkerError, reason):
                self.run_fault(watts)
            self.assertEqual(self.writes, [])

    def test_waits_for_enforcement_before_starting_without_rewriting_cap(self):
        self.enforced_at[UUID1] = 1.4
        result = self.run_fault("60", UUID1, setup_timeout="10")
        self.assertGreaterEqual(self.started_at, 1.4)
        self.assertEqual(result["gpus"][0]["enforced_power_limit_w"], 60)
        self.assertEqual(self.writes, [("set", UUID1, 60000), ("restore", UUID1, self.original[UUID1])])

    def test_mismatched_enforced_cap_times_out_and_restores(self):
        self.enforced_at[UUID1] = float("inf")
        for setup, expected_deadline in (("1", 1), ("120", 5)):
            with self.subTest(setup_timeout=setup):
                self.now = 0.0
                self.writes.clear()
                with self.assertRaisesRegex(
                    worker.common.WorkerError,
                    r"60 W power cap not verified \(verification timed out; last NVML readback: configured 60 W, enforced 67.5 W\)",
                ):
                    self.run_fault("60", UUID1, setup_timeout=setup)
                self.assertAlmostEqual(self.now, expected_deadline)
                self.assertIsNone(self.started_at)
                self.assertEqual(self.events[-1]["gpus"][0]["enforced_power_limit_w"], 67.5)
                self.assertEqual(self.writes, [("set", UUID1, 60000), ("restore", UUID1, self.original[UUID1])])
                self.assertEqual(self.current, self.original)
                self.assertTrue(self.events[-1]["restoration_safe"])

    def test_partial_apply_and_cancellation_restore_attempted_gpus(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                self.fail_apply = None if cancelled else UUID1
                reason = "cancelled" if cancelled else "apply timed out"
                with self.assertRaisesRegex(worker.common.WorkerError, reason):
                    self.run_fault("60", cancel=cancelled)
                self.assertEqual(self.current, self.original)
                self.assertTrue(self.events[-1]["restoration_safe"])

    def test_failed_restore_is_reported_without_skipping_other_gpu(self):
        self.fail_restore = UUID0
        with self.assertRaisesRegex(worker.common.WorkerError, "expected 71250 mW after restore"):
            self.run_fault("60")
        self.assertFalse(self.events[-1]["restoration_safe"])
        self.assertEqual(self.events[-1]["device_restorations"][UUID1]["status"], "verified")
        self.assertEqual(self.events[-1]["device_restorations"][UUID0]["status"], "unverified")
        self.assertEqual(self.current, {UUID0: 60000, UUID1: self.original[UUID1]})
