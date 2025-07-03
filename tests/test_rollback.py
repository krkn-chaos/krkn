import pytest
import logging
import os
import sys
import uuid

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.utils import SafeLogger
from krkn.rollback.config import RollbackConfig

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # Adjust path to include krkn
TEST_LOGS_DIR = "/tmp/krkn_test_rollback_logs_directory"
TEST_VERSIONS_DIR = "/tmp/krkn_test_rollback_versions_directory"

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

    def test_simple_rollback_scenario_plugin(self, lib_telemetry, scenario_telemetry):
        from tests.rollback_scenario_plugins.simple import SimpleRollbackScenarioPlugin

        simple_rollback_scenario_plugin = SimpleRollbackScenarioPlugin(
            scenario_type="simple_rollback_scenario",
            rollback_config=RollbackConfig(
                auto=False,
                versions_directory=TEST_VERSIONS_DIR,
            )
        )
        run_uuid = str(uuid.uuid4())
        simple_rollback_scenario_plugin.run(
            run_uuid=run_uuid,
            scenario="test_scenario",
            krkn_config={"key1": "value", "key2": False, "key3": 123, "key4": ["value1", "value2", "value3"]},
            lib_telemetry=lib_telemetry,
            scenario_telemetry=scenario_telemetry,
        )

        self.validate_rollback_directory(
            f"{TEST_VERSIONS_DIR}/simple_rollback_scenario/{run_uuid}",
        )