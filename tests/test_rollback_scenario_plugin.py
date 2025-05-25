import pytest
import logging
import os
from unittest import mock
import sys

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.utils import SafeLogger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # Adjust path to include krkn

from tests.rollback_scenario_plugins_config import TEST_ROLLBACK_VERSIONS_OUTPUT


class TestRollbackScenarioPlugin:
    def validate_rollback_directory(self, directory: str, versions: int = 1):
        """
        Validate that the rollback directory exists and contains version files.
        """
        assert os.path.exists(directory), f"Rollback directory {directory} does not exist."
        version_files = os.listdir(directory)
        assert len(version_files) == versions, (
            f"Expected {versions} version files, found {len(version_files)} in {directory}."
        )
        for version_file in version_files:
            assert version_file.startswith("rollback_"), (
                f"Version file {version_file} does not start with 'rollback_'"
            )
            assert version_file.endswith(".py"), f"Version file {version_file} does not end with '.py'"

    @pytest.fixture(autouse=True)
    def setup_logging(self):
        os.makedirs(TEST_ROLLBACK_VERSIONS_OUTPUT, exist_ok=True)
        # setup logging
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(os.path.join(TEST_ROLLBACK_VERSIONS_OUTPUT, "test_rollback.log")),
                logging.StreamHandler(),
            ],
        )

    @pytest.fixture(scope="module")
    def kubeconfig_path(self):
        # Provide the path to the kubeconfig file for testing
        return os.getenv("KUBECONFIG", "/path/to/your/kubeconfig")

    @pytest.fixture(scope="module")
    def safe_logger(self):
        os.makedirs(TEST_ROLLBACK_VERSIONS_OUTPUT, exist_ok=True)
        with open(os.path.join(TEST_ROLLBACK_VERSIONS_OUTPUT, "telemetry.log"), "w") as f:
            pass  # Create the file if it doesn't exist
        yield SafeLogger(filename=os.path.join(TEST_ROLLBACK_VERSIONS_OUTPUT, "telemetry.log"))

    @pytest.fixture(scope="module")
    def kubecli(self, kubeconfig_path):
        yield KrknKubernetes(kubeconfig_path=kubeconfig_path)

    @pytest.fixture(scope="module")
    def lib_openshift(self, kubeconfig_path):
        yield KrknOpenshift(kubeconfig_path=kubeconfig_path)

    @pytest.fixture(scope="module")
    def lib_telemetry(self, lib_openshift, safe_logger):
        yield KrknTelemetryOpenshift(
            safe_logger=safe_logger,
            lib_openshift=lib_openshift,
        )

    @pytest.fixture(scope="module")
    def scenario_telemetry(self):
        yield ScenarioTelemetry()

    def test_simple_rollback_scenario_plugin(self, lib_telemetry, scenario_telemetry):
        from tests.rollback_scenario_plugins.simple import SimpleRollbackScenarioPlugin

        mock_rollback_scenario_plugin = SimpleRollbackScenarioPlugin()
        mock_rollback_scenario_plugin.run(
            "test_run_uuid",
            scenario="test_scenario",
            krkn_config={"key1": "value", "key2": False, "key3": 123, "key4": ["value1", "value2", "value3"]},
            lib_telemetry=lib_telemetry,
            scenario_telemetry=scenario_telemetry,
        )

        self.validate_rollback_directory(
            f"{TEST_ROLLBACK_VERSIONS_OUTPUT}/simple",
        )

    def test_krkn_args_rollback_scenario_plugin(self, lib_telemetry, scenario_telemetry):
        from tests.rollback_scenario_plugins.krkn_args import krknArgsRollbackScenarioPlugin

        mock_rollback_scenario_plugin = krknArgsRollbackScenarioPlugin()
        mock_rollback_scenario_plugin.run(
            "test_run_uuid",
            scenario="test_scenario",
            krkn_config={"key1": "value", "key2": False, "key3": 123, "key4": ["value1", "value2", "value3"]},
            lib_telemetry=lib_telemetry,
            scenario_telemetry=scenario_telemetry,
        )

        self.validate_rollback_directory(
            f"{TEST_ROLLBACK_VERSIONS_OUTPUT}/krkn_args",
        )

    def test_multi_call_rollback_scenario_plugin(self, lib_telemetry, scenario_telemetry):
        from tests.rollback_scenario_plugins.multi_call import MultiCallRollbackScenarioPlugin

        mock_rollback_scenario_plugin = MultiCallRollbackScenarioPlugin()
        mock_rollback_scenario_plugin.run(
            "test_run_uuid",
            scenario="test_scenario",
            krkn_config={"key1": "value", "key2": False, "key3": 123, "key4": ["value1", "value2", "value3"]},
            lib_telemetry=lib_telemetry,
            scenario_telemetry=scenario_telemetry,
        )

        # should generate 3 version files in the rollback directory
        self.validate_rollback_directory(f"{TEST_ROLLBACK_VERSIONS_OUTPUT}/multi_call", 3)

    def test_parallel_call_rollback_scenario_plugin(self, lib_telemetry, scenario_telemetry):
        from tests.rollback_scenario_plugins.parallel_call import ParallelCallRollbackScenarioPlugin

        mock_rollback_scenario_plugin = ParallelCallRollbackScenarioPlugin()
        mock_rollback_scenario_plugin.run(
            "test_run_uuid",
            scenario="test_scenario",
            krkn_config={"key1": "value", "key2": False, "key3": 123, "key4": ["value1", "value2", "value3"]},
            lib_telemetry=lib_telemetry,
            scenario_telemetry=scenario_telemetry,
        )

        # should generate 4 version files in the rollback directory
        self.validate_rollback_directory(f"{TEST_ROLLBACK_VERSIONS_OUTPUT}/parallel_call", 4)
