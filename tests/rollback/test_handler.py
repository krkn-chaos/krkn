#!/usr/bin/env python3

"""
Test suite for krkn.rollback.handler module

This test file provides comprehensive coverage for:
- set_rollback_context_decorator
- _parse_rollback_module
- execute_rollback_version_files
- cleanup_rollback_version_files
- RollbackHandler class

Usage:
    python3 -m coverage run --source=krkn -m pytest tests/rollback/test_handler.py -v
    python3 -m coverage report -m --include=krkn/rollback/handler.py
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from krkn.rollback.handler import (
    set_rollback_context_decorator,
    _parse_rollback_module,
    execute_rollback_version_files,
    cleanup_rollback_version_files,
    RollbackHandler,
)

class TestSetRollbackContextDecorator(unittest.TestCase):
    """Test suite for set_rollback_context_decorator"""

    def test_decorator_sets_and_clears_context(self):
        """Test decorator sets context before function and clears after"""
        mock_rollback_handler = MagicMock()
        
        class MockPlugin:
            def __init__(self):
                self.rollback_handler = mock_rollback_handler
            
            @set_rollback_context_decorator
            def run(self, run_uuid=None, **kwargs):
                return "success"
        
        plugin = MockPlugin()
        result = plugin.run(run_uuid="test-uuid-123")
        
        self.assertEqual(result, "success")
        mock_rollback_handler.set_context.assert_called_once_with("test-uuid-123")
        mock_rollback_handler.clear_context.assert_called_once()

    def test_decorator_clears_context_on_exception(self):
        """Test decorator clears context even when function raises exception"""
        mock_rollback_handler = MagicMock()
        
        class MockPlugin:
            def __init__(self):
                self.rollback_handler = mock_rollback_handler
            
            @set_rollback_context_decorator
            def run(self, run_uuid=None, **kwargs):
                raise ValueError("Test error")
        
        plugin = MockPlugin()
        
        with self.assertRaises(ValueError):
            plugin.run(run_uuid="test-uuid-123")
        
        mock_rollback_handler.set_context.assert_called_once_with("test-uuid-123")
        mock_rollback_handler.clear_context.assert_called_once()

    def test_decorator_without_rollback_handler(self):
        """Test decorator works when plugin has no rollback_handler"""
        class MockPlugin:
            @set_rollback_context_decorator
            def run(self, run_uuid=None, **kwargs):
                return "no handler"
        
        plugin = MockPlugin()
        result = plugin.run(run_uuid="test-uuid")
        
        self.assertEqual(result, "no handler")

    def test_decorator_requires_run_uuid(self):
        """Test decorator raises assertion when run_uuid is None"""
        class MockPlugin:
            def __init__(self):
                self.rollback_handler = MagicMock()
            
            @set_rollback_context_decorator
            def run(self, run_uuid=None, **kwargs):
                return "success"
        
        plugin = MockPlugin()
        
        with self.assertRaises(AssertionError):
            plugin.run()  # No run_uuid provided


class TestParseRollbackModule(unittest.TestCase):
    """Test suite for _parse_rollback_module function"""

    def test_parse_valid_rollback_module(self):
        """Test parsing a valid rollback module"""
        # Create a temporary rollback module file
        module_content = '''
from krkn.rollback.config import RollbackContent
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

def rollback_test(content: RollbackContent, telemetry: KrknTelemetryOpenshift):
    pass

rollback_content = {"key": "value"}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(module_content)
            temp_file = f.name
        
        try:
            with patch('inspect.signature') as mock_sig:
                # Mock the signature to return proper parameter annotations
                mock_param1 = MagicMock()
                mock_param1.annotation = 'RollbackContent'
                mock_param2 = MagicMock()
                mock_param2.annotation = 'KrknTelemetryOpenshift'
                mock_sig.return_value.parameters.values.return_value = [mock_param1, mock_param2]
                
                rollback_callable, rollback_content = _parse_rollback_module(temp_file)
                
                self.assertIsNotNone(rollback_callable)
                self.assertEqual(rollback_content, {"key": "value"})
        finally:
            os.unlink(temp_file)

    def test_parse_module_no_spec(self):
        """Test parsing fails when module spec is None"""
        with patch('importlib.util.spec_from_file_location', return_value=None):
            with self.assertRaises(ImportError):
                _parse_rollback_module("/nonexistent/file.py")

    def test_parse_module_no_rollback_function(self):
        """Test parsing fails when no valid rollback function found"""
        module_content = '''
rollback_content = {"key": "value"}

def not_a_rollback():
    pass
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(module_content)
            temp_file = f.name
        
        try:
            with self.assertRaises(ValueError) as ctx:
                _parse_rollback_module(temp_file)
            self.assertIn("No valid rollback function found", str(ctx.exception))
        finally:
            os.unlink(temp_file)

    def test_parse_module_no_rollback_content(self):
        """Test parsing fails when rollback_content variable is missing"""
        module_content = '''
from krkn.rollback.config import RollbackContent
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

def rollback_test(content: RollbackContent, telemetry: KrknTelemetryOpenshift):
    pass
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(module_content)
            temp_file = f.name
        
        try:
            with patch('inspect.signature') as mock_sig:
                mock_param1 = MagicMock()
                mock_param1.annotation = 'RollbackContent'
                mock_param2 = MagicMock()
                mock_param2.annotation = 'KrknTelemetryOpenshift'
                mock_sig.return_value.parameters.values.return_value = [mock_param1, mock_param2]
                
                with self.assertRaises(ValueError) as ctx:
                    _parse_rollback_module(temp_file)
                self.assertIn("rollback_content", str(ctx.exception))
        finally:
            os.unlink(temp_file)

    def test_parse_module_rollback_content_is_none(self):
        """Test parsing fails when rollback_content variable is None"""
        module_content = '''
from krkn.rollback.config import RollbackContent
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

def rollback_test(content: RollbackContent, telemetry: KrknTelemetryOpenshift):
    pass

rollback_content = None
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(module_content)
            temp_file = f.name
        
        try:
            with patch('inspect.signature') as mock_sig:
                mock_param1 = MagicMock()
                mock_param1.annotation = 'RollbackContent'
                mock_param2 = MagicMock()
                mock_param2.annotation = 'KrknTelemetryOpenshift'
                mock_sig.return_value.parameters.values.return_value = [mock_param1, mock_param2]
                
                with self.assertRaises(ValueError) as ctx:
                    _parse_rollback_module(temp_file)
                self.assertIn("rollback_content", str(ctx.exception).lower())
                self.assertIn("None", str(ctx.exception))
        finally:
            os.unlink(temp_file)


class TestExecuteRollbackVersionFiles(unittest.TestCase):
    """Test suite for execute_rollback_version_files function"""

    @patch('krkn.rollback.handler.RollbackConfig')
    def test_execute_skips_when_auto_disabled(self, mock_config_class):
        """Test execution skips when auto rollback is disabled"""
        mock_config = MagicMock()
        mock_config.auto = False
        mock_config_class.return_value = mock_config
        
        mock_telemetry = MagicMock()
        
        # Should return early without executing
        execute_rollback_version_files(mock_telemetry, "test-uuid", "test-scenario")
        
        # search_rollback_version_files should not be called when auto is False
        mock_config_class.search_rollback_version_files.assert_not_called()

    @patch('krkn.rollback.handler.RollbackConfig')
    def test_execute_skips_when_no_version_files(self, mock_config_class):
        """Test execution skips when no version files found"""
        mock_config = MagicMock()
        mock_config.auto = True
        mock_config_class.return_value = mock_config
        mock_config_class.search_rollback_version_files.return_value = []
        
        mock_telemetry = MagicMock()
        
        execute_rollback_version_files(mock_telemetry, "test-uuid", "test-scenario")
        
        mock_config_class.search_rollback_version_files.assert_called_once_with("test-uuid", "test-scenario")

    @patch('krkn.rollback.handler.os.rename')
    @patch('krkn.rollback.handler._parse_rollback_module')
    @patch('krkn.rollback.handler.RollbackConfig')
    def test_execute_successful_rollback(self, mock_config_class, mock_parse, mock_rename):
        """Test successful rollback execution"""
        mock_config = MagicMock()
        mock_config.auto = True
        mock_config_class.return_value = mock_config
        mock_config_class.search_rollback_version_files.return_value = ["/path/to/version.py"]
        
        mock_callable = MagicMock()
        mock_content = {"key": "value"}
        mock_parse.return_value = (mock_callable, mock_content)
        
        mock_telemetry = MagicMock()
        
        execute_rollback_version_files(mock_telemetry, "test-uuid", "test-scenario")
        
        mock_callable.assert_called_once_with(mock_content, mock_telemetry)
        mock_rename.assert_called_once_with("/path/to/version.py", "/path/to/version.py.executed")

    @patch('krkn.rollback.handler._parse_rollback_module')
    @patch('krkn.rollback.handler.RollbackConfig')
    def test_execute_rollback_failure(self, mock_config_class, mock_parse):
        """Test rollback execution failure"""
        mock_config = MagicMock()
        mock_config.auto = True
        mock_config_class.return_value = mock_config
        mock_config_class.search_rollback_version_files.return_value = ["/path/to/version.py"]
        
        mock_callable = MagicMock()
        mock_callable.side_effect = Exception("Rollback failed")
        mock_content = {"key": "value"}
        mock_parse.return_value = (mock_callable, mock_content)
        
        mock_telemetry = MagicMock()
        
        with self.assertRaises(Exception):
            execute_rollback_version_files(mock_telemetry, "test-uuid", "test-scenario")

    @patch('krkn.rollback.handler.os.rename')
    @patch('krkn.rollback.handler._parse_rollback_module')
    @patch('krkn.rollback.handler.RollbackConfig')
    def test_execute_rename_failure(self, mock_config_class, mock_parse, mock_rename):
        """Test execution when rename fails"""
        mock_config = MagicMock()
        mock_config.auto = True
        mock_config_class.return_value = mock_config
        mock_config_class.search_rollback_version_files.return_value = ["/path/to/version.py"]
        
        mock_callable = MagicMock()
        mock_content = {"key": "value"}
        mock_parse.return_value = (mock_callable, mock_content)
        mock_rename.side_effect = OSError("Rename failed")
        
        mock_telemetry = MagicMock()
        
        with self.assertRaises(OSError):
            execute_rollback_version_files(mock_telemetry, "test-uuid", "test-scenario")

    @patch('krkn.rollback.handler.os.rename')
    @patch('krkn.rollback.handler._parse_rollback_module')
    @patch('krkn.rollback.handler.RollbackConfig')
    def test_execute_with_ignore_auto_rollback(self, mock_config_class, mock_parse, mock_rename):
        """Test execution with ignore_auto_rollback_config=True"""
        mock_config = MagicMock()
        mock_config.auto = False  # Auto is disabled
        mock_config_class.return_value = mock_config
        mock_config_class.search_rollback_version_files.return_value = ["/path/to/version.py"]
        
        mock_callable = MagicMock()
        mock_content = {"key": "value"}
        mock_parse.return_value = (mock_callable, mock_content)
        
        mock_telemetry = MagicMock()
        
        # Should execute even though auto is False because ignore_auto_rollback_config=True
        execute_rollback_version_files(
            mock_telemetry, "test-uuid", "test-scenario", 
            ignore_auto_rollback_config=True
        )
        
        mock_callable.assert_called_once()


class TestCleanupRollbackVersionFiles(unittest.TestCase):
    """Test suite for cleanup_rollback_version_files function"""

    @patch('krkn.rollback.handler.RollbackConfig')
    def test_cleanup_skips_when_no_files(self, mock_config_class):
        """Test cleanup skips when no version files found"""
        mock_config_class.search_rollback_version_files.return_value = []
        
        cleanup_rollback_version_files("test-uuid", "test-scenario")
        
        mock_config_class.search_rollback_version_files.assert_called_once_with("test-uuid", "test-scenario")

    @patch('krkn.rollback.handler.os.remove')
    @patch('krkn.rollback.handler.RollbackConfig')
    def test_cleanup_removes_files(self, mock_config_class, mock_remove):
        """Test cleanup removes version files"""
        mock_config_class.search_rollback_version_files.return_value = [
            "/path/to/version1.py",
            "/path/to/version2.py"
        ]
        
        cleanup_rollback_version_files("test-uuid", "test-scenario")
        
        self.assertEqual(mock_remove.call_count, 2)
        mock_remove.assert_any_call("/path/to/version1.py")
        mock_remove.assert_any_call("/path/to/version2.py")

    @patch('krkn.rollback.handler.os.remove')
    @patch('krkn.rollback.handler.RollbackConfig')
    def test_cleanup_raises_on_remove_error(self, mock_config_class, mock_remove):
        """Test cleanup raises exception on remove error"""
        mock_config_class.search_rollback_version_files.return_value = ["/path/to/version.py"]
        mock_remove.side_effect = OSError("Remove failed")
        
        with self.assertRaises(OSError):
            cleanup_rollback_version_files("test-uuid", "test-scenario")


class TestRollbackHandler(unittest.TestCase):
    """Test suite for RollbackHandler class"""

    def test_init(self):
        """Test RollbackHandler initialization"""
        mock_serializer = MagicMock()
        
        handler = RollbackHandler("test-scenario", mock_serializer)
        
        self.assertEqual(handler.scenario_type, "test-scenario")
        self.assertEqual(handler.serializer, mock_serializer)
        self.assertIsNone(handler.rollback_context)

    def test_set_context(self):
        """Test set_context sets rollback context"""
        mock_serializer = MagicMock()
        handler = RollbackHandler("test-scenario", mock_serializer)
        
        handler.set_context("test-uuid-123")
        
        self.assertIsNotNone(handler.rollback_context)
        # RollbackContext is a string formatted as '<timestamp>-<run_uuid>'
        self.assertIn("test-uuid-123", str(handler.rollback_context))

    def test_clear_context(self):
        """Test clear_context clears rollback context"""
        mock_serializer = MagicMock()
        handler = RollbackHandler("test-scenario", mock_serializer)
        handler.set_context("test-uuid-123")
        
        self.assertIsNotNone(handler.rollback_context)
        
        handler.clear_context()
        
        self.assertIsNone(handler.rollback_context)

    @patch('krkn.rollback.handler.RollbackConfig')
    def test_set_rollback_callable(self, mock_config_class):
        """Test set_rollback_callable serializes callable"""
        mock_serializer = MagicMock()
        mock_serializer.serialize_callable.return_value = "/path/to/version.py"
        
        handler = RollbackHandler("test-scenario", mock_serializer)
        handler.set_context("test-uuid-123")
        
        mock_callable = MagicMock()
        mock_callable.__name__ = "test_rollback"
        mock_content = {"key": "value"}
        
        handler.set_rollback_callable(mock_callable, mock_content)
        
        mock_serializer.serialize_callable.assert_called_once()
        call_args = mock_serializer.serialize_callable.call_args
        self.assertEqual(call_args[0][0], mock_callable)
        self.assertEqual(call_args[0][1], mock_content)

    @patch('krkn.rollback.handler.RollbackConfig')
    def test_set_rollback_callable_serialization_error(self, mock_config_class):
        """Test set_rollback_callable handles serialization error"""
        mock_serializer = MagicMock()
        mock_serializer.serialize_callable.side_effect = Exception("Serialization failed")
        
        handler = RollbackHandler("test-scenario", mock_serializer)
        handler.set_context("test-uuid-123")
        
        mock_callable = MagicMock()
        mock_callable.__name__ = "test_rollback"
        mock_content = {"key": "value"}
        
        # Should not raise, just log error
        handler.set_rollback_callable(mock_callable, mock_content)
        
        mock_serializer.serialize_callable.assert_called_once()


if __name__ == "__main__":
    unittest.main()
