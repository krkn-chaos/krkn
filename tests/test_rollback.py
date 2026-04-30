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

    def execute_version_file(self, version_file: str, telemetry_ocp: KrknTelemetryOpenshift):
        """
        Execute a rollback version file using the new importlib approach.

        :param version_file: The path to the version file to execute.
        """
        print(f"Executing rollback version file: {version_file}")
        try:
            from krkn.rollback.handler import _parse_rollback_module

            rollback_callable, rollback_content = _parse_rollback_module(version_file)
            rollback_callable(rollback_content, telemetry_ocp)
            print(f"Rollback version file executed successfully: {version_file}")
        except Exception as e:
            raise AssertionError(
                f"Rollback version file {version_file} failed with error: {e}"
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
    def test_simple_rollback_scenario_plugin(
        self,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ):
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
            self.execute_version_file(version_file, lib_telemetry)

class TestRollbackConfig:

    @pytest.mark.parametrize("directory_name,run_uuid,expected", [
        ("123456789-abcdefgh", "abcdefgh", True),
        ("123456789-abcdefgh", None, True),
        ("123456789-abcdefgh", "ijklmnop", False),
        ("123456789-", "abcdefgh", False),
        ("-abcdefgh", "abcdefgh", False),
        ("123456789-abcdefgh-ijklmnop", "abcdefgh", False),
    ])
    def test_is_rollback_context_directory_format(self, directory_name, run_uuid, expected):
        assert RollbackConfig.is_rollback_context_directory_format(directory_name, run_uuid) == expected

    @pytest.mark.parametrize("file_name,expected", [
        ("simple_rollback_scenario_123456789_abcdefgh.py", True),
        ("simple_rollback_scenario_123456789_abcdefgh.py.executed", False),
        ("simple_rollback_scenario_123456789_abc.py", False),
        ("simple_rollback_scenario_123456789_abcdefgh.txt", False),
        ("simple_rollback_scenario_123456789_.py", False),
    ])
    def test_is_rollback_version_file_format(self, file_name, expected):
        assert RollbackConfig.is_rollback_version_file_format(file_name) == expected

class TestRollbackCommand:
    
    @pytest.mark.parametrize("auto_rollback", [True, False], ids=["enabled_rollback", "disabled_rollback"])
    @pytest.mark.parametrize("encounter_exception", [True, False], ids=["no_exception", "with_exception"])
    def test_execute_rollback_command_ignore_auto_rollback_config(self, auto_rollback, encounter_exception):
        """Test execute_rollback function with different auto rollback configurations."""
        from krkn.rollback.command import execute_rollback
        from krkn.rollback.config import RollbackConfig
        from unittest.mock import Mock, patch
        
        # Create mock telemetry
        mock_telemetry = Mock()

        # Mock search_rollback_version_files to return some test files
        mock_version_files = [
            "/tmp/test_versions/123456789-test-uuid/scenario_123456789_abcdefgh.py",
            "/tmp/test_versions/123456789-test-uuid/scenario_123456789_ijklmnop.py"
        ]
        
        with (
            patch.object(RollbackConfig, 'auto', auto_rollback) as _,
            patch.object(RollbackConfig, 'search_rollback_version_files', return_value=mock_version_files) as mock_search,
            patch('krkn.rollback.command.execute_rollback_version_files') as mock_execute
        ):
            if encounter_exception:
                mock_execute.side_effect = Exception("Test exception")
            # Call the function
            result = execute_rollback(
                telemetry_ocp=mock_telemetry,
                run_uuid="test-uuid",
                scenario_type="scenario"
            )
                
            # Verify return code
            assert result == 0 if not encounter_exception else 1
            
            # Verify that execute_rollback_version_files was called with correct parameters
            mock_execute.assert_called_once_with(
                mock_telemetry,
                "test-uuid",
                "scenario",
                ignore_auto_rollback_config=True
            )

class TestRollbackAbstractScenarioPlugin:

    @pytest.mark.parametrize("auto_rollback", [True, False], ids=["enabled_rollback", "disabled_rollback"])
    @pytest.mark.parametrize("scenario_should_fail", [True, False], ids=["failing_scenario", "successful_scenario"])
    def test_run_scenarios_respect_auto_rollback_config(self, auto_rollback, scenario_should_fail):
        """Test that run_scenarios respects the auto rollback configuration."""
        from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
        from krkn.rollback.config import RollbackConfig
        from unittest.mock import Mock, patch
        
        # Create a test scenario plugin
        class TestScenarioPlugin(AbstractScenarioPlugin):
            def run(self, run_uuid: str, scenario: str, krkn_config: dict, lib_telemetry, scenario_telemetry):
                return 1 if scenario_should_fail else 0
            
            def get_scenario_types(self) -> list[str]:
                return ["test_scenario"]
        
        # Create mock objects
        mock_telemetry = Mock()
        mock_telemetry.set_parameters_base64.return_value = "test_scenario.yaml"
        mock_telemetry.get_telemetry_request_id.return_value = "test_request_id"
        mock_telemetry.get_lib_kubernetes.return_value = Mock()
        
        test_plugin = TestScenarioPlugin("test_scenario")
        
        # Mock version files to be returned by search
        mock_version_files = [
            "/tmp/test_versions/123456789-test-uuid/test_scenario_123456789_abcdefgh.py"
        ]
        
        with (
            patch.object(RollbackConfig, 'auto', auto_rollback),
            patch.object(RollbackConfig, 'versions_directory', "/tmp/test_versions"),
            patch.object(RollbackConfig, 'search_rollback_version_files', return_value=mock_version_files) as mock_search,
            patch('krkn.rollback.handler._parse_rollback_module') as mock_parse,
            patch('krkn.scenario_plugins.abstract_scenario_plugin.utils.collect_and_put_ocp_logs'),
            patch('krkn.scenario_plugins.abstract_scenario_plugin.signal_handler.signal_context') as mock_signal_context,
            patch('krkn.scenario_plugins.abstract_scenario_plugin.time.sleep'),
            patch('os.path.exists', return_value=True),
            patch('os.rename') as mock_rename,
            patch('os.remove') as mock_remove
        ):
            # Make signal_context a no-op context manager
            mock_signal_context.return_value.__enter__ = Mock(return_value=None)
            mock_signal_context.return_value.__exit__ = Mock(return_value=None)
            
            # Mock _parse_rollback_module to return test callable and content
            mock_rollback_callable = Mock()
            mock_rollback_content = Mock()
            mock_parse.return_value = (mock_rollback_callable, mock_rollback_content)
            
            # Call run_scenarios
            test_plugin.run_scenarios(
                run_uuid="test-uuid",
                scenarios_list=["test_scenario.yaml"],
                krkn_config={
                    "tunings": {"wait_duration": 0},
                    "telemetry": {"events_backup": False}
                },
                telemetry=mock_telemetry
            )
            
            # Verify results
            if scenario_should_fail:
                if auto_rollback:
                    # search_rollback_version_files should always be called when scenario fails
                    mock_search.assert_called_once_with("test-uuid", "test_scenario")
                    # When auto_rollback is True, _parse_rollback_module should be called
                    mock_parse.assert_called_once_with(mock_version_files[0])
                    # And the rollback callable should be executed
                    mock_rollback_callable.assert_called_once_with(mock_rollback_content, mock_telemetry)
                    # File should be renamed after successful execution
                    mock_rename.assert_called_once_with(
                        mock_version_files[0], 
                        f"{mock_version_files[0]}.executed"
                    )
                else:
                    # When scenario fail but auto_rollback is False, _parse_rollback_module should NOT be called
                    mock_search.assert_not_called()
                    mock_parse.assert_not_called()
                    mock_rollback_callable.assert_not_called()
                    mock_rename.assert_not_called()
            else:
                mock_search.assert_called_once_with("test-uuid", "test_scenario")
                # Will remove the version files instead of renaming them if scenario succeeds
                mock_remove.assert_called_once_with(
                    mock_version_files[0]
                )

                # When scenario succeeds, rollback should not be executed at all
                mock_parse.assert_not_called()
                mock_rollback_callable.assert_not_called()
                mock_rename.assert_not_called()