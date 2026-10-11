import queue
import unittest

from krkn.telemetry_helpers import collect_health_check_telemetry


class TestCollectHealthCheckTelemetry(unittest.TestCase):
    def test_collects_all_queue_entries(self):
        telemetry_queue = queue.Queue()
        first_record = {"url": "https://first.example", "phase": "pre"}
        second_record = {"url": "https://second.example", "phase": "pre"}
        telemetry_queue.put(first_record)
        telemetry_queue.put(second_record)

        health_checks, object_state_checks = collect_health_check_telemetry(telemetry_queue)

        self.assertEqual(health_checks, [first_record, second_record])
        self.assertEqual(object_state_checks, [])
        self.assertTrue(telemetry_queue.empty())


if __name__ == "__main__":
    unittest.main()
