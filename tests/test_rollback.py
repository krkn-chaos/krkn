import pytest
import logging
import os
import sys
import uuid
import subprocess

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.utils import SafeLogger
from krkn.rollback.config import RollbackConfig

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # Adjust path to include krkn
TEST_LOGS_DIR = "/tmp/krkn_test_rollback_logs_directory"
TEST_VERSIONS_DIR = "/tmp/krkn_test_rollback_versions_directory"


class TestRollbackScenarioPlugin:
    def validate_rollback_directory(
        self, run_uuid: str, scenario: str, versions: int = 1
    ) -> list[str]:
        """
        Validate that the rollback directory exists and contains version files.

        :param run_uuid: The UUID for current run, used to identify the rollback context directory.
        :param scenario: The name of the scenario to validate.
        :param versions: The expected number of version files.
        :return: List of version files in full path.
        """
        rollback_context_directories = [
            dirname for dirname in os.listdir(TEST_VERSIONS_DIR) if run_uuid in dirname
        ]
        assert len(rollback_context_directories) == 1, (
            f"Expected one directory for run UUID {run_uuid}, found: {rollback_context_directories}"
        )

        scenario_rollback_versions_directory = os.path.join(
            TEST_VERSIONS_DIR, rollback_context_directories[0]
        )
        version_files = os.listdir(scenario_rollback_versions_directory)
        assert len(version_files) == versions, (
            f"Expected {versions} version files, found: {len(version_files)}"
        )
        for version_file in version_files:
            assert version_file.startswith(scenario), (
                f"Version file {version_file} does not start with '{scenario}'"
            )
            assert version_file.endswith(".py"), (
                f"Version file {version_file} does not end with '.py'"
            )

        return [
            os.path.join(scenario_rollback_versions_directory, vf)
            for vf in version_files
        ]

    def execute_version_file(self, version_file: str):
        """
        Execute a rollback version file using subprocess.

        :param version_file: The path to the version file to execute.
        """
        print(f"Executing rollback version file: {version_file}")
        result = subprocess.run(
            [sys.executable, version_file],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Rollback version file {version_file} failed with return code {result.returncode}. "
            f"Output: {result.stdout}, Error: {result.stderr}"
        )
        print(
            f"Rollback version file executed successfully: {version_file} with output: {result.stdout}"
        )

    @pytest.fixture(autouse=True)
    def setup_logging(self):
        os.makedirs(TEST_LOGS_DIR, exist_ok=True)
        # setup logging
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(os.path.join(TEST_LOGS_DIR, "test_rollback.log")),
                logging.StreamHandler(),
            ],
        )

    @pytest.fixture(scope="module")
    def kubeconfig_path(self):
        # Provide the path to the kubeconfig file for testing
        return os.getenv("KUBECONFIG", "~/.kube/config")

    @pytest.fixture(scope="module")
    def safe_logger(self):
        os.makedirs(TEST_LOGS_DIR, exist_ok=True)
        with open(os.path.join(TEST_LOGS_DIR, "telemetry.log"), "w") as f:
            pass  # Create the file if it doesn't exist
        yield SafeLogger(filename=os.path.join(TEST_LOGS_DIR, "telemetry.log"))

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

    @pytest.fixture(scope="module")
    def setup_rollback_config(self):
        RollbackConfig.register(
            auto=False,
            versions_directory=TEST_VERSIONS_DIR,
        )

    @pytest.mark.usefixtures("setup_rollback_config")
    def test_simple_rollback_scenario_plugin(self, lib_telemetry, scenario_telemetry):
        from tests.rollback_scenario_plugins.simple import SimpleRollbackScenarioPlugin

        scenario_type = "simple_rollback_scenario"
        simple_rollback_scenario_plugin = SimpleRollbackScenarioPlugin(
            scenario_type=scenario_type,
        )
        run_uuid = str(uuid.uuid4())
        simple_rollback_scenario_plugin.run(
            run_uuid=run_uuid,
            scenario="test_scenario",
            krkn_config={
                "key1": "value",
                "key2": False,
                "key3": 123,
                "key4": ["value1", "value2", "value3"],
            },
            lib_telemetry=lib_telemetry,
            scenario_telemetry=scenario_telemetry,
        )
        # Validate the rollback directory and version files do exist
        version_files = self.validate_rollback_directory(
            run_uuid,
            scenario_type,
        )
        # Execute the rollback version file
        for version_file in version_files:
            self.execute_version_file(version_file)
