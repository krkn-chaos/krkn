#!/usr/bin/env python3

"""
Test suite for krkn/rollback/command.py

This test file provides comprehensive coverage for the rollback command functions:
- list_rollback: Lists rollback version files in a tree-like format
- execute_rollback: Executes rollback version files and cleanup

Usage:
    python3 -m coverage run --source=krkn -m pytest tests/rollback/test_command.py -v
    python3 -m coverage report -m --include=krkn/rollback/command.py
"""

import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import tempfile
import shutil

from krkn.rollback.command import list_rollback, execute_rollback


class TestListRollback(unittest.TestCase):
    """Test suite for list_rollback function"""

    def setUp(self):
        """Set up test fixtures"""
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures"""
        # Remove the temporary directory
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_directory_not_exists(self, mock_config):
        """Test list_rollback when versions directory does not exist"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = "/nonexistent/path"
        mock_config.return_value = mock_config_instance

        result = list_rollback()

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_no_run_directories(self, mock_config):
        """Test list_rollback when no run directories found"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        result = list_rollback()

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_no_run_directories_with_uuid_filter(self, mock_config):
        """Test list_rollback when no run directories found with UUID filter"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        result = list_rollback(run_uuid="nonexistent-uuid")

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_with_directories_and_files(self, mock_config):
        """Test list_rollback with directories and files"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        # Create test directory structure
        run_dir1 = os.path.join(self.test_dir, "run-uuid-001")
        run_dir2 = os.path.join(self.test_dir, "run-uuid-002")
        os.makedirs(run_dir1)
        os.makedirs(run_dir2)

        # Create test files
        with open(os.path.join(run_dir1, "scenario1_v1.yaml"), "w") as f:
            f.write("test")
        with open(os.path.join(run_dir1, "scenario2_v1.yaml"), "w") as f:
            f.write("test")
        with open(os.path.join(run_dir2, "scenario3_v1.yaml"), "w") as f:
            f.write("test")

        result = list_rollback()

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_with_run_uuid_filter(self, mock_config):
        """Test list_rollback with run_uuid filter"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        # Create test directory structure
        run_dir1 = os.path.join(self.test_dir, "run-uuid-001")
        run_dir2 = os.path.join(self.test_dir, "run-uuid-002")
        os.makedirs(run_dir1)
        os.makedirs(run_dir2)

        # Create test files
        with open(os.path.join(run_dir1, "scenario1_v1.yaml"), "w") as f:
            f.write("test")

        result = list_rollback(run_uuid="uuid-001")

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_with_scenario_type_filter(self, mock_config):
        """Test list_rollback with scenario_type filter"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        # Create test directory structure
        run_dir1 = os.path.join(self.test_dir, "run-uuid-001")
        os.makedirs(run_dir1)

        # Create test files with different scenario types
        with open(os.path.join(run_dir1, "pod_scenario_v1.yaml"), "w") as f:
            f.write("test")
        with open(os.path.join(run_dir1, "node_scenario_v1.yaml"), "w") as f:
            f.write("test")

        result = list_rollback(scenario_type="pod")

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_single_directory_is_last(self, mock_config):
        """Test list_rollback with single directory (is_last_dir = True)"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        # Create single test directory
        run_dir1 = os.path.join(self.test_dir, "run-uuid-001")
        os.makedirs(run_dir1)

        # Create multiple test files to test file iteration
        with open(os.path.join(run_dir1, "scenario1_v1.yaml"), "w") as f:
            f.write("test")
        with open(os.path.join(run_dir1, "scenario2_v1.yaml"), "w") as f:
            f.write("test")

        result = list_rollback()

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    @patch('os.listdir')
    def test_list_rollback_permission_error(self, mock_listdir, mock_config):
        """Test list_rollback with PermissionError on subdirectory"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        # Create test directory structure
        run_dir1 = os.path.join(self.test_dir, "run-uuid-001")
        os.makedirs(run_dir1)

        # First call returns directories, second call raises PermissionError
        def listdir_side_effect(path):
            if path == self.test_dir:
                return ["run-uuid-001"]
            raise PermissionError("Permission denied")

        mock_listdir.side_effect = listdir_side_effect

        with patch('os.path.isdir', return_value=True):
            with patch('os.path.exists', return_value=True):
                result = list_rollback()

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    @patch('os.listdir')
    def test_list_rollback_general_exception(self, mock_listdir, mock_config):
        """Test list_rollback with general Exception"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        mock_listdir.side_effect = Exception("General error")

        with patch('os.path.exists', return_value=True):
            result = list_rollback()

        self.assertEqual(result, 1)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_multiple_directories_not_last(self, mock_config):
        """Test list_rollback with multiple directories (is_last_dir = False for first ones)"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        # Create multiple test directories
        run_dir1 = os.path.join(self.test_dir, "run-uuid-001")
        run_dir2 = os.path.join(self.test_dir, "run-uuid-002")
        run_dir3 = os.path.join(self.test_dir, "run-uuid-003")
        os.makedirs(run_dir1)
        os.makedirs(run_dir2)
        os.makedirs(run_dir3)

        # Create files in each directory
        with open(os.path.join(run_dir1, "scenario1_v1.yaml"), "w") as f:
            f.write("test")
        with open(os.path.join(run_dir2, "scenario2_v1.yaml"), "w") as f:
            f.write("test")
        with open(os.path.join(run_dir2, "scenario3_v1.yaml"), "w") as f:
            f.write("test")

        result = list_rollback()

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_empty_directory(self, mock_config):
        """Test list_rollback with empty run directory (no files)"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        # Create test directory without files
        run_dir1 = os.path.join(self.test_dir, "run-uuid-001")
        os.makedirs(run_dir1)

        result = list_rollback()

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_with_subdirectory_in_run_dir(self, mock_config):
        """Test list_rollback ignores subdirectories in run directory"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        # Create test directory structure
        run_dir1 = os.path.join(self.test_dir, "run-uuid-001")
        os.makedirs(run_dir1)

        # Create a subdirectory (should be ignored)
        subdir = os.path.join(run_dir1, "subdir")
        os.makedirs(subdir)

        # Create a file
        with open(os.path.join(run_dir1, "scenario1_v1.yaml"), "w") as f:
            f.write("test")

        result = list_rollback()

        self.assertEqual(result, 0)

    @patch('krkn.rollback.command.RollbackConfig')
    def test_list_rollback_file_in_versions_directory(self, mock_config):
        """Test list_rollback ignores files in versions directory root"""
        mock_config_instance = MagicMock()
        mock_config_instance.versions_directory = self.test_dir
        mock_config.return_value = mock_config_instance

        # Create a file in root (should be ignored, only dirs are listed)
        with open(os.path.join(self.test_dir, "some_file.txt"), "w") as f:
            f.write("test")

        # Create a run directory
        run_dir1 = os.path.join(self.test_dir, "run-uuid-001")
        os.makedirs(run_dir1)

        result = list_rollback()

        self.assertEqual(result, 0)


class TestExecuteRollback(unittest.TestCase):
    """Test suite for execute_rollback function"""

    @patch('krkn.rollback.command.execute_rollback_version_files')
    def test_execute_rollback_success(self, mock_execute):
        """Test execute_rollback successful execution"""
        mock_telemetry = MagicMock()

        result = execute_rollback(mock_telemetry)

        self.assertEqual(result, 0)
        mock_execute.assert_called_once_with(
            mock_telemetry,
            None,
            None,
            ignore_auto_rollback_config=True
        )

    @patch('krkn.rollback.command.execute_rollback_version_files')
    def test_execute_rollback_with_run_uuid(self, mock_execute):
        """Test execute_rollback with run_uuid parameter"""
        mock_telemetry = MagicMock()

        result = execute_rollback(mock_telemetry, run_uuid="test-uuid-123")

        self.assertEqual(result, 0)
        mock_execute.assert_called_once_with(
            mock_telemetry,
            "test-uuid-123",
            None,
            ignore_auto_rollback_config=True
        )

    @patch('krkn.rollback.command.execute_rollback_version_files')
    def test_execute_rollback_with_scenario_type(self, mock_execute):
        """Test execute_rollback with scenario_type parameter"""
        mock_telemetry = MagicMock()

        result = execute_rollback(mock_telemetry, scenario_type="pod_scenario")

        self.assertEqual(result, 0)
        mock_execute.assert_called_once_with(
            mock_telemetry,
            None,
            "pod_scenario",
            ignore_auto_rollback_config=True
        )

    @patch('krkn.rollback.command.execute_rollback_version_files')
    def test_execute_rollback_with_all_parameters(self, mock_execute):
        """Test execute_rollback with all parameters"""
        mock_telemetry = MagicMock()

        result = execute_rollback(
            mock_telemetry,
            run_uuid="test-uuid-123",
            scenario_type="pod_scenario"
        )

        self.assertEqual(result, 0)
        mock_execute.assert_called_once_with(
            mock_telemetry,
            "test-uuid-123",
            "pod_scenario",
            ignore_auto_rollback_config=True
        )

    @patch('krkn.rollback.command.execute_rollback_version_files')
    def test_execute_rollback_exception(self, mock_execute):
        """Test execute_rollback with exception"""
        mock_telemetry = MagicMock()
        mock_execute.side_effect = Exception("Rollback failed")

        result = execute_rollback(mock_telemetry)

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
