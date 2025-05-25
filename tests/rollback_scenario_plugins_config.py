import os
import time

TIMESTAMP = int(time.time())
TEST_ROLLBACK_SCENARIO_PLUGIN_DIRECTORY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_output_rollback"
)
TEST_ROLLBACK_VERSIONS_OUTPUT = os.path.join(
    TEST_ROLLBACK_SCENARIO_PLUGIN_DIRECTORY, f"rollback_versions_{TIMESTAMP}"
)
