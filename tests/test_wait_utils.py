import unittest

from krkn.utils.wait import wait_or_fail


class TestWaitOrFail(unittest.TestCase):
    def test_reached_state_passes(self):
        wait_or_fail(True, "instance i-1 to be running")

    def test_timed_out_wait_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            wait_or_fail(False, "instance i-1 to be running")
        self.assertIn("instance i-1 to be running", str(ctx.exception))

    def test_missing_result_raises(self):
        # A wait that returns nothing has not reported reaching the state.
        with self.assertRaises(RuntimeError):
            wait_or_fail(None, "instance i-1 to be running")

    def test_truthy_value_that_is_not_true_raises(self):
        # Only the literal True counts as reached, so a truthy value can't pass.
        with self.assertRaises(RuntimeError):
            wait_or_fail("RUNNING", "instance i-1 to be running")


if __name__ == "__main__":
    unittest.main()
